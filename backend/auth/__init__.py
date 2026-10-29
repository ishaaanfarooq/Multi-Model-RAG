"""
JWT authentication for the Praxis API.

    settings.py      secret, lifetime and storage paths, read from the environment on every call
    security.py      bcrypt password hashing, access-token encode/decode
    store.py         user accounts in SQLite ({DATA_DIR}/users.db)
    dependencies.py  get_current_user / require_user, the guard on every /api/* route
    routes.py        /api/auth/register, /api/auth/login, /api/auth/me

Auth controls access only: the knowledge base, notebook, personas and cache stay shared.
"""
