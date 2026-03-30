from typing import AsyncGenerator
from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

class GenerationModel:
    """
    Generates the final answer using retrieved context and the user query.
    Prioritizes Gemini with a local Llama fallback.
    Supports inline source citations [1], [2] etc.
    """
    def __init__(self, model_name: str = "llama3.2", persona_memory=None):
        self.llm = DualLLM(llama_model=model_name)
        self.persona_memory = persona_memory
        
        self.analytical_template = PromptTemplate(
            input_variables=["context", "query", "persona"],
            template="""You are a Senior Research Analyst. Your goal is to answer the user's query PRECISELY using the provided context.

### 🧠 REASONING & VERIFICATION
- Before writing the final answer, verify that every fact you mention is explicitly supported by the provided [Source X].
- If the context contains conflicting information, mention the conflict clearly.
- If the context doesn't contain enough information to answer fully, state what is missing.

### 🎯 THE DIRECT ANSWER (MANDATORY)
- **Start your response with a clear, direct answer to the user's query.** 
- If the user asks for a specific fact (like fees, dates, or names), PROVIDE IT IMMEDIATELY.
- DO NOT start with "The report provides..." or "Based on the context...". Just answer.

### 📊 DATA VISUALIZATION (TABLES)
- **IF THE DATA IS TABULAR OR CATEGORICAL (e.g., fee structure per branch, comparison, list of specs), YOU MUST USE A MARKDOWN TABLE.**
- Even if the query doesn't explicitly ask for a "comparison", use a table if it makes the data easier to read.
- Use clear headers. For a fee structure, columns might be: **Branch/Program**, **Fee Amount**, **Duration**.

### 🔍 SUPPORTING DETAILS & CONTEXT
- After the direct answer and any tables, provide a **Detailed Analysis** section if there is more relevant information.
- Use bullet points for readability.
- **Skip sections** (like financial metrics or strategic insights) if they are not relevant to the user's specific question.

### 📜 CITATION RULES (STRICT):
- Cite sources as [1], [2] etc. after every factual claim.
- NO bibliography at the end.

### 🎭 USER PERSONA & PREFERENCES
{persona}

Context:
{context}

User Query: {query}

Final Response:"""
        )

        self.conversational_template = PromptTemplate(
            input_variables=["query", "persona"],
            template="""You are a helpful, friendly AI assistant. Answer the user's query directly and concisely. 
If it's a greeting, respond warmly. If it's a general question, be helpful. Keep it to 1-2 sentences.

### 🎭 USER PERSONA & PREFERENCES
{persona}

User Query: {query}

Response:"""
        )

    def _build_numbered_context(self, context: list[str], sources: list[str] = None) -> str:
        """Build context string with numbered source labels for citation."""
        parts = []
        for i, chunk in enumerate(context):
            source_label = ""
            if sources and i < len(sources):
                source_label = f" (from: {sources[i]})"
            parts.append(f"[Source {i+1}]{source_label}:\n{chunk}")
        return "\n\n---\n\n".join(parts)

    async def generate_answer(self, query: str, context: list[str] = None, sources: list[str] = None, mode: str = "analytical") -> str:
        persona_str = ""
        if self.persona_memory:
            persona_str = self.persona_memory.get_persona_context("Generator")
            
        if mode == "conversational":
            formatted_prompt = self.conversational_template.format(query=query, persona=persona_str)
        else:
            if not context:
                return "No relevant context found to answer the query."
            context_str = self._build_numbered_context(context, sources)
            formatted_prompt = self.analytical_template.format(context=context_str, query=query, persona=persona_str)
        
        response = self.llm.invoke(formatted_prompt)
        return response.strip()

    async def generate_answer_stream(self, query: str, context: list[str] = None, sources: list[str] = None, mode: str = "analytical") -> AsyncGenerator[str, None]:
        persona_str = ""
        if self.persona_memory:
            persona_str = self.persona_memory.get_persona_context("Generator")
            
        if mode == "conversational":
            formatted_prompt = self.conversational_template.format(query=query, persona=persona_str)
        else:
            if not context:
                yield "No relevant context found to answer the query."
                return
            context_str = self._build_numbered_context(context, sources)
            formatted_prompt = self.analytical_template.format(context=context_str, query=query, persona=persona_str)
        
        async for chunk in self.llm.astream(formatted_prompt):
            yield chunk
