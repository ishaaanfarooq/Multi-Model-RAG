import base64
import logging
import os
from email.message import EmailMessage

logger = logging.getLogger(__name__)

# gmail.send   -> compose and send
# gmail.readonly -> list/read the inbox so it can be retrieved over (inbox RAG)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailClient:
    """
    Gmail over OAuth2.

    Degrades gracefully, like the LLM providers do: with no credentials on disk the
    client simply reports itself unavailable rather than crashing the app at import,
    so the rest of the pipeline keeps working.

    First run needs a one-off browser consent (see `authorize.py`), which writes
    token.json. After that it refreshes itself.
    """

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.email_address = None
        self._init_error = None
        self._connect()

    def _connect(self):
        if not os.path.exists(self.token_path):
            self._init_error = (
                "Gmail is not authorized yet. Run: python -m actions.authorize"
            )
            logger.warning(self._init_error)
            return
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_path, "w") as f:
                        f.write(creds.to_json())
                    logger.info("Refreshed Gmail token.")
                else:
                    self._init_error = "Gmail token is invalid. Re-run: python -m actions.authorize"
                    logger.warning(self._init_error)
                    return

            self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            profile = self.service.users().getProfile(userId="me").execute()
            self.email_address = profile.get("emailAddress")
            logger.info(f"Gmail connected as {self.email_address}")
        except Exception as e:
            self._init_error = f"Gmail init failed: {e}"
            logger.error(self._init_error)
            self.service = None

    @property
    def available(self) -> bool:
        return self.service is not None

    def _require(self):
        if not self.available:
            raise RuntimeError(self._init_error or "Gmail is not configured.")

    def send(self, to: str, subject: str, body: str) -> str:
        self._require()
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = self.email_address
        msg["Subject"] = subject
        msg.set_content(body)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Sent email to {to} (id={sent.get('id')})")
        return sent.get("id", "")

    def list_recent(self, max_results: int = 10, query: str = "") -> list[dict]:
        """
        Fetch recent messages as {from, subject, date, snippet, body}.
        `query` accepts Gmail search syntax, e.g. 'is:unread', 'from:supervisor@uni.edu'.
        """
        self._require()
        listing = (
            self.service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
        )
        out = []
        for ref in listing.get("messages", []):
            try:
                out.append(self._fetch(ref["id"]))
            except Exception as e:
                logger.error(f"Failed to fetch message {ref['id']}: {e}")
        return out

    def _fetch(self, message_id: str) -> dict:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        return {
            "id": message_id,
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body": self._extract_body(msg["payload"]),
        }

    def _extract_body(self, payload: dict) -> str:
        """Walk the MIME tree for the text/plain part, falling back to any text."""
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for part in payload.get("parts", []) or []:
            text = self._extract_body(part)
            if text:
                return text

        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""
