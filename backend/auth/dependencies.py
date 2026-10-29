"""
Request dependencies that turn an access token into the signed-in user.

The token is read from `Authorization: Bearer <jwt>` first and from an `access_token` query
parameter second: the browser's EventSource, which the frontend uses for /api/stream and
/api/crawl/stream, cannot send headers. Every failure is a 401 with `WWW-Authenticate: Bearer`.

main.py attaches require_user to the whole /api router, so every existing endpoint is protected
without touching api/routes.py; PUBLIC_API_PATHS are the exceptions.
"""
from __future__ import annotations

import logging

from fastapi import Header, HTTPException, Query, Request, status

from auth.security import InvalidToken, decode_access_token
from auth.store import get_user_by_id, public_user

logger = logging.getLogger(__name__)

# Health stays public so the Sidebar's Online/Offline indicator works before sign-in.
PUBLIC_API_PATHS = {"/api/health"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def _bearer_token(authorization: str | None) -> str | None:
    """The token from an `Authorization: Bearer <token>` header (scheme case-insensitive), else None."""
    if not authorization:
        return None
    scheme, _, credentials = authorization.strip().partition(" ")
    credentials = credentials.strip()
    if scheme.lower() != "bearer" or not credentials:
        return None
    return credentials


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> dict:
    token = _bearer_token(authorization) or (access_token or "").strip()
    if not token:
        raise _unauthorized("Not authenticated")
    try:
        claims = decode_access_token(token)
    except InvalidToken as e:
        if e.reason == "expired":
            raise _unauthorized("Session expired. Please sign in again.") from None
        raise _unauthorized("Invalid token") from None
    # Load the account rather than trusting the claims, so a deleted user's token stops working.
    row = get_user_by_id(claims["sub"])
    if row is None:
        raise _unauthorized("Invalid token")
    user = public_user(row)
    request.state.user = user
    return user


def require_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> dict | None:
    """Router-level guard: get_current_user, except for PUBLIC_API_PATHS."""
    if request.url.path in PUBLIC_API_PATHS:
        return None
    return get_current_user(request, authorization, access_token)
