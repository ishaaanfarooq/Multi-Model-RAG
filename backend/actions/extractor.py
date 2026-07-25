import json
import logging
import re

logger = logging.getLogger(__name__)

# Instruction-shaped phrases that have no business appearing in retrieved content.
# We do not rely on this to be safe — the architecture is what keeps us safe (untrusted
# text never reaches the extractor, and recipients are allowlisted). This is a detector,
# so an injection attempt gets recorded in the audit log instead of passing silently.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(the\s+)?(previous|prior|above)",
    r"\bsystem\s*[:>]",
    r"\bnew\s+instructions?\b",
    r"you\s+are\s+now\s+",
    r"forward\s+.{0,40}\bto\b\s+\S+@\S+",
    r"\b(send|email|mail|exfiltrate|leak)\b.{0,50}@\S+\.\S+",
    r"</?(system|instruction|prompt)>",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE | re.DOTALL)


def scan_for_injection(text: str) -> list[str]:
    """Return the injection-like phrases found in untrusted text (may be empty)."""
    if not text:
        return []
    return [m.group(0).strip()[:120] for m in _INJECTION_RE.finditer(text)]


EMAIL_PROMPT = """You extract the fields of an email the user has asked to send.

You will be given ONLY the user's own instruction and their address book. You are not
given any documents, web pages, or search results, and you must not invent any.

Address book (the ONLY people who can be emailed):
{directory}

Rules:
1. "recipient" MUST be a name copied exactly from the address book above. If the user
   names someone who is not in the address book, set "recipient" to null.
2. Never output an email address that is not in the address book.
3. Write a short, appropriate "subject".
4. Write the "body" as plain text. If the user told you what to say, use that. If they
   only gave a topic, write 2-4 natural sentences on it. Sign off as the user.
5. Output ONLY a JSON object. No markdown fence, no commentary.

Schema:
{{"recipient": "<name from address book or null>", "subject": "<string>", "body": "<string>"}}

User instruction: "{query}"

JSON:"""


WHATSAPP_PROMPT = """You extract the fields of a WhatsApp message the user has asked to send.

You will be given ONLY the user's own instruction and their address book. You are not
given any documents, web pages, or search results, and you must not invent any.

Address book (the ONLY people who can be messaged):
{directory}

Rules:
1. "recipient" MUST be a name copied exactly from the address book above, and that
   contact must have a whatsapp number. If not found, set "recipient" to null.
2. Write "body" as a short, conversational WhatsApp message (1-3 sentences).
3. Output ONLY a JSON object. No markdown fence, no commentary.

Schema:
{{"recipient": "<name from address book or null>", "body": "<string>"}}

User instruction: "{query}"

JSON:"""


TELEGRAM_PROMPT = """You extract the fields of a Telegram message the user has asked to send.

You will be given ONLY the user's own instruction and their address book. You are not
given any documents, web pages, or search results, and you must not invent any.

Address book (the ONLY people who can be messaged):
{directory}

Rules:
1. "recipient" MUST be a name copied exactly from the address book above, and that
   contact must have telegram. If not found, set "recipient" to null.
2. Write "body" as a short, conversational Telegram message (1-3 sentences).
3. Output ONLY a JSON object. No markdown fence, no commentary.

Schema:
{{"recipient": "<name from address book or null>", "body": "<string>"}}

User instruction: "{query}"

JSON:"""


def _parse_json(raw: str) -> dict:
    """LLMs like to wrap JSON in prose or fences. Dig it out."""
    text = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Model did not return valid JSON. Got: {raw[:200]}")


class ActionExtractor:
    """
    Turns a user instruction into a structured, validated action.

    Deliberately narrow: it is handed the raw user query and the address book, and
    nothing else. Retrieved documents never pass through here, so text injected into a
    crawled page cannot name a recipient, add a recipient, or trigger a send.
    """

    def __init__(self, llm, contacts):
        self.llm = llm
        self.contacts = contacts

    def extract_email(self, query: str, model_choice: str = "auto") -> dict:
        prompt = EMAIL_PROMPT.format(
            directory=self.contacts.directory_for_prompt(), query=query
        )
        data = _parse_json(self.llm.invoke(prompt, model_choice=model_choice))

        name = data.get("recipient")
        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()

        if not name:
            raise LookupError(
                "I couldn't match that person to anyone in your contacts. "
                "Add them under Contacts first — I can only send to saved contacts."
            )

        contact = self.contacts.resolve(name)
        if not contact or not contact.get("email"):
            raise LookupError(
                f"'{name}' isn't a saved contact with an email address. "
                "Add them under Contacts first — I can only send to saved contacts."
            )

        # Belt and braces: even if the model fabricated an address, we send to the one
        # on file for the resolved contact, never to anything the model produced.
        return {
            "recipient_name": contact["name"],
            "to": contact["email"],
            "subject": subject or "(no subject)",
            "body": body,
        }

    def extract_whatsapp(self, query: str, model_choice: str = "auto") -> dict:
        prompt = WHATSAPP_PROMPT.format(
            directory=self.contacts.directory_for_prompt(), query=query
        )
        data = _parse_json(self.llm.invoke(prompt, model_choice=model_choice))

        name = data.get("recipient")
        body = (data.get("body") or "").strip()

        if not name:
            raise LookupError(
                "I couldn't match that person to anyone in your contacts. "
                "Add them (with a WhatsApp number) under Contacts first."
            )

        contact = self.contacts.resolve(name)
        if not contact or not contact.get("phone"):
            raise LookupError(
                f"'{name}' isn't a saved contact with a WhatsApp number. "
                "Add them under Contacts first."
            )

        return {
            "recipient_name": contact["name"],
            "to": contact["phone"],
            "body": body,
        }

    def extract_telegram(self, query: str, model_choice: str = "auto") -> dict:
        prompt = TELEGRAM_PROMPT.format(
            directory=self.contacts.directory_for_prompt(), query=query
        )
        data = _parse_json(self.llm.invoke(prompt, model_choice=model_choice))

        name = data.get("recipient")
        body = (data.get("body") or "").strip()

        if not name:
            raise LookupError(
                "I couldn't match that person to anyone in your contacts. "
                "Add them (with a Telegram chat id) under Contacts first."
            )

        contact = self.contacts.resolve(name)
        if not contact or not contact.get("telegram"):
            raise LookupError(
                f"'{name}' isn't a saved contact with a Telegram chat id. "
                "Add them under Contacts first."
            )

        return {
            "recipient_name": contact["name"],
            "to": contact["telegram"],
            "body": body,
        }
