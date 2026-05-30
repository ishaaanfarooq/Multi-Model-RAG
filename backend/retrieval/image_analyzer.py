import os
import io
import base64
import logging
import httpx
from PIL import Image
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
        self.ocr_reader = None
        self.max_image_dimension = 1024  # Max px dimension before resizing

    def _preprocess_image(self, image_bytes: bytes, ext: str) -> bytes:
        """
        Resize large images to fit within max_image_dimension while preserving
        aspect ratio. This reduces payload size, prevents vision model timeouts,
        and improves OCR accuracy by keeping images at a consistent scale before processing.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size

            if max(w, h) > self.max_image_dimension:
                scale = self.max_image_dimension / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.LANCZOS)
                logger.info(f"ImageAnalyzer: Resized image from {w}x{h} → {new_size[0]}x{new_size[1]}")

            # Re-encode to bytes
            fmt = "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
            output = io.BytesIO()
            img.save(output, format=fmt, optimize=True)
            return output.getvalue()
        except Exception as e:
            logger.warning(f"ImageAnalyzer: Preprocessing failed, using original: {e}")
            return image_bytes

    def _get_ocr_reader(self):
        if self.ocr_reader is None:
            try:
                import easyocr
                logger.info("Initializing EasyOCR reader...")
                self.ocr_reader = easyocr.Reader(['en'], gpu=True)
            except ImportError:
                logger.warning("easyocr not installed, OCR will be skipped")
                self.ocr_reader = "disabled"
        return self.ocr_reader if self.ocr_reader != "disabled" else None

    async def analyze(self, image_paths: list[str], query: str = "") -> str:
        """
        Analyze multiple images and return a combined text description.
        """
        if not image_paths:
            return ""

        results = []
        for i, path in enumerate(image_paths):
            if not os.path.exists(path):
                logger.error(f"ImageAnalyzer: File not found: {path}")
                results.append(f"[Image {i+1}: File not found]")
                continue
            
            res = await self._analyze_single(path, query)
            results.append(f"--- IMAGE {i+1} ANALYSIS ---\n{res}\n")
            
        return "\n".join(results)

    async def _analyze_single(self, image_path: str, query: str = "") -> str:
        """
        Analyze an image and return a text description with extracted data.
        """

        try:
            # Read and encode the image
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # Determine file type early so preprocessing can use it
            ext = os.path.splitext(image_path)[1].lower()
            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
            mime_type = mime_map.get(ext, "image/png")

            # Preprocess: resize if oversized to reduce latency and prevent timeouts
            image_bytes = self._preprocess_image(image_bytes, ext)
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # --- Extract text using OCR ---
            ocr_text = ""
            reader = self._get_ocr_reader()
            if reader:
                try:
                    ocr_results = reader.readtext(image_bytes, detail=0)
                    if ocr_results:
                        ocr_text = " ".join(ocr_results)
                        logger.info(f"ImageAnalyzer: Extracted {len(ocr_text)} characters via OCR.")
                except Exception as e:
                    logger.warning(f"ImageAnalyzer: OCR failed: {e}")
            
            # Try Gemini Vision first (it handles images natively)
            if self.llm.gemini_llm:
                try:
                    from langchain_core.messages import HumanMessage
                    
                    prompt_text = self._build_prompt(query, ocr_text)
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
            
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

            async with httpx.AsyncClient(timeout=120.0) as client:
                for model in models_to_try:
                    try:
                        logger.info(f"ImageAnalyzer: Attempting analysis with model '{model}'...")
                        response = await client.post(
                            f"{ollama_host}/api/generate",
                            json={
                                "model": model,
                                "prompt": self._build_prompt(query, ocr_text),
                                "images": [image_b64],
                                "stream": False,
                            }
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

            # Final fallback: just describe that an image was uploaded
            logger.warning("ImageAnalyzer: No vision model available or all failed. Returning basic description.")
            fallback_msg = f"[Vision Analysis Failed] All local models (LLaVA/Moondream) failed to analyze this image. User query: '{query}'."
            if ocr_text:
                fallback_msg += f"\n\nHowever, OCR extracted the following text:\n{ocr_text}"
            return fallback_msg

        except Exception as e:
            logger.error(f"ImageAnalyzer failed: {e}")
            return f"[Image analysis failed: {str(e)}]"

    def _build_prompt(self, query: str = "", ocr_text: str = "") -> str:
        """Build a focused analysis prompt for the vision model."""
        base_instruction = (
            "Analyze the image and provide a highly detailed, comprehensive description. "
            "IMPORTANT: "
            "1. If you see any tables, charts, or structured data, extract them exactly as they appear using Markdown. "
            "2. Extract all visible text accurately. Ensure numerical values are preserved perfectly. "
            "3. Reason deeply about the visual elements: explain the relationships between different parts of the image, the overall context, and any logical conclusions that can be drawn. Do not just list elements; synthesize what they mean together."
        )
        
        if ocr_text:
            base_instruction += f"\n\n[Extracted Text via OCR]:\n{ocr_text}\n"

        if query:
            return f"{base_instruction}\n\nUser Question: {query}\n\nAnswer the user's question precisely and thoroughly using the visual information provided."
        
        return f"{base_instruction}\n\nDescribe the main subject, extract all data points, and explain the deeper meaning of the image."
