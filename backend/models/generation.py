from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

class GenerationModel:
    """
    Generates the final answer using retrieved context and the user query.
    Prioritizes Gemini with a local Llama fallback.
    Supports inline source citations [1], [2] etc.
    """
    def __init__(self, model_name: str = "llama3.2"):
        self.llm = DualLLM(llama_model=model_name)
        
        self.analytical_template = PromptTemplate(
            input_variables=["context", "query"],
            template="""You are an Expert Research Analyst. Your task is to transform raw context into a HIGHLY STRUCTURED, VISUAL Markdown report WITH inline source citations.

### MANDATORY OUTPUT FORMAT:
1. **Summary**: One punchy sentence about the findings, citing the most relevant source(s) ALWAYS in brackets like [1].
2. **Horizontal Rule**: `---`
3. **📊 Comparison Table**: If the query asks for a comparison, YOU MUST CREATE A MARKDOWN TABLE. 
    - Use the first column for 'Metric'.
    - Use separate columns for EACH entity mentioned in the query.
    - Use the actual names of the entities as headers.
4. **💰 Key Financials**: Use bullet points to list specific numbers, revenue, or dates found in the context. Cite each fact with its source number in brackets, e.g. "Revenue was **$28.9B** [1]".
5. **💡 Strategic Insights**: Use bullet points with emojis (👉) to explain the 'why' behind the data.
6. **Horizontal Rule**: `---`

### CITATION RULES (CRITICAL):
- You MUST cite sources inline using the notation [1], [2], etc. after every claim.
- NEVER use plain numbers like 1 or 2 without brackets.
- EVERY factual claim MUST have at least one citation.
- **DO NOT include a bibliography or list of sources at the end.** The system handles this automatically. Stop writing after the last section.

### FORMATTING RULES:
- DO NOT write long paragraphs. Use bullet points.
- ALWAYS ensure multiple newlines between sections.
- BOLD all names of companies and large numbers.
- If data is missing for a table cell, use "N/A".
- Be extremely careful to map the correct data to the correct entity.

Context:
{context}

User Query: {query}

Analytical Report:"""
        )

        self.conversational_template = PromptTemplate(
            input_variables=["query"],
            template="""You are a helpful, friendly AI assistant. Answer the user's query directly and concisely. 
If it's a greeting, respond warmly. If it's a general question, be helpful. Keep it to 1-2 sentences.

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
        if mode == "conversational":
            formatted_prompt = self.conversational_template.format(query=query)
        else:
            if not context:
                return "No relevant context found to answer the query."
            context_str = self._build_numbered_context(context, sources)
            formatted_prompt = self.analytical_template.format(context=context_str, query=query)
        
        response = self.llm.invoke(formatted_prompt)
        return response.strip()
