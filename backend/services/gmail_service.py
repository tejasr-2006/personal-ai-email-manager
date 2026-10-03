"""
Gmail integration (Gmail API + OAuth).

How authentication works
------------------------
* The browser-based OAuth login is done ONCE on your own computer with
  `python scripts/gmail_auth.py`. That creates `token.json`.
* The running server only loads that token (from the GOOGLE_TOKEN_JSON
  environment variable or from the token file) and refreshes it silently.
* The server never opens a browser, so it can run safely on Render.

This module only talks to Gmail. Saving to MongoDB and AI classification
happen in `sync_service.py`.
"""

import base64
import json
import os
import re
import threading
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Dict, List, Optional

import google_auth_httplib2
import httplib2
from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import settings
from utils.email_cleaner import clean_email_body
from utils.logger import get_logger

logger = get_logger(__name__)

# gmail.modify is needed so we can mark messages as read in Gmail too.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

HTTP_TIMEOUT_SECONDS = 30
PAGE_SIZE = 100  # Gmail's maximum per list request


class GmailAuthError(Exception):
    """Gmail is not authorised (or the token was revoked / expired)."""


class GmailAPIError(Exception):
    """Gmail answered with an error. `status` is the HTTP status if known."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


# ----------------------------------------------------------------------
# credentials
# ----------------------------------------------------------------------

_creds: Optional[Credentials] = None
_creds_lock = threading.Lock()


def is_configured() -> bool:
    """True if a token is available (does not call Google)."""
    return bool(settings.GOOGLE_TOKEN_JSON) or os.path.isfile(settings.GOOGLE_TOKEN_FILE)


def _load_token() -> Optional[Credentials]:
    try:
        if settings.GOOGLE_TOKEN_JSON:
            return Credentials.from_authorized_user_info(json.loads(settings.GOOGLE_TOKEN_JSON), SCOPES)
        if os.path.isfile(settings.GOOGLE_TOKEN_FILE):
            return Credentials.from_authorized_user_file(settings.GOOGLE_TOKEN_FILE, SCOPES)
    except (ValueError, KeyError, OSError) as exc:
        logger.error("Gmail token could not be read: %s", type(exc).__name__)
    return None


def get_credentials() -> Credentials:
    """Return valid credentials, refreshing them if needed. Raises GmailAuthError."""
    global _creds

    with _creds_lock:
        if _creds is None:
            _creds = _load_token()

        if _creds is None:
            raise GmailAuthError(
                "Gmail is not authorised yet. Run `python scripts/gmail_auth.py` locally, "
                "then provide the token via GOOGLE_TOKEN_JSON (or GOOGLE_TOKEN_FILE)."
            )

        if not _creds.valid:
            if _creds.refresh_token:
                try:
                    _creds.refresh(Request())
                    logger.info("Gmail access token refreshed.")
                except RefreshError as exc:
                    _creds = None
                    logger.error("Gmail token refresh failed: %s", type(exc).__name__)
                    raise GmailAuthError(
                        "Gmail authorisation expired or was revoked. "
                        "Run `python scripts/gmail_auth.py` again and update the token."
                    ) from exc
                except GoogleAuthError as exc:
                    raise GmailAuthError("Could not refresh the Gmail token.") from exc
            else:
                _creds = None
                raise GmailAuthError("Gmail token has no refresh token. Re-run scripts/gmail_auth.py.")

        return _creds


def get_gmail_service():
    """Build a Gmail API client (with a request timeout)."""
    creds = get_credentials()
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS))
    return build("gmail", "v1", http=http, cache_discovery=False)


# ----------------------------------------------------------------------
# calling Gmail safely
# ----------------------------------------------------------------------

def _execute(request):
    """Run a Gmail request, retrying transient errors and translating failures."""
    try:
        return request.execute(num_retries=2)
    except HttpError as exc:
        status = getattr(exc.resp, "status", None)
        logger.warning("Gmail API error (status %s).", status)
        if status in (401, 403):
            message = ("Gmail rejected the request. Check that the Gmail API is enabled and "
                       "that the token has the gmail.modify scope.")
        elif status == 429:
            message = "Gmail rate limit reached. Try again in a minute."
        elif status == 404:
            message = "Gmail message not found."
        else:
            message = f"Gmail API error (status {status})."
        raise GmailAPIError(message, status) from exc
    except RefreshError as exc:
        raise GmailAuthError("Gmail authorisation expired or was revoked.") from exc
    except (OSError, httplib2.HttpLib2Error) as exc:
        logger.warning("Network problem talking to Gmail: %s", type(exc).__name__)
        raise GmailAPIError("Could not reach Gmail. Try again shortly.") from exc


# ----------------------------------------------------------------------
# parsing a Gmail message
# ----------------------------------------------------------------------

def get_header(headers: List[Dict[str, str]], header_name: str) -> str:
    header_name = header_name.lower()
    for header in headers:
        if header.get("name", "").lower() == header_name:
            return header.get("value", "")
    return ""


def _decode_part(part: Dict[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    try:
        # Gmail often omits base64 padding; add it or decoding fails.
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (ValueError, TypeError):
        logger.warning("Could not base64-decode an email part.")
        return ""

    content_type = get_header(part.get("headers", []), "Content-Type")
    match = re.search(r'charset="?([\w\-]+)', content_type, flags=re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _find_part_text(payload: Dict[str, Any], mime_type: str) -> str:
    """Depth-first search for the first non-empty part of the given MIME type."""
    if payload.get("mimeType", "") == mime_type:
        text = _decode_part(payload)
        if text.strip():
            return text
    for part in payload.get("parts", []) or []:
        text = _find_part_text(part, mime_type)
        if text.strip():
            return text
    return ""


def get_email_body(payload: Dict[str, Any]) -> str:
    """Prefer text/plain; fall back to text/html (HTML-only emails are common)."""
    return _find_part_text(payload, "text/plain") or _find_part_text(payload, "text/html")


def parse_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw Gmail API message into the dict we store."""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    sender = get_header(headers, "From")
    labels = message.get("labelIds", []) or []

    try:
        internal_date = int(message.get("internalDate", 0))
    except (TypeError, ValueError):
        internal_date = 0

    date_header = get_header(headers, "Date")
    if not date_header and internal_date:
        date_header = datetime.fromtimestamp(internal_date / 1000, tz=timezone.utc).isoformat()

    body = clean_email_body(get_email_body(payload))[: settings.MAX_BODY_CHARS]

    return {
        "id": message["id"],
        "thread_id": message.get("threadId"),
        "sender": sender,
        "sender_email": parseaddr(sender)[1],
        "subject": get_header(headers, "Subject"),
        "date": date_header,
        "internal_date": internal_date,
        "snippet": message.get("snippet", ""),
        "body": body,
        "labels": labels,
        "unread": "UNREAD" in labels,
    }


