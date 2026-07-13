import logging
import os

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """
    WhatsApp via the Twilio Sandbox.

    Worth understanding before demoing: WhatsApp does not let you message strangers.
    Twilio (like Meta's own Cloud API) enforces an opt-in and a 24-hour session window
    — the recipient must first send `join <sandbox-code>` to the sandbox number, and
    free-form replies are only permitted for 24h after their last message. Outside that
    window WhatsApp requires a pre-approved template.

    So a send can legitimately fail with "recipient has not opted in", and that is a
    platform rule, not a bug in this code. Have anyone you plan to message during a demo
    join the sandbox first.
    """

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        # Twilio's shared sandbox sender
        self.from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        self.client = None
        self._init_error = None

        if not self.account_sid or not self.auth_token:
            self._init_error = (
                "WhatsApp is not configured. Set TWILIO_ACCOUNT_SID and "
                "TWILIO_AUTH_TOKEN in .env."
            )
            logger.warning(self._init_error)
            return

        try:
            from twilio.rest import Client

            self.client = Client(self.account_sid, self.auth_token)
            logger.info("Twilio WhatsApp client initialized.")
        except Exception as e:
            self._init_error = f"Twilio init failed: {e}"
            logger.error(self._init_error)

    @property
    def available(self) -> bool:
        return self.client is not None

    def send(self, to: str, body: str) -> str:
        """`to` is E.164, e.g. +923001234567."""
        if not self.available:
            raise RuntimeError(self._init_error or "WhatsApp is not configured.")

        to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        try:
            msg = self.client.messages.create(
                from_=self.from_number, to=to_addr, body=body
            )
            logger.info(f"Sent WhatsApp to {to} (sid={msg.sid})")
            return msg.sid
        except Exception as e:
            text = str(e)
            # Twilio 63015/63016: no opt-in, or outside the 24h window.
            if "63015" in text or "63016" in text or "not been able to send" in text:
                raise RuntimeError(
                    f"{to} has not joined the WhatsApp sandbox (or the 24-hour window "
                    f"has expired). Ask them to send 'join <your-sandbox-code>' to "
                    f"{self.from_number.replace('whatsapp:', '')} on WhatsApp, then retry."
                ) from e
            raise
