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
    def __init__(self, model_name: str = None):
        # Prioritize Gemini for accurate classification
        self.llm = DualLLM(llama_model=model_name)
        
        self.prompt_template = PromptTemplate(
            input_variables=["query"],
            template='''You are an intelligent autonomous Agent Router. Your job is to classify the user's query into EXACTLY ONE of the following tool categories:

1. "Search_Knowledge_Base": Choose this ONLY if the user explicitly asks about uploaded/ingested private documents, a specific website they crawled, or content that clearly came from their personal knowledge base.
2. "Web_Search": Choose this if the user is asking for live or real-time information, facts about public entities, or general world knowledge that a search engine would answer.
3. "Vision_Analysis": Choose this if the user is asking about an image, a picture, a screenshot, or specifically mentions "the image", "what's in the photo", or "read this text" (referring to an uploaded file).
4. "Send_Email": Choose this if the user is INSTRUCTING you to send/write/compose/draft an email or mail to someone (e.g. "email Ali about the meeting", "send a mail to my supervisor").
5. "Send_WhatsApp": Choose this if the user is INSTRUCTING you to send a WhatsApp/text message to someone (e.g. "whatsapp Ali that I'll be late", "text mom").
6. "Read_Email": Choose this if the user is asking ABOUT their inbox or received mail (e.g. "any unread emails?", "summarize my inbox", "what did my supervisor email me?").
7. "Direct_Chat": Choose this ONLY for greetings, small talk, or generic conversational questions that need no external data.
8. "Ambiguous_Query": Choose this if the user's query is highly ambiguous, extremely short (like a single word or acronym), or lacks enough context to perform a meaningful search (e.g., "apple", "the project", "what is AAPL").

Note the difference: sending mail is "Send_Email", but asking about mail you received is "Read_Email".

User Query: "{query}"

Analyze the query and respond with EXACTLY ONE tool name from the list above. Do NOT output any other text.
Tool Selection:'''
        )
        
    def route_query(self, query: str, model_choice: str = "auto") -> str:
        """
        Takes a query and returns the name of the tool to use.
        Ensures the output matches exactly one of the known tools.
        """
        try:
            prompt = self.prompt_template.format(query=query)
            response = self.llm.invoke(prompt, model_choice=model_choice).strip()

            # Order matters: the action tools are checked first, and the more specific
            # name wins ("Send_Email"/"Read_Email" both contain "Email").
            for tool in (
                "Send_Email",
                "Send_WhatsApp",
                "Read_Email",
                "Ambiguous_Query",
                "Vision_Analysis",
                "Web_Search",
                "Search_Knowledge_Base",
                "Direct_Chat",
            ):
                if tool in response:
                    return tool

            # The fallback is deliberately a *read-only* tool. An unparseable routing
            # decision must never fall through into something that sends a message.
            logger.warning(f"Router failed to parse strict tool from: {response}")
            return "Search_Knowledge_Base"
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            return "Search_Knowledge_Base"
