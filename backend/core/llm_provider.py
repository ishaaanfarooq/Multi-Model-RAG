import os
import logging
from typing import Any, AsyncGenerator
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.llms import Ollama
from anthropic import Anthropic, AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Single source of truth for the local model. Callers pass llama_model=None to
# inherit this, so LLM_MODEL in the environment actually takes effect.
DEFAULT_LLAMA_MODEL = os.getenv("LLM_MODEL") or "llama3.2"

class DualLLM:
    """
    A wrapper that prioritizes Gemini API and falls back to Local Llama (Ollama)
    if the API key is missing or the call fails. Also supports an explicit
    Claude (Anthropic) backend.

    Supports explicit model_choice:
      - "auto"   : Try Gemini first, fallback to Llama (original behaviour)
      - "local"  : Force Llama only, never touch Gemini or Claude
      - "api"    : Force Gemini only, surfacing an error if Gemini is unavailable
      - "claude" : Force Claude only, surfacing an error if Claude is unavailable
    """
    def __init__(
        self,
        llama_model: str = None,
        gemini_model: str = "gemini-2.0-flash",
        claude_model: str = "claude-opus-4-8",
    ):
        self.llama_model = llama_model or DEFAULT_LLAMA_MODEL
        self.gemini_model = gemini_model
        self.claude_model = claude_model
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        # Initialize Llama (Always available as fallback)
        base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.llama_llm = Ollama(model=self.llama_model, base_url=base_url)

        # Initialize Gemini if key exists and is not a placeholder
        self.gemini_llm = None
        if self.gemini_api_key and self.gemini_api_key != "your_gemini_api_key_here":
            try:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model=self.gemini_model,
                    google_api_key=self.gemini_api_key,
                    temperature=0.7,
                    max_retries=1,
                )
                logger.info("Gemini LLM initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

        # Initialize Claude if key exists and is not a placeholder
        self.claude_client = None
        self.claude_async_client = None
        if self.anthropic_api_key and self.anthropic_api_key != "your_anthropic_api_key_here":
            try:
                self.claude_client = Anthropic(api_key=self.anthropic_api_key)
                self.claude_async_client = AsyncAnthropic(api_key=self.anthropic_api_key)
                logger.info("Claude LLM initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Claude: {e}")

    def _should_use_gemini(self, model_choice: str) -> bool:
        """Determine whether Gemini should be attempted based on model_choice."""
        if model_choice in ("local", "claude"):
            return False
        # For "auto" and "api", try Gemini if it's available
        return self.gemini_llm is not None

    def invoke(self, prompt: str, model_choice: str = "auto") -> str:
        """
        Invoke the LLM. model_choice controls which backend is used:
          - "auto"   : Gemini first, then Llama fallback
          - "local"  : Llama only
          - "api"    : Gemini only
          - "claude" : Claude only
        """
        if model_choice == "api" and self.gemini_llm is None:
            raise RuntimeError("Gemini API model was selected, but GEMINI_API_KEY is not configured.")
        if model_choice == "claude" and self.claude_client is None:
            raise RuntimeError("Claude model was selected, but ANTHROPIC_API_KEY is not configured.")

        if model_choice == "claude":
            response = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in response.content if block.type == "text")

        if self._should_use_gemini(model_choice):
            try:
                # ChatGoogleGenerativeAI returns a message object, so we get .content
                response = self.gemini_llm.invoke(prompt)
                return response.content
            except Exception as e:
                if model_choice == "api":
                    logger.error(f"Gemini call failed and model_choice is 'api': {e}")
                    raise
                else:
                    logger.warning(f"Gemini call failed, falling back to Llama: {e}")
        
        # Fallback to Llama (or primary when model_choice == "local")
        return self.llama_llm.invoke(prompt)

    async def astream(self, prompt: str, model_choice: str = "auto") -> AsyncGenerator[str, None]:
        """
        Stream from the LLM. model_choice controls which backend is used.
        """
        if model_choice == "api" and self.gemini_llm is None:
            raise RuntimeError("Gemini API model was selected, but GEMINI_API_KEY is not configured.")
        if model_choice == "claude" and self.claude_async_client is None:
            raise RuntimeError("Claude model was selected, but ANTHROPIC_API_KEY is not configured.")

        if model_choice == "claude":
            async with self.claude_async_client.messages.stream(
                model=self.claude_model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
            return

        if self._should_use_gemini(model_choice):
            try:
                async for chunk in self.gemini_llm.astream(prompt):
                    yield chunk.content
                return
            except Exception as e:
                if model_choice == "api":
                    logger.error(f"Gemini streaming failed and model_choice is 'api': {e}")
                    raise
                else:
                    logger.warning(f"Gemini streaming failed, falling back to Llama: {e}")
        
        # Fallback to Llama streaming
        try:
            async for chunk in self.llama_llm.astream(prompt):
                yield chunk
        except Exception as e:
            logger.error(f"Llama streaming failed: {e}")
            yield self.llama_llm.invoke(prompt)

    def get_active_model_name(self, model_choice: str = "auto") -> str:
        """Return a human-readable name for the model that will be used."""
        if model_choice == "claude":
            return f"Claude ({self.claude_model})"
        if self._should_use_gemini(model_choice):
            return f"Gemini ({self.gemini_model})"
        return f"Llama ({self.llama_model})"

def get_llm(llama_model: str = None):
    return DualLLM(llama_model=llama_model)
