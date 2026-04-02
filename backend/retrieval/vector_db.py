import os
from langchain_community.vectorstores import FAISS
from models.embedding import LocalEmbeddingModel
from langchain_core.documents import Document

class VectorDatabase:
    def __init__(self, index_path: str = "faiss_index"):
        self.index_path = index_path
        self.embeddings = LocalEmbeddingModel()
        self.vector_store = None
        self._load_or_create_index()

    def _load_or_create_index(self):
        if os.path.exists(self.index_path) and os.listdir(self.index_path):
            try:
                self.vector_store = FAISS.load_local(self.index_path, self.embeddings, allow_dangerous_deserialization=True)
            except Exception as e:
                print(f"Error loading index: {e}")
                self._create_empty_index()
        else:
            self._create_empty_index()

    def _create_empty_index(self):
        # FAISS needs at least one document to initialize
        empty_doc = Document(page_content="Initial empty document.", metadata={"source": "system"})
        self.vector_store = FAISS.from_documents([empty_doc], self.embeddings)

    def add_documents(self, documents: list[Document]):
        """
        Embed and add documents to FAISS.
        """
        self.vector_store.add_documents(documents)
        self.save_index()

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        """
        Retrieve top_k documents based on vector similarity.
        """
        if not self.vector_store:
            return []
        # Return list of Document objects
        return self.vector_store.search(query, search_type="similarity", k=top_k)
        
    def save_index(self):
        self.vector_store.save_local(self.index_path)
