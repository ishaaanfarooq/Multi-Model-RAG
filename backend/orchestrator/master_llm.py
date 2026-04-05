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

logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """
    Coordinates the multi-model RAG workflow.
    Publishes status events directly formatted for SSE.
    """
    def __init__(self):
        self.vector_db = VectorDatabase()
        self.reranker = RerankerModel()
        self.generator = GenerationModel()
        self.verifier = VerificationModule()
        self.visualizer = VisualizerAgent()
        self.notebook = NotebookMemory()
        self.last_image_context = "" # Persist last analyzed image context
        
    async def process_query_stream(self, query: str, history: str = "", image_context: str = "") -> AsyncGenerator[str, None]:
        """
        Executes the entire RAG pipeline and yields SSE JSON strings at each step.
        """
        def emit(model, status, action, details=None):
            data = {"model": model, "status": status, "action": action}
            if details:
                data["details"] = details
            return json.dumps(data)

        # 1. Start pipeline
        yield emit("Master LLM Orchestrator", "Processing", "Analyzing user intent and planning execution")
        
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
4. Return ONLY the rewritten question string.

New Question: '{query}'
Rewritten:"""
            search_query = self.generator.llm.invoke(rewrite_prompt).strip()
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
                answer = await self.generator.generate_answer(
                    search_query,
                    [f"[Image Analysis]:\n{image_context}"],
                    sources=["Uploaded Image"],
                    mode="analytical"
                )
                yield emit("Generation", "Completed", "Answer generated from image analysis")

                # Run verification against the image context
                yield emit("Verification Module", "Processing", "Verifying answer against extracted image data...")
                is_valid, verify_reason = await self.verifier.verify(answer, [image_context])
                if is_valid:
                    yield emit("Verification Module", "Completed", f"Response passed factuality check: {verify_reason}")
                else:
                    yield emit("Verification Module", "Completed", f"Verification note: {verify_reason}")

                # Save to notebook
                self.notebook.save_entry(query, answer, ["Uploaded Image"])

                yield emit("Final Response", "Completed", "Pipeline finished", {
                    "answer": answer,
                    "sources": ["Uploaded Image"],
                    "source_map": {"1": "Uploaded Image"}
                })
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
            router = AgentRouter(model_name="llama3.2")
            tool = await asyncio.to_thread(router.route_query, search_query)
            yield emit("Agent Router", "Completed", f"Selected Tool: [{tool}]")
        except Exception as e:
            logger.error(f"Agent Router exception: {e}")
            yield emit("Agent Router", "Completed", f"Fallback to Default Tool: [{tool}] (Error: {str(e)[:60]})")


        # ─── AMBIGUOUS QUERY branch (Human-in-the-Loop) ───────────────────────
        if tool == "Ambiguous_Query":
            yield emit("Agent Router", "Processing", "Query detected as highly ambiguous. Pausing pipeline to ask for clarification...")
            clarification_prompt = (
                f"The user's query '{search_query}' is highly ambiguous, too short, or lacks context. "
                f"Draft a very brief, polite response asking the user to clarify their intent. "
                f"If possible, provide 2 or 3 likely interpretations they might mean."
            )
            try:
                answer = await self.generator.generate_answer(clarification_prompt, mode="conversational")
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
                answer = await self.generator.generate_answer(
                    search_query,
                    [f"[Image Analysis]:\n{image_context}"],
                    sources=["Uploaded Image"],
                    mode="analytical"
                )
                yield emit("Vision Analysis", "Completed", "Answer generated from visual data")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": answer, 
                    "sources": ["Uploaded Image"],
                    "source_map": {"1": "Uploaded Image"}
                })
                return
            else:
                yield emit("Vision Analysis", "Completed", "No image provided for visual analysis — falling back to Web Search")
                tool = "Web_Search"

        # ─── DIRECT CHAT branch ────────────────────────────────────────────
        if tool == "Direct_Chat":
            yield emit("Direct Chat", "Processing", "Engaging directly without retrieval")
            try:
                answer = await self.generator.generate_answer(
                    search_query,
                    mode="conversational"
                )
                yield emit("Direct Chat", "Completed", "Answer generated")
                yield emit("Final Response", "Completed", "Done", {"answer": answer, "sources": []})
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
                    exp_raw = self.generator.llm.invoke(expansion_prompt).strip()
                    exp_json = re.sub(r'```json\s*|\s*```', '', exp_raw)
                    queries = json.loads(exp_json)
                    yield emit("Agent Router", "Completed", f"Expanded to {len(queries)} research paths")
                except:
                    logger.warning("Query expansion failed, using original query.")
                    queries = [search_query]
                
                # Perform searches in parallel if possible, but sequential is safer for rate limits
                all_docs = []
                all_sources = []
                for q in queries:
                    doc_texts, sources = await search_web(q, max_results=3)
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
                answer = await self.generator.generate_answer(search_query, gen_context, sources=sources, mode="analytical")
                yield emit("Generation", "Completed", "Answer drafted successfully")

                # Verification & Visualization with Self-Healing Loop
                max_retries = 1
                retry_count = 0
                is_valid = False
                chart_filename = None
                warning = None

                while retry_count <= max_retries and not is_valid:
                    yield emit("Verification & Visualization", "Processing", "Running fact-check and chart generation concurrently...")
                    
                    async def safe_visualize():
                        try:
                            return await self.visualizer.run(doc_texts, answer)
                        except Exception as e:
                            logger.error(f"Visualizer failed: {e}")
                            return None
                            
                    verify_task = asyncio.create_task(self.verifier.verify(answer, doc_texts))
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
                            strict_query = search_query + "\n\nCRITICAL INSTRUCTION: The previous answer contained hallucinations. You must regenerate the answer and adhere STRICTLY to the provided context. DO NOT include outside information."
                            answer = await self.generator.generate_answer(strict_query, gen_context, sources=sources, mode="analytical")
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
        answer = await self.generator.generate_answer(search_query, gen_context, sources=list(set(sources)), mode="analytical")
        yield emit("Generation", "Completed", "Answer drafted successfully")

        # Verification & Visualization with Self-Healing Loop
        max_retries = 1
        retry_count = 0
        is_valid = False
        chart_filename = None
        warning = None

        while retry_count <= max_retries and not is_valid:
            yield emit("Verification & Visualization", "Processing", "Running fact-check and chart generation concurrently...")
            
            async def safe_visualize():
                try:
                    return await self.visualizer.run(ranked_docs, answer)
                except Exception as e:
                    logger.error(f"Visualizer failed: {e}")
                    return None
                    
            verify_task = asyncio.create_task(self.verifier.verify(answer, ranked_docs))
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
                    strict_query = search_query + "\n\nCRITICAL INSTRUCTION: The previous answer contained hallucinations. You must regenerate the answer and adhere STRICTLY to the provided context. DO NOT include outside information."
                    answer = await self.generator.generate_answer(strict_query, gen_context, sources=list(set(sources)), mode="analytical")
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
            
        yield emit("Final Response", "Completed", "Pipeline finished", final_details)
