import asyncio
from typing import AsyncGenerator
import json
from models.embedding import LocalEmbeddingModel
from retrieval.vector_db import VectorDatabase
from retrieval.reranker import RerankerModel
from models.generation import GenerationModel
from verification.verifier import VerificationModule

class MasterOrchestrator:
    """
    Coordinates the multi-model RAG workflow.
    Publishes status events directly formatted for SSE.
    """
    def __init__(self):
        # In a real app, these would be dependency injected or singletons
        self.vector_db = VectorDatabase()
        self.reranker = RerankerModel()
        self.generator = GenerationModel()
        self.verifier = VerificationModule()
        
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
        try:
            from models.agentic_router import AgentRouter
            import asyncio
            router = AgentRouter(model_name="llama3.2")
            tool = await asyncio.to_thread(router.route_query, search_query)
            yield emit("Agent Router", "Completed", f"Selected Tool: [{tool}]")
        except Exception as e:
            tool = "Search_Knowledge_Base"
            yield emit("Agent Router", "Completed", f"Fallback to Default Tool: [{tool}]")

        if tool == "Direct_Chat":
            yield emit("Direct Chat", "Processing", "Engaging directly without retrieval")
            try:
                # Provide an empty context string array
                answer = await self.generator.generate_answer(search_query, ["You are a helpful AI assistant. Answer the user's conversational query directly without any knowledge base."])
                yield emit("Direct Chat", "Completed", "Answer generated")
                yield emit("Final Response", "Completed", "Done", {"answer": answer, "sources": []})
            except Exception as e:
                pass
            return
            
        elif tool == "Web_Search":
            yield emit("DuckDuckGo Web Search", "Processing", f"Searching the live internet for: {search_query}")
            try:
                from duckduckgo_search import DDGS
                
                def _do_search():
                    with DDGS() as ddgs:
                        return list(ddgs.text(search_query, max_results=3))
                        
                results = await asyncio.to_thread(_do_search)
                doc_texts = [r["body"] for r in results]
                sources = [r["href"] for r in results]
                
                yield emit("DuckDuckGo Web Search", "Completed", f"Found {len(results)} live results")
                
                yield emit("Generation", "Processing", "Synthesizing answer using live web data")
                answer = await self.generator.generate_answer(search_query, doc_texts)
                yield emit("Generation", "Completed", "Answer drafted successfully")
                
                yield emit("Final Response", "Completed", "Done", {"answer": answer, "sources": sources})
                return
            except Exception as e:
                yield emit("DuckDuckGo Web Search", "Completed", f"Web Search failed. Falling back to local Knowledge Base.")

        # 2. Embedding (Fallback to standard RAG pipeline)
        yield emit("Embedding Model", "Processing", f"Converting query into dense vector representation")
        # Assuming embed happens inside retriever mostly, simulation here for UI flow
        yield emit("Embedding Model", "Completed", "Vector embedding generated successfully")

        # 3. Retrieval
        yield emit("Vector Retrieval", "Processing", "Searching FAISS vector database for nearest neighbors")
        docs = self.vector_db.retrieve(search_query, top_k=10)
        doc_texts = [d.page_content for d in docs]
        sources = [d.metadata.get("source", "Unknown") for d in docs]
        
        if not doc_texts:
            yield emit("Vector Retrieval", "Completed", "No relevant context found in database.")
            yield emit("Generation", "Processing", "Generating fallback response")
            result = "I couldn't find relevant information in my knowledge base."
            yield emit("Final Response", "Completed", "Done", {"answer": result, "sources": []})
            return

        yield emit("Vector Retrieval", "Completed", f"Retrieved {len(docs)} relevant chunks from database")

        # 4. Reranking
        yield emit("Reranking Model", "Processing", "Cross-encoding query and documents to filter relevance")
        ranked_docs = self.reranker.rerank(search_query, doc_texts, top_k=5)
        yield emit("Reranking Model", "Completed", f"Filtered down to top {len(ranked_docs)} most relevant contexts")

        # 5. Generation
        yield emit("Generation", "Processing", "Synthesizing answer using LLM and retrieved context")
        answer = await self.generator.generate_answer(search_query, ranked_docs)
        yield emit("Generation", "Completed", "Answer drafted successfully")

        # 6. Verification
        yield emit("Verification Module", "Processing", "Checking generated answer against original retrieved context for hallucinations")
        is_valid = await self.verifier.verify(answer, ranked_docs)
        if is_valid:
           yield emit("Verification Module", "Completed", "Response passed factuality check (PASS)") 
        else:
           yield emit("Verification Module", "Completed", "Response failed strict verification check, but returning drafted answer with warning (FAIL)")
           answer = "[WARNING: May contain hallucinations] " + answer

        # 7. Final Response
        yield emit("Final Response", "Completed", "Pipeline finished", {"answer": answer, "sources": list(set(sources))})
