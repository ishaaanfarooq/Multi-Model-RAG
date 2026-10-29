"""
JWT authentication: registration, sign-in, token checks and the /api/* guard (auth/*).

main.py is deliberately not imported (it loads the ML models). The `client` fixture builds a small
app with the same wiring: the auth router at /api/auth, and a stand-in /api router guarded by
require_user, exactly as main.py guards api/routes.py. Each test gets its own DATA_DIR.

Run:  cd backend && python -m pytest tests/test_auth.py -v
"""
import logging
import os
import sys
from datetime import timedelta

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import settings, store
from auth.dependencies import require_user
from auth.routes import router as auth_router, reset_throttle
from auth.security import create_access_token

TEST_SECRET = "praxis-test-secret-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"[:64]
PASSWORD = "correct horse 42"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    api = APIRouter()

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.get("/secret")
    def secret(request: Request):
        return {"user": request.state.user}

    app.include_router(api, prefix="/api", dependencies=[Depends(require_user)])
    return app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.delenv("JWT_EXPIRE_MINUTES", raising=False)
    settings.reset_cache()
    reset_throttle()
    yield tmp_path
    settings.reset_cache()
    reset_throttle()


@pytest.fixture
def client(env):
    with TestClient(_build_app()) as c:
        yield c


def register(client, name="Ada Lovelace", email="ada@example.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def login(client, email="ada@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# 1 ─────────────────────────────────────────────────────────────────────────
def test_register_returns_201_with_a_token_and_never_the_hash(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"].count(".") == 2
    assert body["expires_in"] == 1440 * 60
    assert body["user"]["email"] == "ada@example.com" and body["user"]["name"] == "Ada Lovelace"
    assert set(body["user"]) == {"id", "name", "email", "created_at"}
    assert "password_hash" not in r.text and PASSWORD not in r.text
    stored = store.get_user_by_email("ada@example.com")
    assert stored["password_hash"].startswith("$2b$")


# 2 ─────────────────────────────────────────────────────────────────────────
def test_duplicate_email_is_409_in_any_case(client):
    assert register(client, email="Ada@Example.com").status_code == 201
    assert store.get_user_by_email("ada@example.com")["email"] == "ada@example.com", "stored lowercased"
    for email in ("ada@example.com", "ADA@EXAMPLE.COM", "  ada@example.com  "):
        r = register(client, email=email)
        assert r.status_code == 409
        assert r.json()["detail"] == "An account with this email already exists."


# 3 ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("field, value", [
    ("email", "not-an-email"),
    ("email", "ada@localhost"),
    ("email", "a" * 250 + "@x.io"),
    ("password", "abc12"),                       # too short
    ("password", "abcdefghij"),                  # no digit
    ("password", "1234567890"),                  # no letter
    ("password", "a1" + "é" * 36),               # 38 characters but 74 bytes: over bcrypt's 72
    ("name", "A"),
    ("name", "   "),
    ("name", "x" * 61),
])
def test_invalid_registration_is_422(client, field, value):
    data = {"name": "Ada Lovelace", "email": "ada@example.com", "password": PASSWORD, field: value}
    r = client.post("/api/auth/register", json=data)
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][-1] == field


def test_password_limit_counts_bytes_not_characters(client):
    assert register(client, password="a1" + "é" * 35).status_code == 201, "72 bytes is allowed"


# 4 ─────────────────────────────────────────────────────────────────────────
def test_login_right_password_200_wrong_password_and_unknown_email_identical_401(client):
    register(client)
    ok = login(client, email="ADA@example.com")
    assert ok.status_code == 200 and ok.json()["user"]["email"] == "ada@example.com"

    wrong = login(client, password="wrong password 1")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password."}


def test_login_rejects_a_password_bcrypt_would_truncate(client):
    register(client, password="a1" + "x" * 70)                       # exactly 72 bytes
    assert login(client, password="a1" + "x" * 70).status_code == 200
    assert login(client, password="a1" + "x" * 70 + "extra").status_code == 401


