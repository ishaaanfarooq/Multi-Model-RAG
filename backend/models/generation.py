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
            template="""You are an expert AI research assistant. Your job is to give thorough, accurate, and well-written answers based on the provided context.

RULES:
1. Write your answer in clear, well-structured paragraphs (2-4 paragraphs). Do NOT use bullet lists unless the question explicitly asks for a list.
2. Use specific numbers, dates, and facts directly from the context. Do NOT omit data that is present.
3. If the context genuinely does not contain the answer, say so briefly and honestly. Do NOT fabricate figures.
4. Write naturally - like a knowledgeable analyst explaining to a colleague.
5. Do NOT begin your answer with "I don't know" or "I couldn't find" if the context contains relevant information.
6. Aim to be comprehensive and insightful.

Context:
{context}

Question: {query}

Answer:"""
        )

    async def generate_answer(self, query: str, context: list[str]) -> str:
        if not context:
            return "No relevant context found to answer the query."
            
        context_str = "\n\n---\n\n".join(context)
        formatted_prompt = self.prompt_template.format(context=context_str, query=query)
        
        response = self.llm.invoke(formatted_prompt)
        return response.strip()
