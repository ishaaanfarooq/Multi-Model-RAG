import os
import re
import uuid
import subprocess
import logging
from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

class VisualizerAgent:
    """
    An agent that detects numerical data in RAG results and generates
    Matplotlib charts to visualize the information.
    Prioritizes Gemini for sophisticated data extraction and code generation.
    """
    def __init__(self, model_name: str = "llama3.2", output_dir: str = "uploads"):
        self.llm = DualLLM(llama_model=model_name)
        self.output_dir = output_dir
        
        # Ensure output directory exists
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.detect_prompt = PromptTemplate(
            input_variables=["context", "answer"],
            template="""Analyze the following context and the generated answer. Your goal is to determine if a chart (bar, line, or pie) can be generated from the numbers found.
            
TIGGER CONDITIONS (Say YES if ANY are met):
- Academic or Departmental fees/costs are mentioned with specific amounts.
- At least two different companies, entities, or departments are mentioned with a corresponding number (e.g. Sales, Revenue, Price, Fees).
- At least two different years/dates/semesters are mentioned with a corresponding number.
- Any list of at least 3 numbers assigned to categories.

Context:
{context}

Answer:
{answer}

Respond with ONLY the word "YES" if we can plot this data, otherwise ONLY the word "NO".
Response:"""
        )

        self.code_prompt = PromptTemplate(
            input_variables=["context", "answer", "output_path"],
            template="""You are a Lead Data Scientist. Write a Python script using Matplotlib to create a professional high-fidelity chart based on the data in the context/answer.

REQUIREMENTS:
1. DESIGN: Use a sleek, modern design. Background color MUST be '#FDFCFB' (soft wheat). Use a palette of Amber (#B45309), Zinc (#71717A), and Emerald (#059669).
2. STRUCTURE: Use `fig, ax = plt.subplots(figsize=(10, 6))` for the plot.
3. DATA: Extract all relevant numerical values for entities like Tesla, Nvidia, Meta, etc., and their associated years or metrics.
4. SAVE: Save the final image to: '{output_path}'
5. CLEANUP: Do NOT use `plt.show()`, `plt.style.use()`, or any interactive commands.
6. OUTPUT: Return ONLY the raw python code. No markdown, no intro text.

Python Code:"""
        )

    async def run(self, context: list[str], answer: str) -> str:
        """
        Main entry point. Returns the filename of the generated chart, or None.
        """
        full_context = "\n".join(context)
        
        # 1. Detection
        raw_detect = self.llm.invoke(self.detect_prompt.format(context=full_context, answer=answer))
        detect_response = re.sub(r'[^a-zA-Z]', '', raw_detect).upper()
        
        if "YES" not in detect_response:
            logger.info(f"VisualizerAgent: No data-rich content detected. (LLM said: {raw_detect[:50]}...)")
            return None

        # 2. Code Generation
        filename = f"chart_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(self.output_dir, filename)
        
        code_response = self.llm.invoke(self.code_prompt.format(
            context=full_context, 
            answer=answer, 
            output_path=output_path
        ))
        
        # Clean up code (sometimes LLMs include ```python blocks despite instructions)
        code = self._clean_code(code_response)
        
        # 3. Execution
        success = self._execute_code(code)
        
        if success and os.path.exists(output_path):
            logger.info(f"VisualizerAgent: Successfully generated chart at {output_path}")
            return filename
        else:
            logger.error("VisualizerAgent: Failed to generate chart.")
            return None

    def _clean_code(self, response: str) -> str:
        # Try finding markdown code block first
        code = ""
        match = re.search(r'```(?:python)?(.*?)```', response, re.DOTALL)
        if match:
            code = match.group(1).strip()
        else:    
            # Fallback if no code blocks are found
            code = re.sub(r'```python\s*', '', response)
            code = re.sub(r'```\s*', '', code)
            code = code.strip()
            
        # Remove plt.show() to prevent the script from hanging waiting for user input
        code = re.sub(r'plt\.show\(\)', '', code)
        return code

    def _execute_code(self, code: str) -> bool:
        """
        Executes the provided python code in a temporary file.
        """
        temp_script = f"temp_plot_{uuid.uuid4().hex[:8]}.py"
        try:
            with open(temp_script, "w") as f:
                f.write(code)
            
            # Execute the script
            import sys
            result = subprocess.run([sys.executable, temp_script], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Execution Error: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"Visualizer execution failed: {e}")
            return False
        finally:
            if os.path.exists(temp_script):
                os.remove(temp_script)
