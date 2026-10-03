"""
MongoDB access layer.

* One shared MongoClient (created on first use, never at import time).
* Connection problems become `DatabaseUnavailable` (routes turn it into 503).
* Indexes are created once, including a UNIQUE index on the Gmail message id
  so the same email can never be stored twice.
* The connection string is never logged or returned.
"""

import functools
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_client: Optional[MongoClient] = None
_client_lock = threading.Lock()
_indexes_ready = False


class DatabaseUnavailable(Exception):
    """MongoDB is not configured or cannot be reached."""


# ----------------------------------------------------------------------
# connection handling
# ----------------------------------------------------------------------

def get_client() -> MongoClient:
    """Return the shared client, creating it on first use."""
    global _client

    if not settings.MONGODB_URI:
        raise DatabaseUnavailable("MongoDB is not configured (MONGODB_URI is missing).")

    with _client_lock:
        if _client is None:
            _client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=20000,
                maxPoolSize=10,
                appname="personal-ai-email-manager",
            )
            logger.info("MongoDB client created.")
    return _client


def get_collection():
    """Return the emails collection (indexes are ensured on first call)."""
    global _indexes_ready

    try:
        collection = get_client()[settings.MONGODB_DB_NAME][settings.MONGODB_COLLECTION]
        if not _indexes_ready:
            ensure_indexes(collection)
            _indexes_ready = True
        return collection
    except DatabaseUnavailable:
        raise
    except PyMongoError as exc:
        logger.error("MongoDB connection problem: %s: %s", type(exc).__name__, exc)
        raise DatabaseUnavailable("Database is temporarily unavailable.") from exc


def db_guard(func):
    """Convert any PyMongo error into DatabaseUnavailable."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DatabaseUnavailable:
            raise
        except PyMongoError as exc:
            logger.error("MongoDB error in %s: %s: %s", func.__name__, type(exc).__name__, exc)
            raise DatabaseUnavailable("Database is temporarily unavailable.") from exc

    return wrapper


@db_guard
def ping() -> bool:
    get_client().admin.command("ping")
    return True


def close_client() -> None:
    global _client, _indexes_ready
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
        _indexes_ready = False


# ----------------------------------------------------------------------
# indexes + one-off migration
# ----------------------------------------------------------------------

def ensure_indexes(collection) -> None:
    """Create indexes (idempotent). Problems are logged, not fatal."""

    wanted = [
        ([("id", ASCENDING)], {"unique": True, "name": "uniq_email_id"}),
        ([("internal_date", DESCENDING)], {"name": "by_date"}),
        ([("priority", ASCENDING), ("internal_date", DESCENDING)], {"name": "by_priority_date"}),
        ([("action_required", ASCENDING), ("internal_date", DESCENDING)], {"name": "by_action_date"}),
        ([("category", ASCENDING), ("internal_date", DESCENDING)], {"name": "by_category_date"}),
        ([("classification_source", ASCENDING)], {"name": "by_classification_source"}),
    ]

    for keys, options in wanted:
        try:
            collection.create_index(keys, **options)
        except DuplicateKeyError:
            logger.error(
                "Cannot create unique index '%s': duplicate emails already exist. "
                "Remove the duplicates in MongoDB and restart.", options["name"]
            )
        except PyMongoError as exc:
            if options.get("unique"):
                logger.error("Index '%s' failed: %s", options["name"], type(exc).__name__)
            else:
                logger.warning("Index '%s' failed: %s", options["name"], type(exc).__name__)

    _backfill_internal_date(collection)


def _backfill_internal_date(collection) -> None:
    """
    Older documents only have the raw `Date` header. Add a sortable
    `internal_date` (milliseconds since epoch) to them once.
    """
    try:
        updated = 0
        for doc in list(collection.find({"internal_date": {"$exists": False}}, {"id": 1, "date": 1})):
            try:
                millis = int(parsedate_to_datetime(doc.get("date", "")).timestamp() * 1000)
            except Exception:
                millis = 0
            collection.update_one({"_id": doc["_id"]}, {"$set": {"internal_date": millis}})
            updated += 1
        if updated:
            logger.info("Backfilled internal_date on %d older emails.", updated)
    except PyMongoError as exc:
        logger.warning("internal_date backfill skipped: %s", type(exc).__name__)


# ----------------------------------------------------------------------
# reads
# ----------------------------------------------------------------------

_NO_ID = {"_id": 0}


@db_guard
def list_emails(query: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Newest first. `_id` is excluded from every result."""
    cursor = (
        get_collection()
        .find(query or {}, _NO_ID)
        .sort("internal_date", DESCENDING)
        .limit(limit or settings.LIST_DEFAULT_LIMIT)
    )
    return list(cursor)


@db_guard
def get_email(email_id: str) -> Optional[Dict[str, Any]]:
    return get_collection().find_one({"id": email_id}, _NO_ID)


@db_guard
def get_existing_sources(ids: Iterable[str]) -> Dict[str, Optional[str]]:
    """Which of these Gmail ids are already stored? -> {id: classification_source}"""
    ids = list(ids)
    if not ids:
        return {}
    found = get_collection().find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "classification_source": 1}
    )
    return {doc["id"]: doc.get("classification_source") for doc in found}


@db_guard
def find_fallback_emails(limit: int) -> List[Dict[str, Any]]:
    """Emails that were classified by the keyword fallback (AI was down)."""
    if limit <= 0:
        return []
    cursor = (
        get_collection()
        .find({"classification_source": "fallback"}, _NO_ID)
        .sort("internal_date", DESCENDING)
        .limit(limit)
    )
    return list(cursor)


@db_guard
def count_emails() -> int:
    return get_collection().count_documents({})


# ----------------------------------------------------------------------
# writes
# ----------------------------------------------------------------------

@db_guard
def save_email(email: Dict[str, Any]) -> bool:
    """
    Insert an email only if it is new (never overwrites existing data such
    as the unread flag). Returns True if inserted, False if it already existed.
    """
    try:
        result = get_collection().update_one(
            {"id": email["id"]}, {"$setOnInsert": email}, upsert=True
        )
        return result.upserted_id is not None
    except DuplicateKeyError:
        return False  # two syncs raced; the other one won


@db_guard
def update_classification(email_id: str, fields: Dict[str, Any]) -> None:
    get_collection().update_one({"id": email_id}, {"$set": fields})


@db_guard
def mark_read(email_id: str) -> bool:
    """Returns False if the email does not exist."""
    result = get_collection().update_one({"id": email_id}, {"$set": {"unread": False}})
    return result.matched_count > 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
