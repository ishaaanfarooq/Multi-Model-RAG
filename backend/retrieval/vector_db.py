import os
import logging
from langchain_community.vectorstores import FAISS
from models.embedding import LocalEmbeddingModel
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class VectorDatabase:
    """Vector database for storing and retrieving document embeddings using FAISS."""
    def __init__(self, index_path: str = "faiss_index"):
        self.index_path = index_path
        self.embeddings = LocalEmbeddingModel()
        self.vector_store = None
        self._load_or_create_index()

    def _load_or_create_index(self):
        """Load existing FAISS index or create a new one."""
        if os.path.exists(self.index_path) and os.listdir(self.index_path):
            try:
                logger.info(f"Loading existing FAISS index from {self.index_path}...")
                self.vector_store = FAISS.load_local(self.index_path, self.embeddings, allow_dangerous_deserialization=True)
                logger.info("FAISS index loaded successfully.")
            except Exception as e:
                logger.error(f"Error loading index: {e}. Creating new index...")
                self._create_empty_index()
        else:
            logger.info(f"No existing index found at {self.index_path}. Creating new index...")
            self._create_empty_index()

    def _create_empty_index(self):
        """Create a new empty FAISS index with a placeholder document."""
        try:
            os.makedirs(self.index_path, exist_ok=True)
            # FAISS needs at least one document to initialize
            empty_doc = Document(page_content="Initial empty document.", metadata={"source": "system"})
            self.vector_store = FAISS.from_documents([empty_doc], self.embeddings)
            logger.info("New FAISS index created successfully.")
        except Exception as e:
            logger.error(f"Failed to create empty index: {e}")
            raise

    def add_documents(self, documents: list[Document]):
        """
        Embed and add documents to FAISS.
        """
        if not documents:
            logger.warning("No documents provided to add.")
            return
        
        try:
            logger.info(f"Adding {len(documents)} documents to FAISS index...")
            self.vector_store.add_documents(documents)
            self.save_index()
            logger.info(f"Successfully added {len(documents)} documents to FAISS index.")
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        """
        Retrieve top_k documents based on vector similarity.
        """
        if not self.vector_store:
            logger.warning("Vector store not initialized.")
            return []
        
        try:
            logger.debug(f"Retrieving top {top_k} documents for query: {query[:100]}...")
            docs = self.vector_store.similarity_search(query, k=top_k)
            logger.info(f"Retrieved {len(docs)} documents from FAISS.")
            return docs
        except Exception as e:
            logger.error(f"Failed to retrieve documents: {e}")
            return []
        
    def save_index(self):
        """Save the FAISS index to disk."""
        if not self.vector_store:
            logger.warning("No vector store to save.")
            return
        
        try:
            logger.debug(f"Saving FAISS index to {self.index_path}...")
            self.vector_store.save_local(self.index_path)
            logger.info("FAISS index saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}")
            raise
