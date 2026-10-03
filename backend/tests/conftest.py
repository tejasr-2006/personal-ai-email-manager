"""
Offline test setup: no real MongoDB, Gmail or Gemini is ever contacted.
Run with:  pip install -r requirements-dev.txt  &&  pytest
"""

import sys
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from services import mongodb_service  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Ignore whatever is in a developer's real .env."""
    monkeypatch.setattr(settings, "MONGODB_URI", "mongodb://unused-in-tests")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "SYNC_TIME_BUDGET_SECONDS", 60)


@pytest.fixture
def collection(monkeypatch):
    """An in-memory MongoDB collection with the real indexes created."""
    coll = mongomock.MongoClient().test_db.emails
    mongodb_service.ensure_indexes(coll)
    monkeypatch.setattr(mongodb_service, "get_collection", lambda: coll)
    return coll


@pytest.fixture
def client(collection):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def make_email(email_id="e1", **overrides):
    email = {
        "id": email_id,
        "thread_id": "t1",
        "sender": "Recruiter <jobs@example.com>",
        "sender_email": "jobs@example.com",
        "subject": "Interview invitation",
        "date": "Fri, 02 Oct 2026 10:00:00 +0000",
        "internal_date": 1_790_000_000_000,
        "snippet": "Please join us",
        "body": "Please join us for an interview.",
        "labels": ["INBOX", "UNREAD"],
        "unread": True,
        "category": "recruitment",
        "priority": "high",
        "summary": "Interview invite",
        "action_required": True,
        "action_type": "interview",
        "action_text": "Reply to confirm",
        "deadline": None,
        "classification_source": "ai",
    }
    email.update(overrides)
    return email
