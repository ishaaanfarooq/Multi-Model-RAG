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
5. "Send_Telegram": Choose this if the user is INSTRUCTING you to send a message/text/WhatsApp/Telegram to someone (e.g. "message Ali", "text mom", "telegram Ali the notes", "whatsapp Ali that I'll be late"). All chat/message sends go here.
6. "Workspace_Task": Choose this ONLY if the user wants to SAVE A FILE to disk — write code/a script/program into a file, create a named file, or solve a coding problem and save it (e.g. "make a python file that sorts a list", "write a script to rename files", "create index.html", "solve this and save as sol.py", "open vscode and make a file"). Do NOT pick this just because the user says "make"/"create" — if they want to SEE a chart/graph/plot in the chat rather than save a file, use "Visualize_Data".
7. "Visualize_Data": Choose this if the user wants to SEE a chart/graph/plot/visualization rendered in the chat FROM DATA THEY PROVIDED in the message (e.g. "make a bar chart: Jan 100, Feb 75, Mar 50", "plot these numbers", "graph this data", "chart the sales figures I just gave you"). Note: if the numbers must be looked up first because they are NOT in the message (e.g. "chart Samsung's 2025 revenue"), use "Web_Search" instead.
8. "Read_Email": Choose this if the user is asking ABOUT their inbox or received mail (e.g. "any unread emails?", "summarize my inbox", "what did my supervisor email me?").
9. "Direct_Chat": Choose this ONLY for greetings, small talk, or generic conversational questions that need no external data.
10. "Ambiguous_Query": Choose this if the user's query is highly ambiguous, extremely short (like a single word or acronym), or lacks enough context to perform a meaningful search (e.g., "apple", "the project", "what is AAPL").

Note the difference: sending mail is "Send_Email", but asking about mail you received is "Read_Email". Saving code/text to a file is "Workspace_Task", but drawing a chart from data in the message is "Visualize_Data".

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

            # WhatsApp is disabled — but the model still knows the word and may emit the
            # old "Send_WhatsApp" token. Treat any WhatsApp classification as Telegram
            # so a "whatsapp X" request drafts a Telegram message instead of falling
            # through to search.
            if "Send_WhatsApp" in response or "WhatsApp" in response:
                return "Send_Telegram"

            # Order matters: the action tools are checked first, and the more specific
            # name wins ("Send_Email"/"Read_Email" both contain "Email").
            for tool in (
                "Send_Email",
                # WhatsApp is disabled for now — any "whatsapp/text/message" phrasing is
                # mapped to Send_Telegram in the prompt above. Kept out of the parse list
                # so it can never be selected; re-add it here to bring WhatsApp back.
                "Send_Telegram",
                "Workspace_Task",
                "Visualize_Data",
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
