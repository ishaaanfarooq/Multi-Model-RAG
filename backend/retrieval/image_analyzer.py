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

            # Try a list of vision models available in Ollama
            models_to_try = [
                os.getenv("OLLAMA_VISION_MODEL", "llava"),
                "moondream",
                "llava:7b-v1.5-q4_0"
            ]
            
            last_error = None
            import requests
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

            for model in models_to_try:
                try:
                    logger.info(f"ImageAnalyzer: Attempting analysis with model '{model}'...")
                    response = requests.post(
                        f"{ollama_host}/api/generate",
                        json={
                            "model": model,
                            "prompt": self._build_prompt(query),
                            "images": [image_b64],
                            "stream": False,
                        },
                        timeout=120,
                    )
                    
                    if response.status_code == 200:
                        result = response.json().get("response", "").strip()
                        if result:
                            logger.info(f"ImageAnalyzer: Successfully analyzed image with '{model}'. Length: {len(result)}")
                            return result
                        else:
                            logger.warning(f"ImageAnalyzer: Model '{model}' returned an empty response. Trying next...")
                    else:
                        logger.warning(f"ImageAnalyzer: Model '{model}' returned status {response.status_code}")
                except Exception as e:
                    logger.warning(f"ImageAnalyzer: Call to '{model}' failed: {e}")
                    last_error = e

            # Final fallback: just describe that an image was uploaded
            logger.warning("ImageAnalyzer: No vision model available or all failed. Returning basic description.")
            return f"[Vision Analysis Failed] All local models (LLaVA/Moondream) failed to analyze this image. User query: '{query}'. Please check Ollama logs for details."

        except Exception as e:
            logger.error(f"ImageAnalyzer failed: {e}")
            return f"[Image analysis failed: {str(e)}]"

    def _build_prompt(self, query: str = "") -> str:
        """Build a focused analysis prompt for the vision model."""
        base_instruction = (
            "Analyze the image and provide a comprehensive description. "
            "IMPORTANT: If you see any tables, charts, or structured data, extract them exactly "
            "as they appear. Use Markdown formatting for tables. Extract all visible text accurately."
        )
        
        if query:
            return f"{base_instruction}\n\nUser Question: {query}\n\nAnswer the user's question precisely using the visual information provided."
        
        return f"{base_instruction}\n\nDescribe the main subject and extract all data points."
