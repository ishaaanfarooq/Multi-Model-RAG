import os
from tempfile import NamedTemporaryFile
from fastapi import UploadFile
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

class DocumentParser:
    def __init__(self, chunk_size=1000, chunk_overlap=200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def parse_upload_file(self, file: UploadFile) -> list[Document]:
        """
        Parses an uploaded file into a list of Langchain Documents.
        """
        # Save uploaded file temporarily to process it
        ext = os.path.splitext(file.filename)[1].lower()
        
        with NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        documents = []
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(temp_file_path)
                documents = loader.load()
            elif ext in [".txt", ".md"]:
                loader = TextLoader(temp_file_path)
                documents = loader.load()
            else:
                raise ValueError(f"Unsupported file extension: {ext}")
                
            # Basic chunking (can be enhanced with RecursiveCharacterTextSplitter)
            # For simplicity, returning the raw pages as chunks for now
            return documents
        finally:
            os.remove(temp_file_path)
