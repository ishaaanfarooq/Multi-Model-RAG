import logging
from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate

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
        # We can use Ollama directly for basic classification
        self.llm = Ollama(model=model_name)
        
        self.prompt_template = PromptTemplate(
            input_variables=["query"],
            template='''You are an intelligent autonomous Agent Router. Your job is to classify the user's query into EXACTLY ONE of the following three Tool categories:

1. "Search_Knowledge_Base": Choose this if the user is asking about highly specific private knowledge, companies, code, documents, or content from a specific website they might have ingested.
2. "Web_Search": Choose this if the user is asking for LIVE, real-time information (e.g., current stock prices, news today, weather, recent events) that a static database would not know.
3. "Direct_Chat": Choose this if the user is just saying hello, asking a basic conversational question ("How are you?"), or asking a generic programming/factual question that doesn't need external data.

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
