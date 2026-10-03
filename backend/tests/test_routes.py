from conftest import make_email

from services import gmail_service, mongodb_service
from services.gmail_service import GmailAPIError, GmailAuthError


def seed(collection, *emails):
    for email in emails:
        collection.insert_one(dict(email))


def test_list_is_bare_array_newest_first_and_hides_mongo_id(client, collection):
    seed(collection,
         make_email("old", internal_date=1),
         make_email("new", internal_date=2))
    response = client.get("/emails/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)                    # frontend does Array.isArray(...)
    assert [e["id"] for e in data] == ["new", "old"]
    assert all("_id" not in e for e in data)


def test_empty_database_returns_empty_list(client):
    assert client.get("/emails/").json() == []


def test_filters(client, collection):
    seed(collection,
         make_email("a", priority="high", action_required=True, category="job"),
         make_email("b", priority="low", action_required=False, category="promotion"))
    assert [e["id"] for e in client.get("/emails/high-priority").json()] == ["a"]
    assert [e["id"] for e in client.get("/emails/action-required").json()] == ["a"]
    assert [e["id"] for e in client.get("/emails/category/promotion").json()] == ["b"]
    assert client.get("/emails/category/nothing").json() == []   # used to return null


def test_mark_as_read(client, collection, monkeypatch):
    seed(collection, make_email("e1", unread=True))
    monkeypatch.setattr(gmail_service, "mark_email_as_read", lambda _id: True)
    response = client.patch("/emails/e1/read")
    assert response.status_code == 200
    assert response.json() == {"message": "Email marked as read", "gmail_updated": True}
    assert collection.find_one({"id": "e1"})["unread"] is False


def test_mark_as_read_when_gmail_fails_still_updates_locally(client, collection, monkeypatch):
    seed(collection, make_email("e1", unread=True))
    monkeypatch.setattr(gmail_service, "mark_email_as_read", lambda _id: False)
    response = client.patch("/emails/e1/read")
    assert response.status_code == 200
    assert response.json()["gmail_updated"] is False
    assert collection.find_one({"id": "e1"})["unread"] is False


def test_mark_as_read_unknown_email_is_404(client):
    assert client.patch("/emails/nope/read").status_code == 404


def test_invalid_input_is_422(client):
    assert client.patch("/emails/bad id!/read").status_code == 422
    assert client.post("/emails/sync?max_results=0").status_code == 422
    assert client.post("/emails/sync?max_results=100000").status_code == 422


def test_database_down_is_clean_503(client, monkeypatch):
    def down():
        raise mongodb_service.DatabaseUnavailable("Database is temporarily unavailable.")
    monkeypatch.setattr(mongodb_service, "get_collection", down)
    response = client.get("/emails/")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is temporarily unavailable."}


def test_unexpected_error_is_generic_500_without_details(client, monkeypatch):
    def crash(*a, **k):
        raise RuntimeError("secret-internal-detail mongodb://user:pw@host")
    monkeypatch.setattr(mongodb_service, "list_emails", crash)
    response = client.get("/emails/")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}


def test_briefing_ai_down_is_503(client, collection):
    seed(collection, make_email())
    response = client.get("/emails/briefing")      # no GEMINI_API_KEY in tests
    assert response.status_code == 503
    assert "detail" in response.json()


def test_briefing_with_no_emails(client):
    response = client.get("/emails/briefing")
    assert response.status_code == 200
    assert "No emails" in response.json()["briefing"]


# ----------------------------------------------------------------------
# sync
# ----------------------------------------------------------------------

class FakeMailbox:
    def __init__(self, count):
        self.emails = {
            f"m{i}": make_email(f"m{i}", internal_date=i, subject=f"Subject {i}",
                                body="Internship application deadline 2026-12-01")
            for i in range(count)
        }
        for e in self.emails.values():
            for key in ("category", "priority", "summary", "action_required", "action_type",
                        "action_text", "deadline", "classification_source"):
                e.pop(key)
        self.fetched = []

    def install(self, monkeypatch):
        monkeypatch.setattr(gmail_service, "get_gmail_service", lambda: object())
        monkeypatch.setattr(
            gmail_service, "list_message_ids",
            lambda service, n, q=None: list(self.emails)[:n],
        )

        def fetch(service, message_id):
            self.fetched.append(message_id)
            return dict(self.emails[message_id])
        monkeypatch.setattr(gmail_service, "fetch_email", fetch)


