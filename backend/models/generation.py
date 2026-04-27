from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

class GenerationModel:
    """
    Generates the final answer using retrieved context and the user query.
    Prioritizes Gemini with a local Llama fallback.
    """
    def __init__(self, model_name: str = "llama3.2"):
        self.llm = DualLLM(llama_model=model_name)
        
        self.analytical_template = PromptTemplate(
            input_variables=["context", "query"],
            template="""You are a Senior Research Analyst. Your task is to synthesize the provided context into a high-level, data-driven analytical report.

STRICT INSTRUCTIONS:
1. GROUNDING: ONLY use information provided in the context. If specific numbers (like revenue for a specific year) are not in the context, state that the data is unavailable.
2. FORMAT: Write exactly 3 professional paragraphs. Do NOT use lists or bullets.
3. DATA INTEGRITY: Include all relevant financial figures, percentages, and dates found in the context.
4. STYLE: Be authoritative. Do not mention "the context" or "the documents". Just state the analysis.

Context:
{context}

User Query: {query}

Analytical Synthesis:"""
        )

        self.conversational_template = PromptTemplate(
            input_variables=["query"],
            template="""You are a helpful, friendly AI assistant. Answer the user's query directly and concisely. 
If it's a greeting, respond warmly. If it's a general question, be helpful. Keep it to 1-2 sentences.

User Query: {query}

Response:"""
        )

    async def generate_answer(self, query: str, context: list[str] = None, mode: str = "analytical") -> str:
        if mode == "conversational":
            formatted_prompt = self.conversational_template.format(query=query)
        else:
            if not context:
                return "No relevant context found to answer the query."
            context_str = "\n\n---\n\n".join(context)
            formatted_prompt = self.analytical_template.format(context=context_str, query=query)
        
        response = self.llm.invoke(formatted_prompt)
        return response.strip()
