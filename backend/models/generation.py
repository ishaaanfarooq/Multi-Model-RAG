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
            template="""You are an expert AI assistant that provides detailed, helpful, and natural conversational answers based heavily on the provided context.
If the exact answer isn't in the context, but the context provides highly relevant information, synthesize what you CAN tell the user based on the context. Only say you don't know if the context is completely irrelevant.
            
Context:
{context}

Question: {query}
Answer:"""
        )

    async def generate_answer(self, query: str, context: list[str]) -> str:
        if not context:
            return "No relevant context found to answer the query."
            
        context_str = "\n\n".join(context)
        formatted_prompt = self.prompt_template.format(context=context_str, query=query)
        
        response = self.llm.invoke(formatted_prompt)
        return response
