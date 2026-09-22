import asyncio
import os
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
from retrieval.web_search import search_web, parse_query_list, build_search_queries, merge_search_results, series_from_context, search_is_degraded, period_queries
from core.memory_manager import NotebookMemory
from core.persona_memory import AgentPersonaMemory
from utils.cache import ResponseCache
from actions.contacts import ContactsStore
from actions.registry import ActionRegistry
from actions.extractor import ActionExtractor, scan_for_injection
from actions.gmail_client import GmailClient
from actions.whatsapp_client import WhatsAppClient
from actions.telegram_client import TelegramClient
from actions.workspace import WorkspaceAgent, resolve_existing_target
from core.conversation_state import ConversationStore
from core.request_trace import RequestTrace, TraceLog
from retrieval.reranker import KB_ANSWER_MIN_SCORE, below_answer_floor
from verification.verifier import warning_for

logger = logging.getLogger(__name__)

_CLARIFY_RE = re.compile(
    r"(would you like|could you (?:please )?(?:provide|clarify|specify)|can you (?:please )?(?:provide|clarify|specify)"
    r"|please (?:provide|specify|clarify)|let me know|additional details|more context|if available)",
    re.I,
)


_IMAGE_NOUN_RE = re.compile(
    r"\b(image|images|photo|photos|picture|pictures|screenshot|screenshots|pic|pics)\b"
    r"|\bthe (upload|attachment)\b|\battached (image|photo|picture|screenshot|file)\b",
    re.I,
)
_PRONOUN_FOLLOWUP_RE = re.compile(r"\b(it|this|that|these|those)\b", re.I)
IMAGE_CONTEXT_TTL_S = 600.0


def refers_to_previous_image(query: str, max_pronoun_words: int = 6) -> bool:
    """
    Does a query that carries no new image refer back to the last uploaded one?
    Only an explicit visual noun, or a short pronoun-only follow-up ("what's in
    it?", "describe this"), counts. The previous substring check on "the"/"it"
    matched "there" and "with", so after any upload every later query — greetings,
    knowledge-base questions — was answered from the stale image and never reached
    the router. "chart" and "uploaded" deliberately do not count: "chart X by
    quarter" and "my uploaded documents" are not about a picture.
    """
    q = (query or "").strip()
    if not q:
        return False
    if _IMAGE_NOUN_RE.search(q):
        return True
    return len(q.split()) <= max_pronoun_words and bool(_PRONOUN_FOLLOWUP_RE.search(q))


