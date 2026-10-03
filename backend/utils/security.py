"""
Request authentication for the API.

A request is allowed if EITHER:
  1. it carries a valid login-session cookie (the browser / React app), or
  2. it carries the correct `X-API-Key` header (server-to-server use only -
     the key lives in Render's environment and is never sent to the browser).

Anything else gets 401. If neither AUTH_PASSWORD/SESSION_SECRET nor API_KEY
is configured, nothing can authenticate, i.e. the API fails CLOSED.
"""

import secrets
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from config.settings import settings
from services import auth_service

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def enforce_origin(request: Request) -> None:
    """
    CSRF defence for cookie-authenticated requests that change something.

    The session cookie is SameSite=None in production (needed for Vercel ->
    Render), so the browser would attach it even to a request started by an
    evil website. Browsers always send an Origin header on such requests,
    and evil sites cannot forge it, so we only accept our own frontend.
    """
    if request.method in SAFE_METHODS:
        return
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin not in settings.ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to make this request from this origin.",
        )


def _api_key_is_valid(candidate: Optional[str]) -> bool:
    expected = settings.API_KEY
    if not expected or not candidate:
        return False
    return secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def require_session(request: Request) -> None:
    """Browser session only (used by /auth/me)."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if auth_service.validate_session(token) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in.")
    enforce_origin(request)


def require_auth(request: Request, x_api_key: Optional[str] = Header(default=None)) -> None:
    """Dependency for every endpoint that touches email data."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token and auth_service.validate_session(token) is not None:
        enforce_origin(request)
        return

    if _api_key_is_valid(x_api_key):
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in.")
