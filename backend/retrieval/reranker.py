import logging

logger = logging.getLogger(__name__)

class RerankerModel:
    """
    Reranks retrieved documents to heavily penalize documents that aren't actually relevant to the query.
    Uses a smaller HuggingFace CrossEncoder model.
    Falls back gracefully to a pass-through if the model cannot be loaded (low-memory cloud environments).
    """
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", min_relevance_score: float = -5.0):
        self.model = None
        self.model_name = model_name
        self.enabled = True
        self.min_relevance_score = min_relevance_score
        
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
            
            # Log relevance scores for debugging and transparency
            scored_pairs = sorted(zip(scores, documents), reverse=True)
            for i, (score, doc) in enumerate(scored_pairs[:top_k + 2]):
                preview = doc[:80].replace('\n', ' ')
                logger.info(f"Reranker [{i+1}] score={score:.4f}: \"{preview}...\"")
            
            # Filter out documents below minimum relevance threshold
            filtered = [(score, doc) for score, doc in scored_pairs if score >= self.min_relevance_score]
            
            if not filtered:
                logger.warning(f"Reranker: All documents scored below threshold ({self.min_relevance_score}). Returning top result anyway.")
                filtered = [scored_pairs[0]]
            
            return [doc for _, doc in filtered[:top_k]]
        except Exception as e:
            logger.error(f"Reranking failed at runtime ({e}). Falling back to pass-through.")
            return documents[:top_k]

