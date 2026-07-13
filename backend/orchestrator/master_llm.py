import asyncio
import re
import logging
from typing import AsyncGenerator
import json
from models.embedding import LocalEmbeddingModel
from retrieval.vector_db import VectorDatabase
from retrieval.reranker import RerankerModel
from models.generation import GenerationModel
from verification.verifier import VerificationModule
from retrieval.visualizer import VisualizerAgent
from retrieval.web_search import search_web
from core.memory_manager import NotebookMemory
from core.persona_memory import AgentPersonaMemory
from utils.cache import ResponseCache
from actions.contacts import ContactsStore
from actions.registry import ActionRegistry
from actions.extractor import ActionExtractor, scan_for_injection
from actions.gmail_client import GmailClient
from actions.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """
    Coordinates the multi-model RAG workflow.
    Publishes status events directly formatted for SSE.
    
    Performance Optimizations:
    - Parallel web search queries using asyncio.gather
    - Response caching to avoid redundant processing
    - Skip retry loop (max_retries = 0) for faster responses
    - Streaming response chunks for better UX
    """
    def __init__(self):
        self.vector_db = VectorDatabase()
        self.reranker = RerankerModel()
        self.persona_memory = AgentPersonaMemory()
        self.generator = GenerationModel(persona_memory=self.persona_memory)
        self.verifier = VerificationModule()
        self.visualizer = VisualizerAgent(persona_memory=self.persona_memory)
        self.notebook = NotebookMemory()
        self.cache = ResponseCache()
        self.last_image_context = "" # Persist last analyzed image context

        # Outbound actions (email / WhatsApp). These are the only parts of the system
        # that can affect the outside world, so they never fire on their own: the agent
        # drafts, a human approves, and only then does anything get sent.
        self.contacts = ContactsStore()
        self.actions = ActionRegistry()
        self.extractor = ActionExtractor(self.generator.llm, self.contacts)
        self.gmail = GmailClient()
        self.whatsapp = WhatsAppClient()

    async def process_query_stream(self, query: str, history: str = "", image_context: str = "", model_choice: str = "auto") -> AsyncGenerator[str, None]:
        """
        Executes the entire RAG pipeline and yields SSE JSON strings at each step.
        """
        def emit(model, status, action, details=None):
            data = {"model": model, "status": status, "action": action}
            if details:
                data["details"] = details
            return json.dumps(data)

        # 1. Start pipeline
        active_model = self.generator.llm.get_active_model_name(model_choice)
        yield emit("Master LLM Orchestrator", "Processing", f"Analyzing user intent via {active_model}")
        
        search_query = query
        if history:
            vision_hint = ""
            if self.last_image_context:
                vision_hint = "NOTE: An image was previously uploaded and analyzed. If the user refers to 'it', 'this', 'the photo', or 'the image', they are talking about that visual content. DO NOT inject outside topics (like previous search results) into the rewritten question if the user is focused on the image."

            rewrite_prompt = f"""Given the conversation history: '{history}', rewrite the following user question to be completely self-contained. 
{vision_hint}

RULES:
1. If the new question is a different topic than the history, DO NOT merge them. Just fix pronouns.
2. Ensure the core entity (e.g. college name, person name) is explicitly mentioned.
3. If the user mentions 'it' or 'this' in a way that refers to an image, replace it with 'the uploaded image'.
4. If the user is stating a persistent PREFERENCE or INSTRUCTION for how the AI should behave (e.g. "always use bar charts", "write in Spanish", "keep answers short"), output it inside XML tags. Use <PREFERENCE_VISUALIZER> for chart/visual preferences, and <PREFERENCE_GENERATOR> for text/writing preferences. Example: <PREFERENCE_GENERATOR>Always use bullet points</PREFERENCE_GENERATOR>
5. CRITICAL: If the user's question is extremely brief, vague, or contains an ambiguous term/word (like 'apple', 'python', 'the project') and does NOT clearly build on the conversation history, PRESERVE the vagueness exactly. Do NOT invent or guess context, and do NOT rewrite it into a specific question.
6. If it's a normal query, return ONLY the rewritten question string.

New Question: '{query}'
Rewritten:"""
            search_query = self.generator.llm.invoke(rewrite_prompt, model_choice=model_choice).strip()
            
            # Check for preferences
            if "<PREFERENCE_" in search_query:
                vis_match = re.search(r'<PREFERENCE_VISUALIZER>(.*?)</PREFERENCE_VISUALIZER>', search_query, re.IGNORECASE | re.DOTALL)
                gen_match = re.search(r'<PREFERENCE_GENERATOR>(.*?)</PREFERENCE_GENERATOR>', search_query, re.IGNORECASE | re.DOTALL)
                
                if vis_match:
                    pref = vis_match.group(1).strip()
                    self.persona_memory.add_preference("Visualizer", pref, llm=self.generator.llm)
                    yield emit("Master LLM Orchestrator", "Completed", f"Updated Visualizer Persona: '{pref}'")
                if gen_match:
                    pref = gen_match.group(1).strip()
                    self.persona_memory.add_preference("Generator", pref, llm=self.generator.llm)
                    yield emit("Master LLM Orchestrator", "Completed", f"Updated Generator Persona: '{pref}'")
                
                clean_query = re.sub(r'<PREFERENCE_.*?>.*?</PREFERENCE_.*?>', '', search_query, flags=re.IGNORECASE | re.DOTALL).strip()
                if not clean_query:
                    yield emit("Final Response", "Completed", "Done", {
                        "answer": "I have updated my persona memory and will remember this preference for future interactions!",
                        "sources": []
                    })
                    return
                search_query = clean_query

            yield emit("Master LLM Orchestrator", "Completed", f"Contextualized query: {search_query}")
        else:
            yield emit("Master LLM Orchestrator", "Completed", "Delegating task to Agent Router")

        # 1.25 Image-Aware Routing
        # When an image is uploaded, check if the query is primarily about the image.
        # If so, bypass the KB/Web search and answer directly from the image analysis.
        
        # Update or reuse image context
        if image_context:
            self.last_image_context = image_context
        elif not image_context and self.last_image_context:
            # Check if this query refers to the previous image
            image_ref_keywords = ["this", "that", "the", "it", "photo", "image", "picture", "screenshot"]
            if any(kw in query.lower() for kw in image_ref_keywords):
                logger.info("Reusing previous image context for follow-up query.")
                image_context = self.last_image_context

        # Check cache (after resolving potential image context)
        cached_response = self.cache.get(query, history, image_context)
        if cached_response:
            yield emit("Cache Manager", "Completed", "Cache hit! Retrieved answer instantly.")
            yield emit("Final Response", "Completed", "Pipeline finished", cached_response)
            return

        if image_context:
            image_keywords = ["photo", "image", "picture", "screenshot", "uploaded", "this", "that", "it",
                              "describe", "written", "show", "see", "look", "what is", "what's",
                              "tell me", "analyze", "read", "content", "says", "text in",
                              "summarize", "explain", "extract", "info in", "detail"]
            
            # Check keywords in both original and rewritten queries to avoid context loss during rewriting
            query_lower = query.lower()
            search_query_lower = search_query.lower()
            
            is_image_centric = any(kw in query_lower for kw in image_keywords) or \
                               any(kw in search_query_lower for kw in image_keywords)
            
            logger.info(f"Image detection: is_image_centric={is_image_centric}, original='{query}', rewritten='{search_query}'")
            if image_context and len(image_context) < 50:
                logger.warning(f"Extremely short image context: '{image_context}'")

            if is_image_centric:
                yield emit("Image-Aware Router", "Processing", "Query is about the uploaded image — answering from visual analysis")
                logger.info("Routing to Image-Centric generation path.")

                # Generate answer directly from image context only
                yield emit("Generation", "Processing", "Synthesizing answer from image analysis data")
                answer_chunks = []
                async for chunk in self.generator.generate_answer_stream(
                    search_query,
                    [f"[Image Analysis]:\n{image_context}"],
                    sources=["Uploaded Image"],
                    mode="analytical",
                    model_choice=model_choice
                ):
                    answer_chunks.append(chunk)
                    yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
                answer = "".join(answer_chunks)
                yield emit("Generation", "Completed", "Answer generated from image analysis")

                # Run verification against the image context
                yield emit("Verification Module", "Processing", "Verifying answer against extracted image data...")
                is_valid, verify_reason = await self.verifier.verify(answer, [image_context], model_choice=model_choice)
                if is_valid:
                    yield emit("Verification Module", "Completed", f"Response passed factuality check: {verify_reason}")
                else:
                    yield emit("Verification Module", "Completed", f"Verification note: {verify_reason}")

                # Save to notebook
                self.notebook.save_entry(query, answer, ["Uploaded Image"])

                final_details = {
                    "answer": answer,
                    "sources": ["Uploaded Image"],
                    "source_map": {"1": "Uploaded Image"}
                }
                self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Pipeline finished", final_details)
                return
            else:
                # Image is supplementary — enrich the search query with visual data
                yield emit("Image-Aware Router", "Processing", "Image detected as supplementary context — enriching search query")
                logger.info("Routing to supplementary image context path.")
                # Take the first 500 chars of image analysis to augment the search
                image_summary = image_context[:500].replace("\n", " ")
                search_query = f"{search_query}. Visual context: {image_summary}"
                yield emit("Image-Aware Router", "Completed", "Search query enriched with image analysis data")

        # 1.5 Agent Routing
        yield emit("Agent Router", "Processing", "Classifying intent to select the optimal Tool...")
        tool = "Search_Knowledge_Base"
        try:
            from models.agentic_router import AgentRouter
            router = AgentRouter()
            tool = await asyncio.to_thread(router.route_query, search_query, model_choice)
            yield emit("Agent Router", "Completed", f"Selected Tool: [{tool}]")
        except Exception as e:
            logger.error(f"Agent Router exception: {e}")
            yield emit("Agent Router", "Completed", f"Fallback to Default Tool: [{tool}] (Error: {str(e)[:60]})")


        # ─── OUTBOUND ACTION branches (draft only — never sends) ──────────────
        # These are the only tools that can touch the outside world, so they are the
        # only place an injected instruction could do real damage. Two things contain
        # that. First, extraction reads the RAW `query` — the user's own words — and
        # never `search_query`, which by this point may carry text lifted from a crawled
        # page or an uploaded image. Second, the recipient must resolve to a saved
        # contact. Nothing here sends: it produces a draft for a human to approve.
        if tool in ("Send_Email", "Send_WhatsApp"):
            kind = "email" if tool == "Send_Email" else "whatsapp"
            client = self.gmail if kind == "email" else self.whatsapp
            label = "Email Agent" if kind == "email" else "WhatsApp Agent"

            if not client.available:
                reason = client._init_error or f"{kind} is not configured."
                self.actions.audit_blocked(reason, kind, {}, query)
                yield emit(label, "Completed", "Channel not configured")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I can't send that — {reason}",
                    "sources": [],
                })
                return

            yield emit(label, "Processing", f"Composing {kind} from your instruction (contacts allowlist enforced)")
            try:
                if kind == "email":
                    payload = await asyncio.to_thread(self.extractor.extract_email, query, model_choice)
                else:
                    payload = await asyncio.to_thread(self.extractor.extract_whatsapp, query, model_choice)
            except LookupError as e:
                # Recipient not on the allowlist. This is the defense doing its job, so
                # record it — a blocked send is exactly the evidence worth reporting.
                self.actions.audit_blocked(str(e), kind, {"raw_query": query}, query)
                yield emit(label, "Completed", "Blocked: recipient is not a saved contact")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": str(e),
                    "sources": [],
                })
                return
            except Exception as e:
                logger.error(f"Action extraction failed: {e}")
                yield emit(label, "Completed", f"Could not compose the {kind}")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I couldn't work out what to send. Try phrasing it like "
                              f"\"email Ali about the project deadline\". ({str(e)[:80]})",
                    "sources": [],
                })
                return

            draft = self.actions.create_draft(kind, payload, query)
            yield emit(label, "Completed", f"Draft ready for {payload['recipient_name']} — awaiting your approval")

            summary = (
                f"I've drafted this {'email' if kind == 'email' else 'WhatsApp message'} "
                f"to **{payload['recipient_name']}**. Nothing has been sent — review it "
                f"and press Approve to send, or Reject to discard."
            )
            yield emit("Final Response", "Completed", "Awaiting approval", {
                "answer": summary,
                "sources": [],
                "pending_action": draft,
            })
            return

        # ─── READ EMAIL branch (inbox as a retrieval source) ──────────────────
        if tool == "Read_Email":
            if not self.gmail.available:
                yield emit("Email Agent", "Completed", "Gmail not configured")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I can't read your inbox — {self.gmail._init_error}",
                    "sources": [],
                })
                return

            yield emit("Email Agent", "Processing", "Fetching recent mail from your inbox")
            try:
                gmail_query = "is:unread" if "unread" in query.lower() else ""
                emails = await asyncio.to_thread(self.gmail.list_recent, 10, gmail_query)
            except Exception as e:
                logger.error(f"Inbox fetch failed: {e}")
                yield emit("Email Agent", "Completed", f"Inbox fetch failed: {str(e)[:60]}")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I couldn't reach your inbox: {str(e)[:120]}",
                    "sources": [],
                })
                return

            if not emails:
                yield emit("Email Agent", "Completed", "No matching mail found")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": "I didn't find any matching emails in your inbox.",
                    "sources": [],
                })
                return

            # Email is untrusted input — anyone can mail you. Flag injection attempts so
            # they land in the audit trail rather than passing silently into the LLM.
            for e in emails:
                hits = scan_for_injection(f"{e['subject']} {e['body']}")
                if hits:
                    logger.warning(f"Injection-like content in email from {e['from']}: {hits}")
                    self.actions.audit_blocked(
                        f"Injection-like content in inbox mail: {hits}",
                        "read_email", {"from": e["from"], "subject": e["subject"]}, query,
                    )

            yield emit("Email Agent", "Completed", f"Retrieved {len(emails)} email(s)")

            ctx = [
                f"From: {e['from']}\nDate: {e['date']}\nSubject: {e['subject']}\n\n{e['body'][:1500]}"
                for e in emails
            ]
            sources = [f"{e['subject']} — {e['from']}" for e in emails]

            yield emit("Generation", "Processing", "Summarizing your inbox")
            chunks = []
            async for chunk in self.generator.generate_answer_stream(
                query, ctx, sources=sources, mode="analytical", model_choice=model_choice
            ):
                chunks.append(chunk)
                yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
            answer = "".join(chunks)
            yield emit("Generation", "Completed", "Inbox summarized")

            yield emit("Final Response", "Completed", "Done", {
                "answer": answer,
                "sources": sources,
                "source_map": {str(i + 1): s for i, s in enumerate(sources)},
            })
            return

        # ─── AMBIGUOUS QUERY branch (Human-in-the-Loop) ───────────────────────
        if tool == "Ambiguous_Query":
            yield emit("Agent Router", "Processing", "Query detected as highly ambiguous. Pausing pipeline to ask for clarification...")
            clarification_prompt = (
                f"The user's query '{search_query}' is highly ambiguous, too short, or lacks context. "
                f"Draft a very brief, polite response asking the user to clarify their intent. "
                f"If possible, provide 2 or 3 likely interpretations they might mean."
            )
            try:
                answer = await self.generator.generate_answer(clarification_prompt, mode="conversational", model_choice=model_choice)
            except Exception as e:
                logger.error(f"Clarification generation failed: {e}")
                answer = f"Your query '{search_query}' is a bit ambiguous. Could you please clarify what exactly you are looking for?"
            
            yield emit("Agent Router", "Completed", "Clarification requested from user")
            # We safely exit the pipeline and wait for the user to reply in the chat.
            yield emit("Final Response", "Completed", "Awaiting human input", {
                "answer": answer,
                "sources": []
            })
            return

        # ─── VISION ANALYSIS branch ───────────────────────────────────────────
        if tool == "Vision_Analysis":
            if image_context:
                yield emit("Vision Analysis", "Processing", "Analyzing query against visual content")
                answer_chunks = []
                async for chunk in self.generator.generate_answer_stream(
                    search_query,
                    [f"[Image Analysis]:\n{image_context}"],
                    sources=["Uploaded Image"],
                    mode="analytical",
                    model_choice=model_choice
                ):
                    answer_chunks.append(chunk)
                    yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
                answer = "".join(answer_chunks)
                yield emit("Vision Analysis", "Completed", "Answer generated from visual data")
                final_details = {
                    "answer": answer, 
                    "sources": ["Uploaded Image"],
                    "source_map": {"1": "Uploaded Image"}
                }
                self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Done", final_details)
                return
            else:
                yield emit("Vision Analysis", "Completed", "No image provided for visual analysis — falling back to Web Search")
                tool = "Web_Search"

        # ─── DIRECT CHAT branch ────────────────────────────────────────────
        if tool == "Direct_Chat":
            yield emit("Direct Chat", "Processing", "Engaging directly without retrieval")
            try:
                answer_chunks = []
                async for chunk in self.generator.generate_answer_stream(
                    search_query,
                    mode="conversational",
                    model_choice=model_choice
                ):
                    answer_chunks.append(chunk)
                    yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
                answer = "".join(answer_chunks)
                yield emit("Direct Chat", "Completed", "Answer generated")
                final_details = {"answer": answer, "sources": []}
                self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Done", final_details)
            except Exception as e:
                logger.error(f"Direct chat failed: {e}")
            return

        # ─── WEB SEARCH branch ────────────────────────────────────────────
        elif tool == "Web_Search":
            yield emit("Web Search", "Processing", f"Initiating multi-path research for: {search_query}")
            try:
                # ─── Multi-Query Generation ───
                # Generate variations to improve coverage
                expansion_prompt = f"Generate 3 diverse search queries to thoroughly answer this request: '{search_query}'. Return ONLY a JSON list of strings."
                try:
                    exp_raw = self.generator.llm.invoke(expansion_prompt, model_choice=model_choice).strip()
                    exp_json = re.sub(r'```json\s*|\s*```', '', exp_raw)
                    queries = json.loads(exp_json)
                    yield emit("Agent Router", "Completed", f"Expanded to {len(queries)} research paths")
                except:
                    logger.warning("Query expansion failed, using original query.")
                    queries = [search_query]
                
                # OPTIMIZATION: Perform searches in parallel using asyncio.gather for 3x speedup
                # This is Phase 1 optimization - executes all web searches simultaneously
                tasks = [search_web(q, max_results=3) for q in queries]
                search_results = await asyncio.gather(*tasks)
                
                all_docs = []
                all_sources = []
                for doc_texts, sources in search_results:
                    all_docs.extend(doc_texts)
                    all_sources.extend(sources)

                doc_texts = all_docs
                sources = all_sources

                if doc_texts:
                    yield emit("Web Search", "Completed", f"Retrieved {len(doc_texts)} live web results across all paths")
                else:
                    yield emit("Web Search", "Completed", "No web results found — falling back to Knowledge Base")
                    tool = "Search_Knowledge_Base"
            except Exception as e:
                logger.error(f"Web search failed: {e}")
                yield emit("Web Search", "Completed", f"Web search failed ({str(e)[:80]}) — falling back to Knowledge Base")
                tool = "Search_Knowledge_Base"

            # If web search succeeded, generate + verify + visualize then return
            if tool == "Web_Search":
                yield emit("Generation", "Processing", "Synthesizing answer using live web data")
                gen_context = doc_texts
                if image_context:
                    gen_context = [f"[Image Analysis]:\n{image_context}"] + doc_texts
                
                # Inject user-provided data if the query contains rich data points
                import re
                has_rich_data = False
                if any(char in query for char in ["$", "%", "="]) or any(kw in query.lower() for kw in ["is ", "are ", "value ", "ratio "]):
                    numbers = re.findall(r'\d+', query)
                    if len(numbers) >= 3:
                        has_rich_data = True
                if has_rich_data:
                    logger.info("Detected user-provided data in query. Injecting into generation context.")
                    gen_context = [f"[User Provided Data]:\n{query}"] + gen_context
                    if "User-provided Data" not in sources:
                        sources.append("User-provided Data")

                answer_chunks = []
                async for chunk in self.generator.generate_answer_stream(search_query, gen_context, sources=sources, mode="analytical", model_choice=model_choice):
                    answer_chunks.append(chunk)
                    yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
                answer = "".join(answer_chunks)
                yield emit("Generation", "Completed", "Answer drafted successfully")

                # Verification & Visualization with Self-Healing Loop
                max_retries = 0
                retry_count = 0
                is_valid = False
                chart_filename = None
                warning = None

                viz_context = gen_context
                if has_rich_data:
                    viz_context = [f"[User Provided Data]:\n{query}"]

                while retry_count <= max_retries and not is_valid:
                    yield emit("Verification & Visualization", "Processing", "Running fact-check and chart generation concurrently...")
                    
                    async def safe_visualize():
                        try:
                            return await self.visualizer.run(viz_context, answer, model_choice=model_choice)
                        except Exception as e:
                            logger.error(f"Visualizer failed: {e}")
                            return None
                            
                    verify_task = asyncio.create_task(self.verifier.verify(answer, gen_context, model_choice=model_choice))
                    visualize_task = asyncio.create_task(safe_visualize())
                    
                    is_valid_data, current_chart_filename = await asyncio.gather(verify_task, visualize_task)
                    is_valid, verify_reason = is_valid_data
                    
                    if is_valid:
                        yield emit("Verification Module", "Completed", f"Response passed factuality check: {verify_reason}")
                        chart_filename = current_chart_filename
                        if chart_filename:
                            yield emit("Visualizer Agent", "Completed", "Data chart generated successfully", {"chart": f"/uploads/{chart_filename}"})
                        else:
                            yield emit("Visualizer Agent", "Completed", "No significant numerical data found for charting.")
                        break
                    else:
                        yield emit("Verification Module", "Completed", f"Verification flagged potential inaccuracies: {verify_reason}")
                        if retry_count < max_retries:
                            yield emit("Self-Healing", "Processing", f"Hallucination detected. Regenerating response strictly from context (Attempt {retry_count + 1})...")
                            strict_query = search_query + "\n\nCRITICAL INSTRUCTION: The previous answer contained hallucinations. You must regenerate the answer and adhere STRICTLY to the provided context only."
                            answer = await self.generator.generate_answer(strict_query, gen_context, sources=sources, mode="analytical", model_choice=model_choice)
                            retry_count += 1
                        else:
                            warning = "The AI may not have found all details in the retrieved web sources. Treat specific figures as approximate."
                            chart_filename = current_chart_filename
                            break

                # Build source map for inline citations
                source_map = {str(i+1): src for i, src in enumerate(sources)}
                final_details = {"answer": answer, "sources": sources, "source_map": source_map}
                if chart_filename:
                    final_details["chart"] = f"/uploads/{chart_filename}"
                if warning:
                    final_details["warning"] = warning

                # Save metadata to the analytical notebook
                self.notebook.save_entry(query, answer, sources)

                self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Pipeline finished", final_details)
                return

        # ─── KNOWLEDGE BASE branch ───────────────────────────────────────
        yield emit("Embedding Model", "Processing", "Converting query into dense vector representation")
        yield emit("Embedding Model", "Completed", "Vector embedding generated successfully")

        yield emit("Vector Retrieval", "Processing", "Searching FAISS vector database for nearest neighbors")
        docs = self.vector_db.retrieve(search_query, top_k=10)
        doc_texts = [d.page_content for d in docs]
        sources = [d.metadata.get("source", "Unknown") for d in docs]
        
        if not doc_texts:
            yield emit("Vector Retrieval", "Completed", "No relevant context found in the local knowledge base.")
            yield emit("Final Response", "Completed", "Done", {
                "answer": "I couldn't find relevant information in the knowledge base. Try uploading a document or enabling Web Search.",
                "sources": []
            })
            return

        yield emit("Vector Retrieval", "Completed", f"Retrieved {len(docs)} relevant chunks from database")

        yield emit("Reranking Model", "Processing", "Cross-encoding query and documents to filter relevance")
        ranked_docs = self.reranker.rerank(search_query, doc_texts, top_k=5)
        yield emit("Reranking Model", "Completed", f"Filtered down to top {len(ranked_docs)} most relevant contexts")

        yield emit("Generation", "Processing", "Synthesizing answer using LLM and retrieved context")
        gen_context = ranked_docs
        if image_context:
            gen_context = [f"[Image Analysis]:\n{image_context}"] + ranked_docs
            
        # Inject user-provided data if the query contains rich data points
        import re
        has_rich_data = False
        if any(char in query for char in ["$", "%", "="]) or any(kw in query.lower() for kw in ["is ", "are ", "value ", "ratio "]):
            numbers = re.findall(r'\d+', query)
            if len(numbers) >= 3:
                has_rich_data = True
        if has_rich_data:
            logger.info("Detected user-provided data in query. Injecting into generation context.")
            gen_context = [f"[User Provided Data]:\n{query}"] + gen_context
            if "User-provided Data" not in sources:
                sources.append("User-provided Data")

        answer_chunks = []
        async for chunk in self.generator.generate_answer_stream(search_query, gen_context, sources=list(set(sources)), mode="analytical", model_choice=model_choice):
            answer_chunks.append(chunk)
            yield emit("Final Response", "Processing", "Streaming", {"answer_chunk": chunk})
        answer = "".join(answer_chunks)
        yield emit("Generation", "Completed", "Answer drafted successfully")

        # Verification & Visualization with Self-Healing Loop
        max_retries = 0
        retry_count = 0
        is_valid = False
        chart_filename = None
        warning = None

        viz_context = gen_context
        if has_rich_data:
            viz_context = [f"[User Provided Data]:\n{query}"]

        while retry_count <= max_retries and not is_valid:
            yield emit("Verification & Visualization", "Processing", "Running fact-check and chart generation concurrently...")
            
            async def safe_visualize():
                try:
                    return await self.visualizer.run(viz_context, answer, model_choice=model_choice)
                except Exception as e:
                    logger.error(f"Visualizer failed: {e}")
                    return None
                    
            verify_task = asyncio.create_task(self.verifier.verify(answer, gen_context, model_choice=model_choice))
            visualize_task = asyncio.create_task(safe_visualize())
            
            is_valid_data, current_chart_filename = await asyncio.gather(verify_task, visualize_task)
            is_valid, verify_reason = is_valid_data
            
            if is_valid:
                yield emit("Verification Module", "Completed", f"Response passed factuality check: {verify_reason}")
                chart_filename = current_chart_filename
                if chart_filename:
                    yield emit("Visualizer Agent", "Completed", "Data chart generated successfully", {"chart": f"/uploads/{chart_filename}"})
                else:
                    yield emit("Visualizer Agent", "Completed", "No significant numerical data found for charting.")
                break
            else:
                yield emit("Verification Module", "Completed", f"Verification flagged potential inaccuracies: {verify_reason}")
                if retry_count < max_retries:
                    yield emit("Self-Healing", "Processing", f"Hallucination detected. Regenerating response strictly from context (Attempt {retry_count + 1})...")
                    strict_query = search_query + "\n\nCRITICAL INSTRUCTION: The previous answer contained hallucinations. You must regenerate the answer and adhere STRICTLY to the provided context only."
                    answer = await self.generator.generate_answer(strict_query, gen_context, sources=list(set(sources)), mode="analytical", model_choice=model_choice)
                    retry_count += 1
                else:
                    warning = "The AI's answer may contain information not fully supported by the retrieved source documents despite self-healing attempts."
                    chart_filename = current_chart_filename
                    break

        # Final Response
        unique_sources = list(set(sources))
        source_map = {str(i+1): src for i, src in enumerate(unique_sources)}
        final_details = {"answer": answer, "sources": unique_sources, "source_map": source_map}
        if chart_filename:
            final_details["chart"] = f"/uploads/{chart_filename}"
        if warning:
            final_details["warning"] = warning
            
        # Save metadata to the analytical notebook
        self.notebook.save_entry(query, answer, list(set(sources)))
            
        self.cache.set(query, history, image_context, final_details)
        yield emit("Final Response", "Completed", "Pipeline finished", final_details)
