from fastapi import APIRouter
from services.gmail_service import get_emails
from services.mongodb_service import emails_collection
from services.gmail_service import get_emails
from services.ai_service import generate_daily_briefing

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.get("/")
def get_all_emails():
    emails = list(
        emails_collection.find(
            {},
            {"_id": 0}
        ).sort("date", -1)
    )
    return emails


@router.get("/high-priority")
def get_high_priority_emails():
    emails = list(
        emails_collection.find(
            {"priority": "high"},
            {"_id": 0}
        )
    )
    return emails


@router.get("/action-required")
def get_action_required_emails():
    emails = list(
        emails_collection.find(
            {"action_required": True},
            {"_id": 0}
        )
    )
    return emails


@router.get("/category/{category}")
def get_emails_by_category(category: str):
    emails = list(
        emails_collection.find(
            {"category": category},
            {"_id": 0}
        )
    )

@router.post("/sync")
def sync_emails():
    emails = get_emails(max_results=20)

    return {
        "message": "Emails synced successfully",
        "count": len(emails)
    }
    return emails

@router.post("/sync")
def sync_emails():
    emails = get_emails(max_results=20)

    return {
        "message": "Emails synced successfully",
        "count": len(emails)
    }

@router.get("/briefing")
def get_daily_briefing():

    emails = list(
        emails_collection.find(
            {},
            {"_id": 0}
        ).sort("date", -1).limit(20)
    )

    briefing = generate_daily_briefing(emails)

    return {
        "briefing": briefing
    }

@router.patch("/{email_id}/read")
def mark_as_read(email_id: str):
    mark_email_as_read(email_id)

    emails_collection.update_one(
        {"id": email_id},
        {"$set": {"unread": False}}
    )

    return {"message": "Email marked as read"}