from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

class VerificationModule:
    """
    Evaluates the generated response against the retrieved context to ensure 
    it aligns with the source documents and reduces hallucinations.
    """
    def __init__(self, model_name: str = "llama3.2"):
        self.llm = DualLLM(llama_model=model_name)
        self.prompt_template = PromptTemplate(
            input_variables=["context", "answer"],
            template="""You are a verification AI. Determine if the generated Answer is based on the provided Context.
Respond with 'PASS' if the answer is factual and primarily supported by the context. Respond with 'FAIL' if the answer contains significant hallucinations. 

Return your response in the following format:
Result: [PASS or FAIL]
Reason: [One brief sentence explaining why]

Context:
{context}

Answer:
{answer}

Verification Output:"""
        )

    async def verify(self, answer: str, context: list[str], model_choice: str = "auto") -> tuple[bool, str]:
        if not context:
            return False, "No context provided for verification."
            
        context_str = "\n".join(context)
        formatted_prompt = self.prompt_template.format(context=context_str, answer=answer)
        
        response = self.llm.invoke(formatted_prompt, model_choice=model_choice).strip()
        
        # Simple parsing for Result and Reason
        is_valid = "Result: PASS" in response
        reason = "No reason provided."
        if "Reason:" in response:
            reason = response.split("Reason:")[1].strip().split("\n")[0]
            
        return is_valid, reason
