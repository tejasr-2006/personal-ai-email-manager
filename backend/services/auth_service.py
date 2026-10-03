"""
Single-user login with server-side sessions.

How it works
------------
* Login checks AUTH_PASSWORD (constant-time comparison).
* A random 256-bit session token is created and sent to the browser in an
  HttpOnly cookie. JavaScript can never read it.
* MongoDB stores only an HMAC-SHA256 *hash* of the token (keyed with
  SESSION_SECRET), so a database leak does not reveal usable sessions.
* Logout deletes the session, so the cookie stops working immediately.
  Sessions also expire by themselves (absolute lifetime + MongoDB TTL index).
* Changing SESSION_SECRET logs everybody out.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional, Tuple

from config.settings import settings
from services import mongodb_service
from utils.logger import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# password
# ----------------------------------------------------------------------

def verify_password(candidate: str) -> bool:
    """Constant-time check. Hashing first hides the password length."""
    expected = settings.AUTH_PASSWORD
    if not expected:
        return False
    a = hashlib.sha256(candidate.encode("utf-8")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


# ----------------------------------------------------------------------
# brute-force protection (in memory; this is a single-user app)
# ----------------------------------------------------------------------

_failures: Deque[float] = deque()
_failures_lock = threading.Lock()


def lockout_seconds_remaining() -> int:
    """0 if logins are allowed, otherwise seconds until they are."""
    now = time.monotonic()
    with _failures_lock:
        while _failures and now - _failures[0] > settings.LOGIN_LOCKOUT_SECONDS:
            _failures.popleft()
        if len(_failures) >= settings.LOGIN_MAX_FAILURES:
            return max(1, int(settings.LOGIN_LOCKOUT_SECONDS - (now - _failures[0])))
    return 0


def record_failed_login() -> None:
    with _failures_lock:
        _failures.append(time.monotonic())


def clear_failed_logins() -> None:
    with _failures_lock:
        _failures.clear()


# ----------------------------------------------------------------------
# sessions
# ----------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hmac.new(
        settings.SESSION_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _utc_naive(value: datetime) -> datetime:
    """MongoDB hands back naive UTC datetimes."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@mongodb_service.db_guard
def create_session() -> Tuple[str, datetime]:
    """Returns (raw_token_for_cookie, expires_at_utc)."""
    token = secrets.token_urlsafe(32)          # 256 bits of randomness
    now = _now()
    expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)
    mongodb_service.get_sessions_collection().insert_one(
        {"sid_hash": _hash_token(token), "created_at": now, "expires_at": expires_at}
    )
    return token, expires_at


@mongodb_service.db_guard
def validate_session(token: Optional[str]) -> Optional[datetime]:
    """Returns the expiry time if the session is valid, otherwise None."""
    if not token or len(token) > 200 or not settings.auth_configured:
        return None

    sessions = mongodb_service.get_sessions_collection()
    doc = sessions.find_one({"sid_hash": _hash_token(token)})
    if doc is None:
        return None

    expires_at = _utc_naive(doc["expires_at"])
    if expires_at <= _now():
        sessions.delete_one({"_id": doc["_id"]})
        return None
    return expires_at


@mongodb_service.db_guard
def delete_session(token: Optional[str]) -> None:
    if token and settings.SESSION_SECRET:
        mongodb_service.get_sessions_collection().delete_one({"sid_hash": _hash_token(token)})
