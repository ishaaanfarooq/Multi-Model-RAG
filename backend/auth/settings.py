"""
Authentication settings.

Everything is read from the environment inside functions, not module constants, so tests can
monkeypatch DATA_DIR / JWT_SECRET_KEY per test. load_dotenv() runs here as well: elsewhere it only
runs when core/llm_provider.py is imported, and auth must not depend on import order.

The signing secret resolves in this order:
  1. JWT_SECRET_KEY, when it is at least 32 characters and not a placeholder;
  2. the contents of {DATA_DIR}/.jwt_secret;
  3. a freshly generated secret, written to that file.
Persisting the generated secret means a backend restart does not sign everyone out, even when no
secret was configured. DATA_DIR is gitignored and, in Docker, the action_data volume.
"""
from __future__ import annotations

import logging
import os
import secrets
import threading

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 1440        # 24 hours
MIN_SECRET_LENGTH = 32
SECRET_FILE_NAME = ".jwt_secret"

# Values people paste from examples. Signing with one of them would let anyone forge a token.
_PLACEHOLDERS = {"changeme", "change-me", "change_me", "secret", "jwt_secret", "jwt_secret_key", "your-secret-key"}

_lock = threading.Lock()
_cached_secret: str | None = None


def data_dir() -> str:
    return os.getenv("DATA_DIR", "data")


def db_path() -> str:
    return os.path.join(data_dir(), "users.db")


def secret_file_path() -> str:
    return os.path.join(data_dir(), SECRET_FILE_NAME)


def jwt_expire_minutes() -> int:
    raw = os.getenv("JWT_EXPIRE_MINUTES", "").strip()
    if not raw:
        return DEFAULT_EXPIRE_MINUTES
    try:
        minutes = int(raw)
    except ValueError:
        logger.warning(f"Ignoring JWT_EXPIRE_MINUTES={raw!r}: not a whole number of minutes.")
        return DEFAULT_EXPIRE_MINUTES
    return minutes if minutes > 0 else DEFAULT_EXPIRE_MINUTES


def _is_placeholder(value: str) -> bool:
    v = value.lower()
    return (v in _PLACEHOLDERS or v.startswith("your_") or v.endswith("_here")
            or len(set(v)) <= 2)   # "xxxxxxxx…", "00000000…"


def _usable(value: str | None) -> bool:
    v = (value or "").strip()
    return len(v) >= MIN_SECRET_LENGTH and not _is_placeholder(v)


def _resolve_secret() -> str:
    configured = os.getenv("JWT_SECRET_KEY", "").strip()
    if _usable(configured):
        return configured

    path = secret_file_path()
    try:
        with open(path, encoding="utf-8") as f:
            stored = f.read().strip()
        if _usable(stored):
            return stored
    except FileNotFoundError:
        pass

    generated = secrets.token_urlsafe(64)
    os.makedirs(data_dir(), exist_ok=True)
    try:
        # O_EXCL: if another process wrote the file a moment ago, use its secret instead of
        # overwriting it (that would invalidate the tokens it already issued).
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with open(path, encoding="utf-8") as f:
            stored = f.read().strip()
        if _usable(stored):
            return stored
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(generated)
    logger.warning(
        f"JWT_SECRET_KEY is not set (or shorter than {MIN_SECRET_LENGTH} characters): generated a signing "
        f"secret and saved it to {os.path.abspath(path)}. Set JWT_SECRET_KEY in .env to choose your own."
    )
    return generated


def jwt_secret() -> str:
    global _cached_secret
    with _lock:
        if _cached_secret is None:
            _cached_secret = _resolve_secret()
        return _cached_secret


def reset_cache() -> None:
    """Forget the resolved secret (tests change JWT_SECRET_KEY / DATA_DIR between cases)."""
    global _cached_secret
    with _lock:
        _cached_secret = None
