import logging
import os

import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    """
    Telegram via the Bot API (https://core.telegram.org/bots/api).

    Chosen over WhatsApp/Twilio for this project because it is free, has no
    per-message session window, and needs no SDK — it's plain HTTPS. The only
    onboarding step is that a person must press Start on the bot once (Telegram
    does not let bots message users who haven't opted in), after which the bot
    can message them at any time.

    Recipients are addressed by numeric `chat_id`, not phone number. Use
    `recent_chats()` (exposed via /api/telegram/chats) to discover the chat_id of
    anyone who has messaged the bot.
    """

    API = "https://api.telegram.org"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._init_error = None
        self.bot_username = None

        if not self.token or self.token == "your_telegram_bot_token_here":
            self._init_error = (
                "Telegram is not configured. Create a bot with @BotFather and set "
                "TELEGRAM_BOT_TOKEN in .env."
            )
            logger.warning(self._init_error)
            self.token = None  # so `available` reports False, not just carrying an error
            return

        try:
            # getMe both validates the token and gives us the bot's @username.
            r = httpx.get(f"{self.API}/bot{self.token}/getMe", timeout=10)
            data = r.json()
            if not data.get("ok"):
                self._init_error = f"Telegram token rejected: {data.get('description')}"
                logger.error(self._init_error)
                self.token = None
                return
            self.bot_username = data["result"].get("username")
            logger.info(f"Telegram connected as @{self.bot_username}")
        except Exception as e:
            self._init_error = f"Telegram init failed: {e}"
            logger.error(self._init_error)
            self.token = None

    @property
    def available(self) -> bool:
        return bool(self.token)

    def send(self, chat_id: str, body: str) -> str:
        """`chat_id` is a numeric Telegram chat id (as a string)."""
        if not self.available:
            raise RuntimeError(self._init_error or "Telegram is not configured.")

        try:
            r = httpx.post(
                f"{self.API}/bot{self.token}/sendMessage",
                json={"chat_id": chat_id, "text": body},
                timeout=15,
            )
            data = r.json()
            if not data.get("ok"):
                desc = data.get("description", "unknown error")
                # 403: the user has never pressed Start on the bot.
                if "bot can't initiate" in desc or "chat not found" in desc or r.status_code == 403:
                    raise RuntimeError(
                        f"Can't message chat {chat_id} — they haven't started the bot yet. "
                        f"Ask them to open @{self.bot_username or '<your bot>'} on Telegram "
                        f"and press Start, then retry."
                    )
                raise RuntimeError(f"Telegram send failed: {desc}")
            msg_id = data["result"].get("message_id")
            logger.info(f"Sent Telegram message to {chat_id} (message_id={msg_id})")
            return str(msg_id)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Telegram send failed: {e}") from e

    def recent_chats(self) -> list[dict]:
        """
        Discovery helper: everyone who has recently messaged the bot, as
        {chat_id, name, username}. Lets a user find the chat_id to save as a
        contact without hunting through Telegram's API by hand.
        """
        if not self.available:
            raise RuntimeError(self._init_error or "Telegram is not configured.")

        r = httpx.get(f"{self.API}/bot{self.token}/getUpdates", timeout=10)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"getUpdates failed: {data.get('description')}")

        seen: dict[str, dict] = {}
        for update in data.get("result", []):
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat", {})
            cid = str(chat.get("id"))
            if not cid or cid in seen:
                continue
            name = " ".join(
                x for x in [chat.get("first_name"), chat.get("last_name")] if x
            ) or chat.get("title") or "(unknown)"
            seen[cid] = {
                "chat_id": cid,
                "name": name,
                "username": chat.get("username"),
            }
        return list(seen.values())
