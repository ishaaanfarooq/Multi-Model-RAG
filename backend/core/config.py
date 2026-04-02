import os

class Settings:
    PROJECT_NAME: str = "Cloud-Based Multi-Model RAG System"
    VECTOR_STORE_PATH: str = "faiss_index"
    UPLOAD_DIR: str = "uploads"
    
    # These would normally come from .env in a real deployment
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    
    # Ensure directories exist
    @classmethod
    def setup_directories(cls):
        os.makedirs(cls.VECTOR_STORE_PATH, exist_ok=True)
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)

settings = Settings()
settings.setup_directories()
