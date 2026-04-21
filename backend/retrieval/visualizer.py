import os
import re
import uuid
import subprocess
import logging
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

class VisualizerAgent:
    """
    An agent that detects numerical data in RAG results and generates
    Matplotlib charts to visualize the information.
    """
    def __init__(self, model_name: str = "llama3.2", output_dir: str = "uploads"):
        self.llm = Ollama(model=model_name)
        self.output_dir = output_dir
        
        # Ensure output directory exists
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.detect_prompt = PromptTemplate(
            input_variables=["context", "answer"],
            template="""Analyze the following context and the generated answer. 
Determine if there is enough numerical or tabular data to create a high-quality visualization (bar chart, line graph, or pie chart).

Context:
{context}

Answer:
{answer}

Respond with ONLY the word "YES" if a visualization would be highly beneficial and has sufficient data, otherwise respond with "NO".
Response:"""
        )

        self.code_prompt = PromptTemplate(
            input_variables=["context", "answer", "output_path"],
            template="""You are an expert Data Visualizer. Your task is to write a Python script using Matplotlib and Pandas to visualize the numerical data found in the context/answer.

DATA:
Context: {context}
Answer: {answer}

REQUIREMENTS:
1. Use a professional style. Set the background color strictly using `fig, ax = plt.subplots()` followed by `fig.patch.set_facecolor('#f5deb3')` and `ax.set_facecolor('#f5deb3')`. Use 'Amber' accents (#ffbf00) if possible.
2. The script MUST save the plot to the path: '{output_path}'
3. The script MUST be self-contained and not require any external files.
4. Output ONLY the valid Python code. Do NOT include markdown blocks, explanations, or any other text.
5. Use clear titles and labels.
6. DO NOT use `plt.style.use()` as it may cause FileNotFoundError on some systems.

Python Code:"""
        )

    async def run(self, context: list[str], answer: str) -> str:
        """
        Main entry point. Returns the filename of the generated chart, or None.
        """
        full_context = "\n".join(context)
        
        # 1. Detection
        detect_response = self.llm.invoke(self.detect_prompt.format(context=full_context, answer=answer)).strip().upper()
        
        if "YES" not in detect_response:
            logger.info("VisualizerAgent: No data-rich content detected for visualization.")
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
