import logging

logger = logging.getLogger(__name__)

class RerankerModel:
    """
    Reranks retrieved documents to heavily penalize documents that aren't actually relevant to the query.
    Uses a smaller HuggingFace CrossEncoder model.
    Falls back gracefully to a pass-through if the model cannot be loaded (low-memory cloud environments).
    """
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = None
        self.model_name = model_name
        self.enabled = True
        
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(self.model_name)
        except Exception as e:
            logger.warning(f"Could not load CrossEncoder reranker ({e}). Reranking will be bypassed.")
            self.enabled = False

    def rerank(self, query: str, documents: list[str], top_k: int = 3) -> list[str]:
        if not documents:
            return []
            
        if not self.enabled or self.model is None:
            # Pass-through fallback: return top_k directly
            return documents[:top_k]
            
        try:
            # pairs for cross encoder: (query, doc1), (query, doc2)...
            pairs = [[query, doc] for doc in documents]
            
            # scores represent relevance
            scores = self.model.predict(pairs)
            
            # sort docs by highest score
            ranked_docs = [doc for _, doc in sorted(zip(scores, documents), reverse=True)]
            
            return ranked_docs[:top_k]
        except Exception as e:
            logger.error(f"Reranking failed at runtime ({e}). Falling back to pass-through.")
            return documents[:top_k]

