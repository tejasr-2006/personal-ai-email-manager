from config.settings import settings
from conftest import make_email


def test_api_key_required_when_configured(client, collection, monkeypatch):
    collection.insert_one(make_email())
    monkeypatch.setattr(settings, "API_KEY", "super-secret-key")

    assert client.get("/emails/").status_code == 401
    assert client.get("/emails/", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/emails/", headers={"X-API-Key": "super-secret-key"}).status_code == 200
    # health endpoints stay public so Render can check them
    assert client.get("/healthz").status_code == 200


def test_cors_allows_local_frontend(client):
    response = client.options(
        "/emails/",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_unknown_origin(client):
    response = client.options(
        "/emails/",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_error_responses_still_carry_cors_headers(client, monkeypatch):
    from services import mongodb_service

    def crash(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(mongodb_service, "list_emails", crash)
    response = client.get("/emails/", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_logs_redact_secrets():
    from utils.logger import redact
    text = redact("failed mongodb+srv://bob:hunter2@cluster0.x.mongodb.net/db and AIzaSyA1234567890abcdefghijklmnopqrstuv")
    assert "hunter2" not in text and "AIzaSy" not in text
