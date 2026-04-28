import os
import base64
import logging
from core.llm_provider import DualLLM

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """
    Analyzes uploaded images using a vision-capable LLM.
    Tries Ollama's LLaVA model (local, free) first, 
    then falls back to Gemini Vision if available.
    """

    def __init__(self):
        self.llm = DualLLM()

    async def analyze(self, image_path: str, query: str = "") -> str:
        """
        Analyze an image and return a text description with extracted data.
        
        Args:
            image_path: Path to the image file.
            query: Optional user query for context-aware analysis.
        
        Returns:
            A detailed text description of the image contents.
        """
        try:
            # Read and encode the image
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Determine file type
            ext = os.path.splitext(image_path)[1].lower()
            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
            mime_type = mime_map.get(ext, "image/png")

            # Try Gemini Vision first (it handles images natively)
            if self.llm.gemini_llm:
                try:
                    from langchain_core.messages import HumanMessage
                    
                    prompt_text = self._build_prompt(query)
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                        ]
                    )
                    response = self.llm.gemini_llm.invoke([message])
                    logger.info("ImageAnalyzer: Successfully analyzed image with Gemini Vision.")
                    return response.content
                except Exception as e:
                    logger.warning(f"Gemini Vision failed, trying Ollama LLaVA: {e}")

            # Fallback: Try Ollama with LLaVA (vision model)
            try:
                import requests
                ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
                
                response = requests.post(
                    f"{ollama_host}/api/generate",
                    json={
                        "model": "llava",
                        "prompt": self._build_prompt(query),
                        "images": [image_b64],
                        "stream": False,
                    },
                    timeout=60,
                )
                
                if response.status_code == 200:
                    result = response.json().get("response", "")
                    logger.info("ImageAnalyzer: Successfully analyzed image with Ollama LLaVA.")
                    return result
                else:
                    logger.warning(f"Ollama LLaVA returned status {response.status_code}")
            except Exception as e:
                logger.warning(f"Ollama LLaVA failed: {e}")

            # Final fallback: just describe that an image was uploaded
            logger.warning("ImageAnalyzer: No vision model available. Returning basic description.")
            return f"[An image was uploaded by the user. No vision model is available to analyze it. The user's query about this image was: '{query}']"

        except Exception as e:
            logger.error(f"ImageAnalyzer failed: {e}")
            return f"[Image analysis failed: {str(e)}]"

    def _build_prompt(self, query: str = "") -> str:
        """Build the analysis prompt for the vision model."""
        base = """Analyze this image in detail. Extract ALL of the following:

1. **Text Content**: Any text, labels, numbers, titles visible in the image.
2. **Data Points**: Any numerical data, statistics, percentages, or measurements.
3. **Visual Structure**: Describe charts, tables, diagrams, or graphs if present. Include axis labels, legends, and data values.
4. **Key Entities**: Names of companies, people, products, or locations mentioned.
5. **Summary**: A concise 2-sentence summary of what this image shows.

Be extremely precise with numbers and text. Do not hallucinate data that isn't visible."""
        
        if query:
            base += f"\n\nThe user specifically wants to know: {query}"
        
        return base