def test_sync_saves_new_emails_and_never_reprocesses(client, collection, monkeypatch):
    mailbox = FakeMailbox(3)
    mailbox.install(monkeypatch)

    first = client.post("/emails/sync")
    assert first.status_code == 200
    body = first.json()
    assert body["message"] == "Emails synced successfully"
    assert body["count"] == 3 and body["new"] == 3 and body["skipped"] == 0
    assert body["fallback_classified"] == 3          # no Gemini key => keyword fallback
    assert collection.count_documents({}) == 3

    mailbox.fetched.clear()
    second = client.post("/emails/sync").json()
    assert second["count"] == 0 and second["skipped"] == 3
    assert mailbox.fetched == []                     # nothing downloaded again


def test_sync_does_not_overwrite_user_changes(client, collection, monkeypatch):
    FakeMailbox(1).install(monkeypatch)
    client.post("/emails/sync")
    collection.update_one({"id": "m0"}, {"$set": {"unread": False}})
    client.post("/emails/sync")
    assert collection.find_one({"id": "m0"})["unread"] is False


def test_unique_index_prevents_duplicates(collection):
    assert mongodb_service.save_email(make_email("dup")) is True
    assert mongodb_service.save_email(make_email("dup")) is False
    assert collection.count_documents({"id": "dup"}) == 1


def test_sync_respects_max_results(client, monkeypatch):
    mailbox = FakeMailbox(10)
    mailbox.install(monkeypatch)
    assert client.post("/emails/sync?max_results=4").json()["new"] == 4


def test_sync_continues_after_one_email_fails(client, collection, monkeypatch):
    mailbox = FakeMailbox(3)
    mailbox.install(monkeypatch)

    def flaky(service, message_id):
        if message_id == "m1":
            raise GmailAPIError("boom", 500)
        return dict(mailbox.emails[message_id])
    monkeypatch.setattr(gmail_service, "fetch_email", flaky)

    body = client.post("/emails/sync").json()
    assert body["new"] == 2 and body["failed"] == 1


def test_sync_gmail_not_authorised_is_503(client, monkeypatch):
    def deny():
        raise GmailAuthError("Gmail is not authorised yet.")
    monkeypatch.setattr(gmail_service, "get_gmail_service", deny)
    response = client.post("/emails/sync")
    assert response.status_code == 503
    assert "not authorised" in response.json()["detail"]


def test_sync_gmail_api_error_is_502(client, monkeypatch):
    monkeypatch.setattr(gmail_service, "get_gmail_service", lambda: object())

    def broken(*a, **k):
        raise GmailAPIError("Gmail rate limit reached.", 429)
    monkeypatch.setattr(gmail_service, "list_message_ids", broken)
    assert client.post("/emails/sync").status_code == 502


def test_ai_circuit_breaker_stops_calling_ai(client, monkeypatch):
    from services import ai_service
    from services.ai_service import AIServiceError
    monkeypatch.setattr(ai_service.settings, "GEMINI_API_KEY", "fake-key-for-test")
    calls = []

    def always_fail(*a, **k):
        calls.append(1)
        raise AIServiceError("down")
    monkeypatch.setattr(ai_service, "_call_gemini", always_fail)
    FakeMailbox(8).install(monkeypatch)

    body = client.post("/emails/sync").json()
    assert body["new"] == 8 and body["fallback_classified"] == 8
    assert len(calls) == 3        # gave up after 3 consecutive failures


def test_fallback_emails_are_reclassified_by_ai_later(client, collection, monkeypatch):
    import json
    from services import ai_service
    FakeMailbox(2).install(monkeypatch)
    client.post("/emails/sync")                       # AI off -> fallback
    assert collection.count_documents({"classification_source": "fallback"}) == 2

    monkeypatch.setattr(ai_service.settings, "GEMINI_API_KEY", "fake-key-for-test")
    reply = json.dumps({"category": "job", "priority": "high", "summary": "AI summary",
                        "action_required": True, "action_type": "application"})
    monkeypatch.setattr(ai_service, "_call_gemini", lambda *a, **k: reply)

    body = client.post("/emails/sync").json()
    assert body["reclassified"] == 2
    assert collection.count_documents({"classification_source": "ai"}) == 2


def test_concurrent_sync_is_refused_politely(client, monkeypatch):
    from services import sync_service
    assert sync_service._sync_lock.acquire(blocking=False)
    try:
        body = client.post("/emails/sync").json()
    finally:
        sync_service._sync_lock.release()
    assert body["status"] == "in_progress" and body["count"] == 0


def test_backfill_adds_internal_date_to_old_documents(collection):
    collection.insert_one({"id": "old", "date": "Fri, 02 Oct 2026 10:00:00 +0000"})
    mongodb_service._backfill_internal_date(collection)
    assert collection.find_one({"id": "old"})["internal_date"] > 0
