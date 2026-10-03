"""
Offline test setup: no real MongoDB, Gmail or Gemini is ever contacted.
Run with:  pip install -r requirements-dev.txt  &&  pytest
"""

import os
import sys
from pathlib import Path

# Must happen BEFORE the app is imported, so a developer's real .env cannot
# change what the tests expect.
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173,https://app.example.test"
os.environ["ENVIRONMENT"] = "development"

import mongomock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from services import auth_service, mongodb_service  # noqa: E402

ORIGIN = "http://localhost:5173"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Ignore whatever is in a developer's real .env."""
    monkeypatch.setattr(settings, "MONGODB_URI", "mongodb://unused-in-tests")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "SYNC_TIME_BUDGET_SECONDS", 60)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", ["http://localhost:5173", "https://app.example.test"])
    monkeypatch.setattr(settings, "AUTH_PASSWORD", PASSWORD)
    monkeypatch.setattr(settings, "SESSION_SECRET", "s" * 48)
    monkeypatch.setattr(settings, "SESSION_MAX_AGE_SECONDS", 3600)
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)      # tests use http://
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 10)
    auth_service.clear_failed_logins()


@pytest.fixture
def collection(monkeypatch):
    """An in-memory MongoDB collection with the real indexes created."""
    coll = mongomock.MongoClient().test_db.emails
    mongodb_service.ensure_indexes(coll)
    monkeypatch.setattr(mongodb_service, "get_collection", lambda: coll)
    return coll


@pytest.fixture
def sessions(monkeypatch):
    """In-memory sessions collection."""
    coll = mongomock.MongoClient().test_db.sessions
    monkeypatch.setattr(mongodb_service, "get_sessions_collection", lambda: coll)
    return coll


@pytest.fixture
def make_client(collection, sessions):
    """Factory for browser-like test clients (Origin header optional)."""
    from main import app

    opened = []

    def factory(origin=ORIGIN):
        test_client = TestClient(app, headers={"Origin": origin} if origin else {})
        test_client.__enter__()
        opened.append(test_client)
        return test_client

    yield factory
    for test_client in opened:
        test_client.__exit__(None, None, None)


@pytest.fixture
def anon_client(make_client):
    """Not logged in."""
    return make_client()


@pytest.fixture
def client(make_client):
    """Logged in as the owner (so the pre-existing tests keep testing the same things)."""
    test_client = make_client()
    response = test_client.post("/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return test_client


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
