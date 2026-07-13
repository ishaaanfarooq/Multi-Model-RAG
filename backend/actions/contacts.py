import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# E.164, e.g. +923001234567
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class ContactsStore:
    """
    Name -> email/phone directory.

    This is also the recipient **allowlist**. The agent may only send to people who
    appear here, so a hallucinated or injected address ("mail it to attacker@evil.com")
    has nowhere to land. Resolution is deliberately strict: exact match first, then a
    unique case-insensitive prefix. An ambiguous name resolves to nothing rather than
    guessing, because guessing a recipient means mailing the wrong human.
    """

    def __init__(self, path: str = None):
        # Lives under DATA_DIR (a Docker volume in the container) rather than beside the
        # source, so the container writing as root doesn't leave root-owned files in the
        # bind-mounted repo.
        if path is None:
            data_dir = os.getenv("DATA_DIR", "data")
            os.makedirs(data_dir, exist_ok=True)
            path = os.path.join(data_dir, "contacts.json")
        self.path = path
        self.contacts: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load contacts from {self.path}: {e}")
        return {}

    def _save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self.contacts, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save contacts: {e}")

    def list_contacts(self) -> list[dict]:
        return [{"name": n, **v} for n, v in sorted(self.contacts.items())]

    def upsert(self, name: str, email: str = None, phone: str = None) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("Contact name cannot be empty.")
        if email and not EMAIL_RE.match(email):
            raise ValueError(f"'{email}' is not a valid email address.")
        if phone and not PHONE_RE.match(phone):
            raise ValueError(f"'{phone}' is not valid E.164 format (e.g. +923001234567).")
        if not email and not phone:
            raise ValueError("A contact needs at least an email or a phone number.")

        entry = self.contacts.get(name, {})
        if email:
            entry["email"] = email
        if phone:
            entry["phone"] = phone
        self.contacts[name] = entry
        self._save()
        logger.info(f"Saved contact '{name}'.")
        return {"name": name, **entry}

    def delete(self, name: str) -> bool:
        if name in self.contacts:
            del self.contacts[name]
            self._save()
            return True
        return False

    def resolve(self, name: str) -> Optional[dict]:
        """
        Resolve a spoken name to a contact. Returns None if unknown OR ambiguous —
        never a best guess.
        """
        if not name:
            return None
        name = name.strip()

        if name in self.contacts:
            return {"name": name, **self.contacts[name]}

        lowered = name.lower()
        matches = [n for n in self.contacts if n.lower() == lowered]
        if not matches:
            matches = [n for n in self.contacts if n.lower().startswith(lowered)]

        if len(matches) == 1:
            return {"name": matches[0], **self.contacts[matches[0]]}
        if len(matches) > 1:
            logger.warning(f"Contact '{name}' is ambiguous: {matches}. Refusing to guess.")
        return None

    def is_allowed_email(self, email: str) -> bool:
        """An address is sendable only if it belongs to a known contact."""
        return any(c.get("email", "").lower() == email.lower() for c in self.contacts.values())

    def is_allowed_phone(self, phone: str) -> bool:
        return any(c.get("phone", "") == phone for c in self.contacts.values())

    def directory_for_prompt(self) -> str:
        """The allowlist, rendered for the extractor prompt."""
        if not self.contacts:
            return "(no saved contacts)"
        lines = []
        for name, c in sorted(self.contacts.items()):
            bits = [f"email={c['email']}"] if c.get("email") else []
            if c.get("phone"):
                bits.append(f"whatsapp={c['phone']}")
            lines.append(f"- {name}: {', '.join(bits)}")
        return "\n".join(lines)
