import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ActionRegistry:
    """
    Holds drafted actions awaiting human approval, and an append-only audit log.

    Drafts live in memory (they are short-lived and tied to a chat turn); the audit
    log is written to disk. The log records *every* attempt, including ones that were
    blocked before a draft was ever shown — that record is what lets you demonstrate
    the injection defenses actually firing, rather than just asserting they exist.
    """

    def __init__(self, audit_path: str = None):
        if audit_path is None:
            data_dir = os.getenv("DATA_DIR", "data")
            os.makedirs(data_dir, exist_ok=True)
            audit_path = os.path.join(data_dir, "action_audit.jsonl")
        self.audit_path = audit_path
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── drafts ────────────────────────────────────────────────────────────
    def create_draft(self, kind: str, payload: dict, origin_query: str) -> dict:
        """kind: 'email' | 'whatsapp'. Nothing is sent here — this only stages it."""
        action_id = f"act_{uuid.uuid4().hex[:10]}"
        draft = {
            "id": action_id,
            "kind": kind,
            "payload": payload,
            "origin_query": origin_query,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._pending[action_id] = draft
        self.audit("drafted", draft)
        return draft

    def get(self, action_id: str) -> dict | None:
        with self._lock:
            return self._pending.get(action_id)

    def resolve(self, action_id: str, status: str, result: str = "") -> dict | None:
        """status: 'sent' | 'rejected' | 'failed'."""
        with self._lock:
            draft = self._pending.pop(action_id, None)
        if not draft:
            return None
        draft["status"] = status
        draft["result"] = result
        draft["resolved_at"] = datetime.now(timezone.utc).isoformat()
        self.audit(status, draft)
        return draft

    def list_pending(self) -> list[dict]:
        with self._lock:
            return list(self._pending.values())

    # ── audit ─────────────────────────────────────────────────────────────
    def audit(self, event: str, data: dict):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **{k: v for k, v in data.items() if k != "payload"},
            "payload": self._redact(data.get("payload", {})),
        }
        try:
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
        logger.info(f"AUDIT [{event}] {data.get('kind', '?')} -> {self._redact(data.get('payload', {}))}")

    def audit_blocked(self, reason: str, kind: str, payload: dict, origin_query: str):
        """A send that never became a draft (unknown recipient, injection, etc.)."""
        self.audit("blocked", {
            "id": f"blk_{uuid.uuid4().hex[:8]}",
            "kind": kind,
            "payload": payload,
            "origin_query": origin_query,
            "status": "blocked",
            "reason": reason,
        })

    @staticmethod
    def _redact(payload: dict) -> dict:
        """Keep the audit log useful without dumping full message bodies into it."""
        out = dict(payload)
        body = out.get("body")
        if isinstance(body, str) and len(body) > 200:
            out["body"] = body[:200] + f"... [{len(body)} chars]"
        return out

    def read_audit(self, limit: int = 100) -> list[dict]:
        if not os.path.exists(self.audit_path):
            return []
        try:
            with open(self.audit_path) as f:
                lines = f.readlines()[-limit:]
            return [json.loads(ln) for ln in lines if ln.strip()]
        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")
            return []
