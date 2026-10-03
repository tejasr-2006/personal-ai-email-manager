"""
Sync = Gmail -> AI -> MongoDB.

Rules:
* Only emails that are NOT already in MongoDB are downloaded and classified,
  so the same email is never processed twice.
* If the AI keeps failing, we stop calling it for the rest of this sync
  (circuit breaker) and use the keyword fallback instead.
* A time budget stops one sync from running forever; anything not reached is
  simply picked up by the next sync.
* Only one sync runs at a time.
"""

import threading
import time
from typing import Any, Dict, Optional

from config.settings import settings
from services import ai_service, gmail_service, mongodb_service
from services.gmail_service import GmailAPIError
from utils.logger import get_logger

logger = get_logger(__name__)

_sync_lock = threading.Lock()
AI_FAILURES_BEFORE_SKIPPING = 3


def _empty_result(status: str, message: str) -> Dict[str, Any]:
    return {
        "message": message, "status": status, "count": 0, "new": 0, "skipped": 0,
        "reclassified": 0, "fallback_classified": 0, "failed": 0,
    }


def sync_emails(max_results: Optional[int] = None) -> Dict[str, Any]:
    if not _sync_lock.acquire(blocking=False):
        return _empty_result("in_progress", "A sync is already running.")
    try:
        return _run_sync(max_results or settings.SYNC_MAX_EMAILS)
    finally:
        _sync_lock.release()


def _run_sync(max_results: int) -> Dict[str, Any]:
    started = time.monotonic()
    result = _empty_result("completed", "Emails synced successfully")

    service = gmail_service.get_gmail_service()          # may raise GmailAuthError
    ids = gmail_service.list_message_ids(service, max_results, settings.GMAIL_QUERY)

    existing = mongodb_service.get_existing_sources(ids)  # may raise DatabaseUnavailable
    new_ids = [i for i in ids if i not in existing]
    result["skipped"] = len(ids) - len(new_ids)

    ai_failures = 0

    def classify(email: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal ai_failures
        use_ai = ai_failures < AI_FAILURES_BEFORE_SKIPPING
        classification = ai_service.classify_email(email, use_ai=use_ai)
        if use_ai:
            ai_failures = ai_failures + 1 if classification["classification_source"] == "fallback" else 0
        return classification

    # ---- new emails -------------------------------------------------
    for position, message_id in enumerate(new_ids):
        if time.monotonic() - started > settings.SYNC_TIME_BUDGET_SECONDS:
            result["status"] = "partial"
            result["message"] = (
                f"Sync stopped early after {settings.SYNC_TIME_BUDGET_SECONDS}s; "
                f"{len(new_ids) - position} email(s) will be picked up next time."
            )
            break
        try:
            email = gmail_service.fetch_email(service, message_id)
        except GmailAPIError as exc:
            if exc.status == 404:   # deleted between list and get
                continue
            logger.warning("Failed to download email %s: %s", message_id, exc)
            result["failed"] += 1
            continue

        email.update(classify(email))
        email["classified_at"] = mongodb_service.utc_now_iso()
        email["synced_at"] = mongodb_service.utc_now_iso()

        if mongodb_service.save_email(email):
            result["new"] += 1
            if email["classification_source"] == "fallback":
                result["fallback_classified"] += 1
        else:
            result["skipped"] += 1

    result["count"] = result["new"]

    # ---- retry earlier fallback classifications ------------------------
    if (
        settings.GEMINI_API_KEY
        and ai_failures < AI_FAILURES_BEFORE_SKIPPING
        and result["status"] == "completed"
    ):
        for email in mongodb_service.find_fallback_emails(settings.SYNC_RECLASSIFY_LIMIT):
            classification = classify(email)
            if classification["classification_source"] == "ai":
                classification["classified_at"] = mongodb_service.utc_now_iso()
                mongodb_service.update_classification(email["id"], classification)
                result["reclassified"] += 1
            if ai_failures >= AI_FAILURES_BEFORE_SKIPPING:
                break

    logger.info(
        "Sync finished: %d new, %d skipped, %d reclassified, %d fallback, %d failed (%s).",
        result["new"], result["skipped"], result["reclassified"],
        result["fallback_classified"], result["failed"], result["status"],
    )
    return result