# ----------------------------------------------------------------------
# public functions
# ----------------------------------------------------------------------

def list_message_ids(service, max_results: int, query: Optional[str] = None) -> List[str]:
    """Return up to `max_results` message ids (newest first), following pagination."""
    ids: List[str] = []
    page_token = None

    while len(ids) < max_results:
        params: Dict[str, Any] = {
            "userId": "me",
            "maxResults": min(PAGE_SIZE, max_results - len(ids)),
        }
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        response = _execute(service.users().messages().list(**params))
        ids.extend(m["id"] for m in response.get("messages", []))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return ids[:max_results]


def fetch_email(service, message_id: str) -> Dict[str, Any]:
    """Download and parse one message."""
    raw = _execute(service.users().messages().get(userId="me", id=message_id, format="full"))
    return parse_message(raw)


def get_emails(max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch and parse recent emails WITHOUT saving or classifying them
    (used by scripts/check_gmail.py).
    """
    service = get_gmail_service()
    emails = []
    for message_id in list_message_ids(service, max_results, settings.GMAIL_QUERY):
        try:
            emails.append(fetch_email(service, message_id))
        except GmailAPIError as exc:
            logger.warning("Skipping email %s: %s", message_id, exc)
    return emails


def mark_email_as_read(email_id: str) -> bool:
    """Remove the UNREAD label in Gmail. Returns True on success, never raises."""
    try:
        service = get_gmail_service()
        _execute(
            service.users().messages().modify(
                userId="me", id=email_id, body={"removeLabelIds": ["UNREAD"]}
            )
        )
        return True
    except (GmailAuthError, GmailAPIError) as exc:
        logger.warning("Could not mark email %s as read in Gmail: %s", email_id, exc)
        return False
