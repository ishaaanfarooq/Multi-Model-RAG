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
    def __init__(self, model_name: str = "llama3.2", output_dir: str = "uploads", persona_memory=None):
        self.llm = DualLLM(llama_model=model_name)
        self.output_dir = output_dir
        self.persona_memory = persona_memory
        
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
            input_variables=["context", "answer", "output_path", "persona"],
            template="""You are a Lead Data Scientist and UI/UX Designer. Write a Python script using Matplotlib to create a STUNNING, professional, presentation-grade chart based on the data in the context/answer.

### 🎭 USER PERSONA & PREFERENCES
{persona}

### 🎨 PREMIUM DESIGN SYSTEM REQUIREMENTS:
1. **BACKGROUND & BORDERS**:
   - Set the figure background color to `#F8FAFC` (soft slate white) for an elegant dashboard look: `fig, ax = plt.subplots(figsize=(8, 5), facecolor='#F8FAFC')` and `ax.set_facecolor('#F8FAFC')`.
   - Remove the top and right black boundary lines (spines) entirely: 
     `ax.spines['top'].set_visible(False)`
     `ax.spines['right'].set_visible(False)`
   - Set left and bottom spines to a clean soft grey color: `#94A3B8`.

2. **GRIDLINES & ALIGNMENT**:
   - Add faint, clean, horizontal gridlines (Y-axis only) to help the reader map numbers:
     `ax.grid(axis='y', linestyle='--', alpha=0.3, color='#CBD5E1')`
     `ax.set_axisbelow(True)` # Keep grid lines behind the data bars

3. **MODERN COLOR PALETTES**:
   - Use beautiful modern hex colors. Do NOT use standard flat red/green/blue.
   - For comparisons/rankings: Sunset Indigo (`#6366F1`), Soft Violet (`#8B5CF6`), Rose Pink (`#EC4899`), Warm Coral (`#F43F5E`).
   - For finance/metrics: Forest Green (`#10B981`), Mint (`#34D399`), Charcoal Slate (`#475569`).
   - For general categorical items: Deep Teal (`#0D9488`), Sky Blue (`#0EA5E9`), Amber Gold (`#F59E0B`).

4. **CHART-SPECIFIC EXCELLENCE**:
   - **BAR CHARTS**: Add clean, bold value labels exactly on top of the bars so they can be read precisely without looking at the Y-axis:
     Use `ax.bar_label(bars, padding=3, fontsize=9, fontweight='semibold', color='#334155')` or loop to place text values at the top of the bars.
   - **PIE CHARTS**: Never make a flat standard pie chart. Always make a sleek **Donut Chart** by setting `wedgeprops=dict(width=0.4, edgecolor='w')` which creates a clean cutout circle in the middle.
   - **LINE CHARTS**: Use thick curves (`linewidth=2.5`), elegant circular markers (`marker='o', markersize=6, markerfacecolor='white', markeredgewidth=2`), and smooth lines.

5. **TYPOGRAPHY & LABELS**:
   - Use clean, bold titles with proper spacing. Use a modern sans-serif font family.
   - Set title with a bold weight: `ax.set_title('Title Here', pad=20, fontsize=14, fontweight='bold', color='#1E293B')`
   - Rotate long X-axis labels by 15 or 30 degrees to completely prevent collisions or text clipping: `plt.xticks(rotation=15, ha='right')`

6. **EXECUTION & CLEANUP**:
   - Save the final image to: '{output_path}'
   - Do NOT use `plt.show()`, `plt.style.use()`, or any interactive backend commands.
   - Call `plt.tight_layout()` right before saving to prevent label truncation.
   - Return ONLY the executable python code. No markdown formatting, no explanation text.

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
        
        persona_str = ""
        if self.persona_memory:
            persona_str = self.persona_memory.get_persona_context("Visualizer")
        
        code_response = self.llm.invoke(self.code_prompt.format(
            context=full_context, 
            answer=answer, 
            output_path=output_path,
            persona=persona_str
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