def looks_like_clarification(rewritten: str, original: str) -> bool:
    """
    The history-rewriter is asked to restate the user's question self-contained.
    A small model sometimes *answers* instead — "What chart would you like to see
    of Samsung's revenue?" — and that text then drives routing, search and the
    "Contextualized query" shown in the UI. Detect it so the original words are used.
    """
    r = (rewritten or "").strip()
    if not r:
        return True
    if _CLARIFY_RE.search(r):
        return True
    o = (original or "").strip()
    if r.endswith("?") and not o.endswith("?") and r.lower().startswith(("what ", "which ", "could ", "would ", "can ", "do you", "are you")):
        return True
    return False


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
        # Per-conversation state (last uploaded image, ...). See core/conversation_state.py.
        self.conversations = ConversationStore()
        self.trace_log = TraceLog()   # per-request timings, see core/request_trace.py

        # Outbound actions (email / WhatsApp). These are the only parts of the system
        # that can affect the outside world, so they never fire on their own: the agent
        # drafts, a human approves, and only then does anything get sent.
        self.contacts = ContactsStore()
        self.actions = ActionRegistry()
        self.extractor = ActionExtractor(self.generator.llm, self.contacts)
        self.gmail = GmailClient()
        self.whatsapp = WhatsAppClient()
        self.telegram = TelegramClient()
        self.workspace = WorkspaceAgent()

    def kb_relevance(self, query: str) -> float | None:
        """Best cross-encoder score among the knowledge base's fused top-3 for `query`,
        or None if the base is empty / the reranker is unavailable. ~0.3-0.5 s on CPU,
        cheaper than the classifier call it replaces on a hit."""
        try:
            docs = self.vector_db.hybrid_retrieve(query, top_k=3)
            texts = [d.page_content for d in docs if d.page_content and d.page_content.strip()]
            if not texts or not getattr(self.reranker, "model", None):
                return None
            scores = self.reranker.model.predict([(query, t) for t in texts])
            return float(max(scores))
        except Exception as e:
            logger.warning(f"kb_relevance failed: {e}")
            return None

    async def process_query_stream(self, query: str, history: str = "", image_context: str = "", model_choice: str = "auto",
                                   conversation_id: str | None = None) -> AsyncGenerator[str, None]:
        """
        Executes the entire RAG pipeline and yields SSE JSON strings at each step.
        """
        trace = RequestTrace(query, conversation_id, model_choice)

        def emit(model, status, action, details=None):
            data = {"model": model, "status": status, "action": action}
            if details:
                data["details"] = details
            # Tracing rides on the events the pipeline already narrates: every event
            # carries elapsed ms, a Completed event carries its stage's duration, and
            # the final response carries the whole request's summary.
            data["t_ms"] = trace.record(data)
            if status == "Completed" and trace.stages and trace.stages[-1]["model"] == model:
                data["ms"] = trace.stages[-1]["ms"]
            if model == "Final Response" and status == "Completed":
                summary = trace.summary()
                data.setdefault("details", {})["trace"] = summary
                self.trace_log.append(summary)
                logger.info("TRACE " + json.dumps({k: summary[k] for k in
                            ("request_id", "conversation_id", "tool", "total_ms", "cache_hit", "search_degraded", "chart", "verification", "ms_by_model")}))
            return json.dumps(data)

        # 1. Start pipeline
        active_model = self.generator.llm.get_active_model_name(model_choice)
        yield emit("Master LLM Orchestrator", "Processing", f"Analyzing user intent via {active_model}")
        
        search_query = query
        state = self.conversations.get(conversation_id)
        if history:
            vision_hint = ""
            if state.last_image_context:
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

            if looks_like_clarification(search_query, query):
                logger.info(f"Rewriter returned a clarification instead of a rewrite; using the original query. Got: {search_query[:90]!r}")
                search_query = query

            yield emit("Master LLM Orchestrator", "Completed", f"Contextualized query: {search_query}")
        else:
            yield emit("Master LLM Orchestrator", "Completed", "Delegating task to Agent Router")

        # 1.25 Image-Aware Routing
        # When an image is uploaded, check if the query is primarily about the image.
        # If so, bypass the KB/Web search and answer directly from the image analysis.
        
        # Update or reuse image context. Reuse only for an explicit follow-up about the
        # picture, and only for a while: a stale image must not hijack the next
        # unrelated question (see refers_to_previous_image).
        if image_context:
            state.set_image(image_context)
        elif state.last_image_context:
            if state.image_age_s() > IMAGE_CONTEXT_TTL_S:
                logger.info(f"[{state.conversation_id}] previous image context expired; dropping it.")
                state.clear_image()
            elif refers_to_previous_image(query):
                logger.info(f"[{state.conversation_id}] reusing previous image context for follow-up query.")
                image_context = state.last_image_context

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
            router = AgentRouter(kb_probe=self.kb_relevance)
            # Pass the RAW user words too: the deterministic fast-path keys off the user's
            # literal request ("make a folder ... rng.py"), never the history-rewritten
            # query, so a file task can't be biased into a message by prior chat context.
            tool = await asyncio.to_thread(router.route_query, search_query, model_choice, query)
            if getattr(router, "last_probe_score", None) is not None and tool == "Search_Knowledge_Base":
                yield emit("Agent Router", "Completed", f"Knowledge base holds a strong match (relevance {router.last_probe_score:.1f}) — answering from your documents")
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
        if tool in ("Send_Email", "Send_WhatsApp", "Send_Telegram"):
            channel = {
                "Send_Email": ("email", self.gmail, "Email Agent", self.extractor.extract_email),
                "Send_WhatsApp": ("whatsapp", self.whatsapp, "WhatsApp Agent", self.extractor.extract_whatsapp),
                "Send_Telegram": ("telegram", self.telegram, "Telegram Agent", self.extractor.extract_telegram),
            }
            kind, client, label, extract = channel[tool]

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
                payload = await asyncio.to_thread(extract, query, model_choice)
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

            channel_label = {"email": "email", "whatsapp": "WhatsApp message", "telegram": "Telegram message"}[kind]
            summary = (
                f"I've drafted this {channel_label} to **{payload['recipient_name']}**. "
                f"Nothing has been sent — review it and press Approve to send, or Reject to discard."
            )
            yield emit("Final Response", "Completed", "Awaiting approval", {
                "answer": summary,
                "sources": [],
                "pending_action": draft,
            })
            return

        # ─── WORKSPACE FILE branch (draft only — never writes) ────────────────
        # Highest-privilege action: it writes a real file. Same containment as messaging —
        # extraction reads the RAW `query` (never retrieved documents), the WorkspaceAgent
        # confines every path to praxis-workspace/, and nothing hits disk without approval.
        if tool == "Workspace_Task":
            label = "Workspace Agent"
            if not self.workspace.available:
                self.actions.audit_blocked(self.workspace._init_error, "file", {}, query)
                yield emit(label, "Completed", "Workspace not available")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I can't write files right now — {self.workspace._init_error}",
                    "sources": [],
                })
                return

            # Prefer Claude for code generation when it's configured; otherwise use the
            # model the user picked (Qwen works, just weaker at coding).
            coding_choice = "claude" if self.generator.llm.claude_client else model_choice
            yield emit(label, "Processing", f"Writing the file with {self.generator.llm.get_active_model_name(coding_choice)} (confined to praxis-workspace/)")
            try:
                # Show the model what is already in the workspace, so "the txt folder"
                # resolves to the real txt/name.txt instead of a newly invented
                # txt/names.txt sitting beside it.
                existing_files = await asyncio.to_thread(self.workspace.list_files)
                payload = await asyncio.to_thread(
                    self.extractor.extract_file_task, query, coding_choice, existing_files
                )
                # Validate the path stays inside the workspace up-front, so a bad path is
                # caught now rather than at approval time.
                payload["path"] = self.workspace.rel(self.workspace._safe_path(payload["path"]))
                # The model names files unreliably; if the user is clearly editing, map
                # its guess onto the file that actually exists (name.txt vs names.txt).
                payload["path"] = resolve_existing_target(payload["path"], existing_files, query)

                # If the file already exists, this is an EDIT: re-run against its current
                # contents so an instruction like "remove the old names" actually removes
                # them, instead of overwriting the file with freshly invented content.
                if self.workspace.exists(payload["path"]):
                    current = await asyncio.to_thread(self.workspace.read_file, payload["path"])
                    yield emit(label, "Processing", f"{payload['path']} exists — editing it rather than replacing it")
                    payload["content"] = await asyncio.to_thread(
                        self.extractor.revise_file_content, query, payload["path"], current, coding_choice
                    )
                    payload["mode"] = "edit"
                    payload["previous_content"] = current
                else:
                    payload["mode"] = "create"
            except ValueError as e:
                self.actions.audit_blocked(str(e), "file", {"raw_query": query}, query)
                yield emit(label, "Completed", "Blocked: path escapes the workspace")
                yield emit("Final Response", "Completed", "Done", {"answer": str(e), "sources": []})
                return
            except Exception as e:
                logger.error(f"Workspace extraction failed: {e}")
                yield emit(label, "Completed", "Could not produce the file")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": f"I couldn't work out the file to create. Try e.g. "
                              f"\"write a python script that reverses a string, save as reverse.py\". ({str(e)[:80]})",
                    "sources": [],
                })
                return

            draft = self.actions.create_draft("file", payload, query)
            is_edit = payload.get("mode") == "edit"
            verb = "Edited" if is_edit else "Draft ready"
            yield emit(label, "Completed", f"{verb}: {payload['path']} — awaiting your approval")
            yield emit("Final Response", "Completed", "Awaiting approval", {
                "answer": (f"I've drafted an edit to **{payload['path']}**, replacing its current contents. "
                           if is_edit else
                           f"I've drafted **{payload['path']}**. ")
                          + "Nothing has been written yet — "
                          f"review it and press Approve to save it to your workspace, or Reject to discard.",
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
        # ─── VISUALIZE DATA branch (chart the numbers in the user's message) ──
        # "make a bar chart: Jan 100, Feb 75, ..." — the data is already in the query, so
        # there is no retrieval and nothing is invented. We lay the data out cleanly, then
        # render a chart from the user's OWN message. This is deliberately separate from
        # Workspace_Task (which saves a .py file to disk) and from Web_Search (which is for
        # figures that must be looked up first).
        if tool == "Visualize_Data":
            # Guard against the weak router's mistakes deterministically: if the message
            # has no numbers to plot, the user must want data we don't have yet (e.g.
            # "chart Samsung's revenue"). Hand off to Web_Search to FIND it first, rather
            # than asking them for figures they expect us to look up. (Two+ numbers = data
            # in the message; a lone year like "2025" is not enough.)
            data_numbers = re.findall(r"\d[\d,\.]*", query)
            if len(data_numbers) < 2:
                yield emit("Agent Router", "Completed", "No figures in the message — searching the web for the data first")
                tool = "Web_Search"

        if tool == "Visualize_Data":
            yield emit("Visualizer Agent", "Processing", "Reading the data from your message")
            try:
                # Two-step, robust with a small local model: (1) the LLM only EXTRACTS the
                # numbers as JSON — a task Qwen handles well — and (2) we render the chart
                # with a fixed, correct matplotlib template. This is why the chart shows the
                # user's real figures and never a hallucinated placeholder or a code crash.
                data = await asyncio.to_thread(self.visualizer.extract_data_points, query, model_choice)
                points, title, kind = data["points"], data["title"], data["kind"]

                yield emit("Verification & Visualization", "Processing",
                           f"Rendering a {kind} chart of {len(points)} data points")
                chart_filename = await asyncio.to_thread(
                    self.visualizer.render_data_chart, points, title, kind
                )

                # Build the chat answer from the SAME parsed data, so the text and the chart
                # can never disagree and nothing is invented downstream.
                table = "| Label | Value |\n|---|---|\n" + "\n".join(f"| {l} | {v:g} |" for l, v in points)
                answer = f"Here's a {kind} chart of **{title}** from the data you gave:\n\n{table}"

                final_details = {
                    "answer": answer,
                    "sources": ["User-provided Data"],
                    "chart": f"/uploads/{chart_filename}",
                }
                yield emit("Visualizer Agent", "Completed", "Data chart generated successfully",
                           {"chart": f"/uploads/{chart_filename}"})
                self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Pipeline finished", final_details)
            except Exception as e:
                logger.error(f"Visualize_Data failed: {e}")
                yield emit("Visualizer Agent", "Completed", "Couldn't build a chart from that")
                yield emit("Final Response", "Completed", "Done", {
                    "answer": ("I couldn't pull clear numbers to chart from that. Try giving explicit "
                               "label/value pairs, e.g. \"bar chart: Jan 100, Feb 75, Mar 50\"."),
                    "sources": [],
                })
            return

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
                expansions = []
                if period_queries(query):
                    # A series request already gets one deterministic search per period;
                    # the model's generic expansions add a call and no coverage.
                    logger.info("Series request: skipping LLM query expansion (per-period queries cover it).")
                else:
                    expansion_prompt = f"Generate 3 diverse search queries to thoroughly answer this request: '{search_query}'. Return ONLY a JSON list of strings."
                    try:
                        exp_raw = self.generator.llm.invoke(expansion_prompt, model_choice=model_choice).strip()
                        expansions = parse_query_list(exp_raw)
                    except Exception as e:
                        logger.warning(f"Query expansion failed ({e}); using the base queries only.")

                # The user's literal words are always searched first (see build_search_queries):
                # the history-rewrite can turn a request into a question aimed at the user,
                # which every engine answers with nothing. The rewritten form runs second so
                # follow-ups keep their context.
                queries = build_search_queries(query, search_query, expansions)
                yield emit("Agent Router", "Completed", f"Expanded to {len(queries)} research paths")
                
                # OPTIMIZATION: Perform searches in parallel using asyncio.gather for 3x speedup
                # This is Phase 1 optimization - executes all web searches simultaneously
                tasks = [search_web(q, max_results=3) for q in queries]
                search_results = await asyncio.gather(*tasks)
                
                # De-duplicate across the parallel searches (the same page surfaces for
                # every query variant) and cap the total so it fits the model's context
                # window rather than being truncated from the front by the runtime.
                doc_texts, sources = merge_search_results(search_results)

                # If the primary engine rate-limited us mid-request, what follows is
                # headlines and encyclopedia entries, not a web search. Say so, and
                # do not let it be cached as if it were the real answer.
                search_degraded = search_is_degraded()
                if search_degraded:
                    yield emit("Web Search", "Completed",
                               "Primary search engine is rate-limiting this address — results below are from fallback sources (news headlines, Wikipedia)")

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

                # A "by quarter / by half" request: take the series straight from the
                # annotated source tables and draw it with the fixed renderer. The local
                # model cannot be trusted to transcribe multi-source financial tables
                # (it hands full-year totals to quarters), so the chart's numbers must
                # come from the filings, not from the prose.
                series = series_from_context(doc_texts, query)
                if series:
                    yield emit("Visualizer Agent", "Completed", f"Series taken from source tables: {len(series['points'])} periods")

                while retry_count <= max_retries and not is_valid:
                    yield emit("Verification & Visualization", "Processing", "Running fact-check and chart generation concurrently...")
                    
                    async def safe_visualize():
                        try:
                            if series:
                                return await asyncio.to_thread(
                                    self.visualizer.render_data_chart, series["points"], series["title"], series["kind"]
                                )
                            return await self.visualizer.run(viz_context, answer, model_choice=model_choice)
                        except Exception as e:
                            logger.error(f"Visualizer failed: {e}")
                            return None
                            
                    verify_task = asyncio.create_task(self.verifier.verify_fast(answer, gen_context, model_choice=model_choice))
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
                            strict_query = search_query + f"\n\nCRITICAL INSTRUCTION: The previous answer failed verification: {verify_reason} Regenerate the answer and adhere STRICTLY to the provided context only; do not state anything the context does not contain."
                            answer = await self.generator.generate_answer(strict_query, gen_context, sources=sources, mode="analytical", model_choice=model_choice)
                            retry_count += 1
                        else:
                            warning = warning_for(verify_reason, fallback="The AI may not have found all details in the retrieved web sources. Treat specific figures as approximate.")
                            chart_filename = current_chart_filename
                            break

                if search_degraded:
                    warning = ("Live web search was rate-limited during this request, so this answer was built from "
                               "news headlines and Wikipedia only. Retry in a while for a full search.")

                # The chart above is drawn from the filings; make the prose carry the same
                # figures so a reader never has to reconcile the two.
                if series:
                    answer = answer.rstrip() + "\n\n**Figures from the source tables**\n\n" + series["table"]

                # Build source map for inline citations
                source_map = {str(i+1): src for i, src in enumerate(sources)}
                final_details = {"answer": answer, "sources": sources, "source_map": source_map}
                if chart_filename:
                    final_details["chart"] = f"/uploads/{chart_filename}"
                if warning:
                    final_details["warning"] = warning

                # Save metadata to the analytical notebook
                self.notebook.save_entry(query, answer, sources)

                # Cache only what deserves to be served again for an hour: a full search
                # (not the fallback tier) whose answer passed the factuality check.
                if not search_degraded and is_valid:
                    self.cache.set(query, history, image_context, final_details)
                yield emit("Final Response", "Completed", "Pipeline finished", final_details)
                return

        # ─── KNOWLEDGE BASE branch ───────────────────────────────────────
        yield emit("Embedding Model", "Processing", "Converting query into dense vector representation")
        yield emit("Embedding Model", "Completed", "Vector embedding generated successfully")

        yield emit("Vector Retrieval", "Processing", "Searching FAISS vector database for nearest neighbors")
        # Hybrid (dense + BM25, rank-fused) unless HYBRID_RETRIEVAL=0. Measured on the
        # eval set: dense-only top-5 hit 50/64, hybrid candidates cover 62/64.
        if os.getenv("HYBRID_RETRIEVAL", "1").lower() not in ("0", "false", "no"):
            docs = self.vector_db.hybrid_retrieve(search_query, top_k=10)
        else:
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
        scored_docs = await asyncio.to_thread(self.reranker.rerank_with_scores, search_query, doc_texts, top_k=5)
        ranked_docs = [doc for _, doc in scored_docs]
        best_score = scored_docs[0][0] if scored_docs else None

        # Answer floor: if even the best passage is not about the question, decline. Without
        # this the model answers from its own memory and cites [1] for a source that says
        # nothing of the kind (measured: "boiling point of ethanol" -> "78.4 C [1]").
        # Skipped when the question carries its own material (an image, or inline data).
        carries_own_material = bool(image_context) or (len(re.findall(r'\d+', query)) >= 3)
        if below_answer_floor(best_score) and not carries_own_material:
            logger.info(f"KB answer floor: best passage {best_score:.2f} < {KB_ANSWER_MIN_SCORE:.1f}; declining without generation.")
            yield emit("Reranking Model", "Completed", f"No passage is relevant enough (best {best_score:.1f}, floor {KB_ANSWER_MIN_SCORE:.1f}) — declining rather than guessing")
            yield emit("Final Response", "Completed", "Declined: not in the knowledge base", {
                "answer": ("I couldn't find anything about this in your documents, so I won't guess. "
                           "Try rephrasing, upload a document that covers it, or ask me to search the web for it."),
                "sources": [],
                "abstained": True,
            })
            return
        yield emit("Reranking Model", "Completed", f"Filtered down to top {len(ranked_docs)} most relevant contexts")

        yield emit("Generation", "Processing", "Synthesizing answer using LLM and retrieved context")
        gen_context = ranked_docs
        if image_context:
            gen_context = [f"[Image Analysis]:\n{image_context}"] + ranked_docs
            
        # Inject user-provided data if the query contains rich data points
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
                    
            verify_task = asyncio.create_task(self.verifier.verify_fast(answer, gen_context, model_choice=model_choice))
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
                    strict_query = search_query + f"\n\nCRITICAL INSTRUCTION: The previous answer failed verification: {verify_reason} Regenerate the answer and adhere STRICTLY to the provided context only; do not state anything the context does not contain."
                    answer = await self.generator.generate_answer(strict_query, gen_context, sources=list(set(sources)), mode="analytical", model_choice=model_choice)
                    retry_count += 1
                else:
                    warning = warning_for(verify_reason)
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
