import os

from core.llm_provider import DualLLM
from verification.specifics import unsupported_specifics

SPECIFICS_REASON_PREFIX = "The answer states specifics that do not appear in the sources: "


def unsupported_specifics_reason(missing: list[str], limit: int = 5) -> str:
    shown = ", ".join(f"'{m}'" for m in missing[:limit])
    more = f" (and {len(missing) - limit} more)" if len(missing) > limit else ""
    return f"{SPECIFICS_REASON_PREFIX}{shown}{more}."


GENERIC_WARNING = "The AI's answer may contain information not fully supported by the retrieved source documents."


def warning_for(reason: str, fallback: str = GENERIC_WARNING) -> str:
    """The banner shown with a flagged answer. When it was flagged for unsupported specifics the
    banner names them - 'mentions 41.2 and A100, which the sources do not' is something a reader
    can act on. Otherwise each pipeline branch keeps its own wording via `fallback`."""
    if reason and reason.startswith(SPECIFICS_REASON_PREFIX):
        listed = reason[len(SPECIFICS_REASON_PREFIX):].rstrip(".")
        return f"Check before relying on this: the answer mentions {listed}, which do not appear in the retrieved sources."
    return fallback
from langchain_core.prompts import PromptTemplate

class VerificationModule:
    """
    Evaluates the generated response against the retrieved context to ensure 
    it aligns with the source documents and reduces hallucinations.
    """
    def __init__(self, model_name: str = None):
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

    # Support above this: grounded, no model call. Below the lower bound: invented, no
    # model call. Between: ask the model. Measured on the evaluation set the proxy is
    # decisive at the extremes; the 3B judge is lenient and slow (it re-reads every
    # source chunk), so it is spent only where it can change the verdict.
    CHECK_SPECIFICS = os.getenv("VERIFY_SPECIFICS", "1").lower() not in ("0", "false", "no")
    SUPPORT_PASS = 0.75
    SUPPORT_FAIL = 0.30
    JUDGE_CHUNKS = 3
    JUDGE_CHUNK_CHARS = 1500

    async def verify_fast(self, answer: str, context: list[str], model_choice: str = "auto") -> tuple[bool, str]:
        """verify() with a model-free first pass. Same return shape."""
        from core.text_support import lexical_support
        if not context:
            return False, "No context provided for verification."
        support = lexical_support(answer, context)
        if support <= self.SUPPORT_FAIL:
            return False, f"Most answer sentences use words absent from the sources (lexical support {support:.2f})."
        # Concrete claims the sources never mention. Runs BEFORE the auto-pass, because that is where
        # they slipped through: a changed figure leaves every other word supported, and one invented
        # sentence barely moves a long answer's average. Measured (eval/VERIFIER.md).
        if self.CHECK_SPECIFICS:
            missing = unsupported_specifics(answer, context)
            if missing:
                return False, unsupported_specifics_reason(missing)
        if support >= self.SUPPORT_PASS:
            return True, f"Answer sentences are supported by the sources (lexical support {support:.2f})."
        trimmed = [c[: self.JUDGE_CHUNK_CHARS] for c in context[: self.JUDGE_CHUNKS]]
        ok, reason = await self.verify(answer, trimmed, model_choice=model_choice)
        return ok, f"{reason} (lexical support {support:.2f}; model consulted)"

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
