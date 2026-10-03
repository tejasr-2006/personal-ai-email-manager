"""
Email API. Every endpoint the frontend uses is kept:

    GET    /emails/                       list (bare JSON array)
    GET    /emails/high-priority
    GET    /emails/action-required
    GET    /emails/category/{category}
    GET    /emails/briefing               {"briefing": "..."}
    POST   /emails/sync                   {"message": ..., "count": ...}
    PATCH  /emails/{email_id}/read        {"message": ...}

Errors are raised as exceptions (DatabaseUnavailable, GmailAuthError, ...)
and converted to clean JSON responses in main.py.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from config.settings import settings
from models.email import (
    BriefingResponse,
    EmailOut,
    MarkReadResponse,
    SyncResponse,
)
from services import ai_service, gmail_service, mongodb_service, sync_service
from utils.logger import get_logger
from utils.security import require_api_key

logger = get_logger(__name__)

router = APIRouter(
    prefix="/emails",
    tags=["Emails"],
    dependencies=[Depends(require_api_key)],
)

LimitQuery = Query(default=None, ge=1, le=5000, description="Maximum emails to return")


@router.get("/", response_model=List[EmailOut])
def get_all_emails(limit: Optional[int] = LimitQuery):
    return mongodb_service.list_emails(limit=limit)


@router.get("/high-priority", response_model=List[EmailOut])
def get_high_priority_emails(limit: Optional[int] = LimitQuery):
    return mongodb_service.list_emails({"priority": "high"}, limit)


@router.get("/action-required", response_model=List[EmailOut])
def get_action_required_emails(limit: Optional[int] = LimitQuery):
    return mongodb_service.list_emails({"action_required": True}, limit)


@router.get("/category/{category}", response_model=List[EmailOut])
def get_emails_by_category(
    category: str = Path(min_length=1, max_length=40, pattern=r"^[A-Za-z_\-]+$"),
    limit: Optional[int] = LimitQuery,
):
    return mongodb_service.list_emails({"category": category.lower()}, limit)


@router.get("/briefing", response_model=BriefingResponse)
def get_daily_briefing():
    emails = mongodb_service.list_emails(limit=20)
    return {"briefing": ai_service.generate_daily_briefing(emails)}


@router.post("/sync", response_model=SyncResponse)
def sync_emails(
    max_results: Optional[int] = Query(
        default=None, ge=1, le=settings.SYNC_MAX_EMAILS_LIMIT,
        description="How many recent Gmail messages to check (default from SYNC_MAX_EMAILS)",
    ),
):
    return sync_service.sync_emails(max_results)


@router.patch("/{email_id}/read", response_model=MarkReadResponse)
def mark_as_read(email_id: str = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")):
    if mongodb_service.get_email(email_id) is None:
        raise HTTPException(status_code=404, detail="Email not found.")

    gmail_updated = gmail_service.mark_email_as_read(email_id)
    mongodb_service.mark_read(email_id)

    return {"message": "Email marked as read", "gmail_updated": gmail_updated}
