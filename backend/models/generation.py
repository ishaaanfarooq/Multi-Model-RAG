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
            template="""You are an Expert Financial Data Journalist. Your task is to transform raw context into a HIGHLY STRUCTURED, VISUAL Markdown report.
            
### MANDATORY OUTPUT FORMAT:
1. **Summary**: One punchy sentence about the findings.
2. **Horizontal Rule**: `---`
3. **📊 Comparison Table**: If two or more things are being compared, YOU MUST CREATE A MARKDOWN TABLE. Include columns for 'Metric', 'Entity A', and 'Entity B'.
4. **💰 Key Financials**: Use bullet points to list specific numbers, revenue, or dates found in the context.
5. **💡 Strategic Insights**: Use bullet points with emojis (👉) to explain the 'why' behind the data.
6. **Horizontal Rule**: `---`

### CRITICAL RULES:
- DO NOT write long paragraphs.
- ALWAYS ensure multiple newlines between sections to ensure markdown renders correctly.
- Tables MUST have empty lines before and after them.
- DO NOT mention "the provided text" or "the documents".
- ALWAYS use EMOJIS in headers.
- BOLD all names of companies and large numbers.
- If data is missing for a table cell, use "N/A".

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
