"""
/api/auth: create an account, sign in, and ask who is signed in.

    POST /register  {name, email, password} -> 201 AuthResponse (the new user is signed in)
    POST /login     {email, password}       -> 200 AuthResponse
    GET  /me        Bearer token            -> 200 {"user": {...}}

Sign-in never reveals whether an account exists: an unknown email gets the same 401 message as a
wrong password, and still pays for one bcrypt check against a dummy hash so the response time is
the same too. Repeated failures for one (client IP, email) are throttled in memory.
Passwords and tokens are never logged.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from auth.dependencies import get_current_user
from auth.security import BCRYPT_MAX_BYTES, create_access_token, hash_password, verify_password
from auth.store import EmailTaken, create_user, get_user_by_email, public_user

logger = logging.getLogger(__name__)

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX = 254
NAME_MIN, NAME_MAX = 2, 60
PASSWORD_MIN_BYTES = 8

# A fixed cost-12 bcrypt hash of a random value nobody knows. Checking an unknown email's password
# against it makes "no such account" take as long as "wrong password".
_DUMMY_HASH = "$2b$12$Cj2GReRQ0/b9cEdNw.1H.ut3d3na1gCICu3IBOnsC0urlx99nzQTC"

INVALID_CREDENTIALS = "Invalid email or password."
EMAIL_TAKEN = "An account with this email already exists."


# ── request / response models ────────────────────────────────────────────────
def _clean_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > EMAIL_MAX:
        raise ValueError(f"Email must be at most {EMAIL_MAX} characters.")
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    return email


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        name = v.strip()
        if not NAME_MIN <= len(name) <= NAME_MAX:
            raise ValueError(f"Name must be {NAME_MIN}-{NAME_MAX} characters.")
        return name

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        size = len(v.encode("utf-8"))
        if size < PASSWORD_MIN_BYTES:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_BYTES} characters.")
        if size > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
        if not any(c.isalpha() for c in v) or not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if not v:
            raise ValueError("Enter your password.")
        return v


class PublicUser(BaseModel):
    id: str
    name: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: PublicUser


class MeResponse(BaseModel):
    user: PublicUser


def _auth_response(row: dict) -> dict:
    user = public_user(row)
    token, expires_in = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user}


# ── sign-in throttle ─────────────────────────────────────────────────────────
MAX_FAILURES = 5
WINDOW_S = 300.0

_failures: dict[tuple[str, str], list[float]] = {}
_throttle_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent(key: tuple[str, str], now: float) -> list[float]:
    """Failures for `key` inside the window; drops the expired ones. Call with the lock held."""
    times = [t for t in _failures.get(key, ()) if now - t < WINDOW_S]
    if times:
        _failures[key] = times
    else:
        _failures.pop(key, None)
    return times


def _retry_after_s(key: tuple[str, str]) -> int:
    """Seconds until `key` may try again; 0 when it is not throttled."""
    now = time.monotonic()
    with _throttle_lock:
        times = _recent(key, now)
        if len(times) < MAX_FAILURES:
            return 0
        return max(1, math.ceil(times[0] + WINDOW_S - now))


def _record_failure(key: tuple[str, str]) -> None:
    now = time.monotonic()
    with _throttle_lock:
        times = _recent(key, now)
        times.append(now)
        _failures[key] = times
        if len(times) == MAX_FAILURES:
            logger.warning(f"Sign-in throttled for {key[1]} from {key[0]}: "
                           f"{MAX_FAILURES} failed attempts in {int(WINDOW_S // 60)} minutes.")
        if len(_failures) > 10_000:   # bound memory under a spray of different emails
            for stale in [k for k, v in _failures.items() if now - v[-1] >= WINDOW_S]:
                del _failures[stale]


def _clear_failures(key: tuple[str, str]) -> None:
    with _throttle_lock:
        _failures.pop(key, None)


def reset_throttle() -> None:
    """Forget every recorded failure (tests)."""
    with _throttle_lock:
        _failures.clear()


# ── routes ───────────────────────────────────────────────────────────────────
# Plain `def`: bcrypt is CPU-bound (~0.2 s at cost 12), so FastAPI runs these in its thread pool
# instead of blocking the event loop that serves the SSE streams.
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    try:
        row = create_user(body.name, body.email, hash_password(body.password))
    except EmailTaken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    logger.info(f"Registered account {row['email']}")
    return _auth_response(row)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request):
    key = (_client_ip(request), body.email)
    wait_s = _retry_after_s(key)
    if wait_s:
        minutes = math.ceil(wait_s / 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(wait_s)},
        )

    row = get_user_by_email(body.email)
    password_ok = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH)
    if row is None or not password_ok:
        _record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    _clear_failures(key)
    logger.info(f"Signed in {row['email']}")
    return _auth_response(row)


@router.get("/me", response_model=MeResponse)
def me(user: dict = Depends(get_current_user)):
    return {"user": user}
