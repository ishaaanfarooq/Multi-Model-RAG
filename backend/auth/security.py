"""
Password hashing and access tokens.

bcrypt is called directly, not through passlib: passlib 1.7.4 breaks against bcrypt >= 4.1.
bcrypt only reads the first 72 bytes of a password, which is why registration caps passwords at
72 bytes (auth/routes.py) and verify_password rejects anything longer instead of truncating it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from auth.settings import ALGORITHM, jwt_expire_minutes, jwt_secret

logger = logging.getLogger(__name__)

BCRYPT_ROUNDS = 12
BCRYPT_MAX_BYTES = 72


class InvalidToken(Exception):
    """The token cannot be used. `reason` is "expired" or "invalid"."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """False for a wrong password, a malformed hash, or a password bcrypt would silently truncate."""
    try:
        raw = password.encode("utf-8")
        if len(raw) > BCRYPT_MAX_BYTES:
            return False
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        return False


def create_access_token(user: dict, expires_delta: timedelta | None = None) -> tuple[str, int]:
    """Signed HS256 access token for `user` and its lifetime in seconds."""
    lifetime = expires_delta if expires_delta is not None else timedelta(minutes=jwt_expire_minutes())
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "type": "access",
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(claims, jwt_secret(), algorithm=ALGORITHM), int(lifetime.total_seconds())


def decode_access_token(token: str) -> dict:
    """Verified claims, or InvalidToken. The algorithm is pinned so a token cannot choose its own."""
    try:
        claims = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM],
                            options={"require": ["exp", "iat", "sub"]})
    except jwt.ExpiredSignatureError:
        raise InvalidToken("expired") from None
    except jwt.InvalidTokenError:
        raise InvalidToken("invalid") from None
    if claims.get("type") != "access" or not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise InvalidToken("invalid")
    return claims
