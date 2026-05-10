import logging
from core.llm_provider import DualLLM
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

class AgentRouter:
    """
    An autonomous agent router that decides which Tool to use based on the user's query.
    It has three tools:
    1. Web_Search: Live internet access
    2. Search_Knowledge_Base: Existing ingested corpus
    3. Direct_Chat: Casual conversation
    """
    def __init__(self, model_name: str = "llama3.2"):
        # Prioritize Gemini for accurate classification
        self.llm = DualLLM(llama_model=model_name)
        
        self.prompt_template = PromptTemplate(
            input_variables=["query"],
            template='''You are an intelligent autonomous Agent Router. Your job is to classify the user's query into EXACTLY ONE of the following three Tool categories:

1. "Search_Knowledge_Base": Choose this ONLY if the user explicitly asks about uploaded/ingested private documents, a specific website they crawled, or content that clearly came from their personal knowledge base.
2. "Web_Search": Choose this if the user is asking for live or real-time information, facts about public entities, or general world knowledge that a search engine would answer.
3. "Vision_Analysis": Choose this if the user is asking about an image, a picture, a screenshot, or specifically mentions "the image", "what's in the photo", or "read this text" (referring to an uploaded file).
4. "Direct_Chat": Choose this ONLY for greetings, small talk, or generic conversational questions that need no external data.

User Query: "{query}"

Analyze the query and respond with EXACTLY ONE tool name from the list above. Do NOT output any other text.
Tool Selection:'''
        )
        
    def route_query(self, query: str) -> str:
        """
        Takes a query and returns the name of the tool to use.
        Ensures the output matches exactly one of the 3 tools.
        """
        try:
            prompt = self.prompt_template.format(query=query)
            response = self.llm.invoke(prompt).strip()
            
            # Clean up response in case LLM gets chatty
            if "Web_Search" in response:
                return "Web_Search"
            elif "Vision_Analysis" in response:
                return "Vision_Analysis"
            elif "Search_Knowledge_Base" in response:
                return "Search_Knowledge_Base"
            elif "Direct_Chat" in response:
                return "Direct_Chat"
            else:
                # Default safety fallback
                logger.warning(f"Router failed to parse strict tool from: {response}")
                return "Search_Knowledge_Base"
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            return "Search_Knowledge_Base"