# 5 ─────────────────────────────────────────────────────────────────────────
def test_protected_route_needs_a_valid_token_in_header_or_query(client):
    token = register(client).json()["access_token"]

    r = client.get("/api/secret")
    assert r.status_code == 401 and r.json()["detail"] == "Not authenticated"
    assert r.headers["www-authenticate"] == "Bearer"

    r = client.get("/api/secret", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "ada@example.com"
    assert client.get("/api/secret", headers={"Authorization": f"bearer {token}"}).status_code == 200
    assert client.get("/api/secret", params={"access_token": token}).status_code == 200

    for malformed in ("Bearer", "Bearer   ", token, f"Token {token}", "Basic dXNlcjpwYXNz", "Bearer not.a.jwt"):
        r = client.get("/api/secret", headers={"Authorization": malformed})
        assert r.status_code == 401, malformed
        assert r.headers["www-authenticate"] == "Bearer"


# 6 ─────────────────────────────────────────────────────────────────────────
def test_tampered_and_expired_tokens(client):
    body = register(client).json()
    token, user = body["access_token"], body["user"]

    header, payload, signature = token.split(".")
    flipped = signature[:10] + ("A" if signature[10] != "A" else "B") + signature[11:]
    for bad in (f"{header}.{payload}.{flipped}",
                jwt.encode({"sub": user["id"], "type": "access", "iat": 0, "exp": 4102444800}, "x" * 40, algorithm="HS256")):
        r = client.get("/api/secret", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401 and r.json()["detail"] == "Invalid token"

    expired, lifetime = create_access_token(user, expires_delta=timedelta(seconds=-30))
    assert lifetime == -30
    r = client.get("/api/secret", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["detail"] == "Session expired. Please sign in again."


def test_token_of_a_deleted_user_or_wrong_type_is_invalid(client):
    user = register(client).json()["user"]
    ghost, _ = create_access_token({**user, "id": "no-such-user"})
    wrong_type = jwt.encode({"sub": user["id"], "type": "refresh", "iat": 1, "exp": 4102444800},
                            TEST_SECRET, algorithm="HS256")
    for token in (ghost, wrong_type):
        r = client.get("/api/secret", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and r.json()["detail"] == "Invalid token"


# 7 ─────────────────────────────────────────────────────────────────────────
def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


# 8 ─────────────────────────────────────────────────────────────────────────
def test_me_returns_the_signed_in_user(client):
    body = register(client).json()
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 200 and r.json() == {"user": body["user"]}
    assert client.get("/api/auth/me").status_code == 401


# 9 ─────────────────────────────────────────────────────────────────────────
def test_sixth_attempt_after_five_failures_is_429(client, caplog):
    register(client)
    with caplog.at_level(logging.WARNING, logger="auth.routes"):
        for _ in range(5):
            assert login(client, password="wrong password 1").status_code == 401
    assert any("throttled" in rec.getMessage() for rec in caplog.records)

    r = login(client)                                     # even the right password waits
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Too many sign-in attempts. Try again in ")
    assert 0 < int(r.headers["retry-after"]) <= 300

    assert login(client, email="other@example.com", password="x").status_code == 401, "other emails unaffected"
    reset_throttle()
    assert login(client).status_code == 200


def test_successful_sign_in_clears_the_failure_count(client):
    register(client)
    for _ in range(4):
        login(client, password="wrong password 1")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="wrong password 1").status_code == 401
    assert login(client).status_code == 200


# 10 ────────────────────────────────────────────────────────────────────────
def test_secret_is_generated_once_and_reused(env, monkeypatch, caplog):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    settings.reset_cache()
    with caplog.at_level(logging.WARNING, logger="auth.settings"):
        first = settings.jwt_secret()
    secret_file = env / ".jwt_secret"
    assert secret_file.read_text(encoding="utf-8") == first and len(first) >= 64
    assert sum("generated a signing secret" in r.getMessage() for r in caplog.records) == 1

    user = {"id": "u1", "email": "a@b.co", "name": "A"}
    token, _ = create_access_token(user)
    settings.reset_cache()                                # what a backend restart does
    assert settings.jwt_secret() == first
    assert jwt.decode(token, settings.jwt_secret(), algorithms=["HS256"])["sub"] == "u1"


def test_short_or_placeholder_secret_is_not_used(env, monkeypatch):
    for weak in ("too-short", "your_jwt_secret_key_here_xxxxxxxxxxxxxxxx", "x" * 64):
        monkeypatch.setenv("JWT_SECRET_KEY", weak)
        settings.reset_cache()
        assert settings.jwt_secret() != weak


def test_passwords_and_tokens_are_never_logged(client, caplog):
    with caplog.at_level(logging.DEBUG):
        token = register(client).json()["access_token"]
        login(client)
        login(client, password="wrong password 1")
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert PASSWORD not in logged and "wrong password 1" not in logged and token not in logged
    assert "ada@example.com" in logged
