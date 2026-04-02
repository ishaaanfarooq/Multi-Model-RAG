from sentence_transformers import CrossEncoder

class RerankerModel:
    """
    Reranks retrieved documents to heavily penalize documents that aren't actually relevant to the query.
    Uses a smaller HuggingFace CrossEncoder model.
    """
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, documents: list[str], top_k: int = 3) -> list[str]:
        if not documents:
            return []
            
        # pairs for cross encoder: (query, doc1), (query, doc2)...
        pairs = [[query, doc] for doc in documents]
        
        # scores represent relevance
        scores = self.model.predict(pairs)
        
        # sort docs by highest score
        ranked_docs = [doc for _, doc in sorted(zip(scores, documents), reverse=True)]
        
        return ranked_docs[:top_k]
