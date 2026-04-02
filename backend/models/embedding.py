from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

class LocalEmbeddingModel(Embeddings):
    """
    Wrapper around HuggingFace's sentence-transformers to use as a local embedding model.
    This runs entirely locally without API calls.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # sentence-transformers returns numpy arrays, we convert to list of floats for FAISS/Langchain
        embeddings = self.model.encode(texts)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self.model.encode([text])[0]
        return embedding.tolist()
