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
            yield emit("Master LLM Orchestrator", "Processing", "Rewriting query using conversational context...")
            rewrite_prompt = f"Given the conversation history: '{history}', rewrite the following question to be completely self-contained with no pronouns. Return ONLY the rewritten question string. Question: '{query}'"
            search_query = self.generator.llm.invoke(rewrite_prompt).strip()
            yield emit("Master LLM Orchestrator", "Completed", f"Contextualized query: {search_query}")
        else:
            yield emit("Master LLM Orchestrator", "Completed", "Delegating task to Agent Router")

        # 1.25 Image-Aware Routing
        # When an image is uploaded, check if the query is primarily about the image.
        # If so, bypass the KB/Web search and answer directly from the image analysis.
        if image_context:
            image_keywords = ["photo", "image", "picture", "screenshot", "uploaded", "this",
                              "describe", "written", "show", "see", "look", "what is", "what's",
                              "tell me about", "analyze", "read", "content", "says", "text in"]
            query_lower = search_query.lower()
            is_image_centric = any(kw in query_lower for kw in image_keywords)

            if is_image_centric:
                yield emit("Image-Aware Router", "Processing", "Query is about the uploaded image — answering from visual analysis")

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
                # Take the first 300 chars of image analysis to augment the search
                image_summary = image_context[:300].replace("\n", " ")
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
            yield emit("Web Search", "Processing", f"Searching the live internet for: {search_query}")
            try:
                # ─── Query Decomposition (NEW) ───
                # If the query is complex, break it down for better coverage
                queries = [search_query]
                if any(x in search_query.lower() for x in ["compare", "difference", "versus", "vs", "and", ","]):
                    yield emit("Agent Router", "Processing", "Decomposing complex query into focused sub-queries...")
                    decomposition_prompt = f"Decompose this complex query into 3 short, specific search queries to get balanced results for all entities mentioned: '{search_query}'. Return ONLY a JSON list of strings."
                    try:
                        decomp_raw = self.generator.llm.invoke(decomposition_prompt).strip()
                        # Clean up possible markdown
                        decomp_json = re.sub(r'```json\s*|\s*```', '', decomp_raw)
                        queries = json.loads(decomp_json)
                        yield emit("Agent Router", "Completed", f"Expanded to {len(queries)} research paths")
                    except:
                        logger.warning("Query decomposition failed, using original query.")
                
                # Perform searches (could be parallelized for speed)
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
                    tool = "Search_Knowledge_Base"   # fall-through below

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
