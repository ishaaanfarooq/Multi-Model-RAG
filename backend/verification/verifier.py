from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate

class VerificationModule:
    """
    Evaluates the generated response against the retrieved context to ensure 
    it aligns with the source documents and reduces hallucinations.
    """
    def __init__(self, model_name: str = "llama3.2"):
        self.llm = Ollama(model=model_name)
        self.prompt_template = PromptTemplate(
            input_variables=["context", "answer"],
            template="""You are a verification AI. Determine if the generated Answer is based on the provided Context.
Respond with 'PASS' if the answer is factual and primarily supported by the context. Respond with 'FAIL' ONLY if the answer contains significant, completely fabricated hallucinations that contradict the context. Output EXACTLY 'PASS' or 'FAIL'.

Context:
{context}

Answer:
{answer}

Verification Result (PASS/FAIL):"""
        )

    async def verify(self, answer: str, context: list[str]) -> bool:
        if not context:
            return False
            
        context_str = "\n".join(context)
        formatted_prompt = self.prompt_template.format(context=context_str, answer=answer)
        
        response = self.llm.invoke(formatted_prompt).strip().upper()
        return "PASS" in response
