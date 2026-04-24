from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate

class GenerationModel:
    """
    Generates the final answer using retrieved context and the user query.
    Utilizes Ollama for local LLM inference.
    """
    def __init__(self, model_name: str = "llama3.2"):
        self.llm = Ollama(model=model_name)
        self.prompt_template = PromptTemplate(
            input_variables=["context", "query"],
            template="""You are a Senior Research Analyst. Your task is to synthesize the provided context into a high-level, data-driven analytical report.

STRICT INSTRUCTIONS:
1. FORMAT: Write exactly 3-4 professional paragraphs. Each paragraph should focus on a different aspect of the query.
2. NO LISTS: Do NOT use bullet points or numbered lists. Explain the numbers within the prose.
3. DATA INTEGRITY: Use every specific financial figure, date, and percentage found in the context.
4. STYLE: Be authoritative and direct. Do not say "The context mentions..." or "Based on the text...". Just state the data.
5. COMPLETENESS: If the data for several years or entities is available, ensure you compare them explicitly.

Context:
{context}

User Query: {query}

Analytical Synthesis:"""
        )

    async def generate_answer(self, query: str, context: list[str]) -> str:
        if not context:
            return "No relevant context found to answer the query."
            
        context_str = "\n\n---\n\n".join(context)
        formatted_prompt = self.prompt_template.format(context=context_str, query=query)
        
        response = self.llm.invoke(formatted_prompt)
        return response.strip()
