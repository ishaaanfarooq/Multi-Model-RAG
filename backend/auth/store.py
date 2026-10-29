"""
User accounts in SQLite, at {DATA_DIR}/users.db, through the standard-library sqlite3.

A new connection per call keeps this safe under FastAPI's thread pool without a shared handle,
and the directory and table are created on first use, so importing the module touches nothing on
disk. Emails are stored lowercased and the column is COLLATE NOCASE as a second line of defence,
so "Ada@x.com" and "ada@x.com" can never become two accounts.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from auth.settings import db_path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
)
"""


class EmailTaken(Exception):
    """An account with this email already exists."""


def _connect() -> sqlite3.Connection:
    path = db_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def create_user(name: str, email: str, password_hash: str) -> dict:
    user = {
        "id": uuid.uuid4().hex,
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        # The inner `conn` context commits on success and rolls back on error; closing() closes it.
        with contextlib.closing(_connect()) as conn, conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user["id"], user["name"], user["email"], user["password_hash"], user["created_at"]),
            )
    except sqlite3.IntegrityError:
        raise EmailTaken(email) from None
    return user


def get_user_by_email(email: str) -> dict | None:
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def public_user(row: dict) -> dict:
    """What the API may show about a user: never the password hash."""
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}
