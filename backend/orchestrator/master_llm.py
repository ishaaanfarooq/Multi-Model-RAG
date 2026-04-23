import asyncio
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
        
    async def process_query_stream(self, query: str, history: str = "") -> AsyncGenerator[str, None]:
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
            yield emit("Master LLM Orchestrator", "Processing", "Rewriting query using conversational context...")
            rewrite_prompt = f"Given the conversation history: '{history}', rewrite the following question to be completely self-contained with no pronouns. Return ONLY the rewritten question string. Question: '{query}'"
            search_query = self.generator.llm.invoke(rewrite_prompt).strip()
            yield emit("Master LLM Orchestrator", "Completed", f"Contextualized query: {search_query}")
        else:
            yield emit("Master LLM Orchestrator", "Completed", "Delegating task to Agent Router")

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

        # ─── DIRECT CHAT branch ────────────────────────────────────────────
        if tool == "Direct_Chat":
            yield emit("Direct Chat", "Processing", "Engaging directly without retrieval")
            try:
                answer = await self.generator.generate_answer(
                    search_query,
                    ["You are a helpful AI assistant. Answer the user's conversational query directly."]
                )
                yield emit("Direct Chat", "Completed", "Answer generated")
                yield emit("Final Response", "Completed", "Done", {"answer": answer, "sources": []})
            except Exception as e:
                logger.error(f"Direct chat failed: {e}")
            return

        # ─── WEB SEARCH branch ────────────────────────────────────────────
        elif tool == "Web_Search":
            yield emit("Web Search", "Processing", f"Searching the live internet for: {search_query}")
            try:
                doc_texts, sources = await search_web(search_query, max_results=5)

                if doc_texts:
                    yield emit("Web Search", "Completed", f"Retrieved {len(doc_texts)} live web results")
                else:
                    yield emit("Web Search", "Completed", "No web results found — falling back to Knowledge Base")
                    tool = "Search_Knowledge_Base"   # fall-through below

            except Exception as e:
                logger.error(f"Web search failed: {e}")
                yield emit("Web Search", "Completed", f"Web search failed ({str(e)[:80]}) — falling back to Knowledge Base")
                tool = "Search_Knowledge_Base"

            # If web search succeeded, generate + verify + visualize then return
            if tool == "Web_Search":
                yield emit("Generation", "Processing", "Synthesizing answer using live web data")
                answer = await self.generator.generate_answer(search_query, doc_texts)
                yield emit("Generation", "Completed", "Answer drafted successfully")

                # Verification
                yield emit("Verification Module", "Processing", "Fact-checking answer against retrieved web context")
                is_valid = await self.verifier.verify(answer, doc_texts)
                warning = None
                if is_valid:
                    yield emit("Verification Module", "Completed", "Response passed factuality check (PASS)")
                else:
                    yield emit("Verification Module", "Completed", "Verification flagged potential inaccuracies (FAIL)")
                    warning = "The AI may not have found all details in the retrieved web sources. Treat specific figures as approximate."

                # Visualization
                chart_filename = None
                yield emit("Visualizer Agent", "Processing", "Scanning for numerical data to generate a visual chart...")
                try:
                    chart_filename = await self.visualizer.run(doc_texts, answer)
                    if chart_filename:
                        yield emit("Visualizer Agent", "Completed", "Data chart generated successfully", {"chart": f"/uploads/{chart_filename}"})
                    else:
                        yield emit("Visualizer Agent", "Completed", "No significant numerical data found for charting.")
                except Exception as e:
                    logger.error(f"Visualizer failed: {e}")
                    yield emit("Visualizer Agent", "Error", f"Visualization failed: {str(e)[:80]}")

                final_details = {"answer": answer, "sources": sources}
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
        answer = await self.generator.generate_answer(search_query, ranked_docs)
        yield emit("Generation", "Completed", "Answer drafted successfully")

        # Verification
        yield emit("Verification Module", "Processing", "Checking generated answer against original retrieved context for hallucinations")
        is_valid = await self.verifier.verify(answer, ranked_docs)
        warning = None
        if is_valid:
            yield emit("Verification Module", "Completed", "Response passed factuality check (PASS)")
        else:
            yield emit("Verification Module", "Completed", "Verification flagged potential inaccuracies (FAIL)")
            warning = "The AI's answer may contain information not fully supported by the retrieved source documents."

        # Visualization
        chart_filename = None
        yield emit("Visualizer Agent", "Processing", "Scanning for numerical data to generate a visual chart...")
        try:
            chart_filename = await self.visualizer.run(ranked_docs, answer)
            if chart_filename:
                yield emit("Visualizer Agent", "Completed", "Data chart generated successfully", {"chart": f"/uploads/{chart_filename}"})
            else:
                yield emit("Visualizer Agent", "Completed", "No significant numerical data found for charting.")
        except Exception as e:
            logger.error(f"Visualizer failed: {e}")
            yield emit("Visualizer Agent", "Error", f"Visualization failed: {str(e)[:80]}")

        # Final Response
        final_details = {"answer": answer, "sources": list(set(sources))}
        if chart_filename:
            final_details["chart"] = f"/uploads/{chart_filename}"
        if warning:
            final_details["warning"] = warning
            
        # Save metadata to the analytical notebook
        self.notebook.save_entry(query, answer, list(set(sources)))
            
        yield emit("Final Response", "Completed", "Pipeline finished", final_details)
