import os
import logging
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.llms import Ollama
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class DualLLM:
    """
    A wrapper that prioritizes Gemini API and falls back to Local Llama (Ollama)
    if the API key is missing or the call fails.
    """
    def __init__(self, llama_model: str = "llama3.2", gemini_model: str = "gemini-1.5-pro"):
        self.llama_model = llama_model
        self.gemini_model = gemini_model
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        # Initialize Llama (Always available as fallback)
        self.llama_llm = Ollama(model=self.llama_model)
        
        # Initialize Gemini if key exists
        self.gemini_llm = None
        if self.gemini_api_key:
            try:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model=self.gemini_model,
                    google_api_key=self.gemini_api_key,
                    temperature=0.7
                )
                logger.info("Gemini LLM initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

    def invoke(self, prompt: str) -> str:
        """
        Try Gemini first, then fallback to Llama.
        """
        if self.gemini_llm:
            try:
                # ChatGoogleGenerativeAI returns a message object, so we get .content
                response = self.gemini_llm.invoke(prompt)
                return response.content
            except Exception as e:
                logger.warning(f"Gemini call failed, falling back to Llama: {e}")
        
        # Fallback to Llama
        return self.llama_llm.invoke(prompt)

def get_llm(llama_model: str = "llama3.2"):
    return DualLLM(llama_model=llama_model)
