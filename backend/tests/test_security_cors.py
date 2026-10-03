from config.settings import settings
from conftest import ORIGIN, make_email


def test_cors_allows_the_configured_frontend_with_credentials(anon_client):
    response = anon_client.options(
        "/emails/",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == ORIGIN     # exact origin, not *
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unauthorized_origins(anon_client):
    for evil in ("https://evil.example", "https://app.example.test.evil.com", "null"):
        response = anon_client.options(
            "/emails/",
            headers={"Origin": evil, "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in response.headers, evil


def test_cors_never_uses_wildcard_even_on_error_responses(anon_client):
    response = anon_client.get("/emails/", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_wildcard_in_allowed_origins_is_dropped(monkeypatch):
    from config import settings as settings_module
    monkeypatch.setenv("ALLOWED_ORIGINS", "*,https://app.example.test/")
    loaded = settings_module.load_settings()
    assert "*" not in loaded.ALLOWED_ORIGINS
    assert loaded.ALLOWED_ORIGINS == ["https://app.example.test"]
    assert loaded.WILDCARD_ORIGIN_REMOVED is True


def test_error_responses_still_carry_cors_headers(client, monkeypatch):
    from services import mongodb_service

    def crash(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(mongodb_service, "list_emails", crash)
    response = client.get("/emails/", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_server_to_server_api_key_still_works_but_only_when_correct(anon_client, collection, monkeypatch):
    collection.insert_one(make_email())
    monkeypatch.setattr(settings, "API_KEY", "super-secret-key-123")

    assert anon_client.get("/emails/").status_code == 401
    assert anon_client.get("/emails/", headers={"X-API-Key": "wrong"}).status_code == 401
    assert anon_client.get("/emails/", headers={"X-API-Key": "super-secret-key-123"}).status_code == 200


def test_api_is_closed_when_nothing_is_configured(anon_client, collection, monkeypatch):
    """Old behaviour was 'no API_KEY => open'. Now it fails closed."""
    collection.insert_one(make_email())
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "AUTH_PASSWORD", "")
    monkeypatch.setattr(settings, "SESSION_SECRET", "")
    assert anon_client.get("/emails/").status_code == 401
    assert anon_client.get("/emails/", headers={"X-API-Key": ""}).status_code == 401
    assert anon_client.get("/healthz").status_code == 200


def test_logs_redact_secrets(monkeypatch):
    from utils.logger import redact
    monkeypatch.setattr(settings, "AUTH_PASSWORD", "my-very-secret-password")
    text = redact(
        "failed mongodb+srv://bob:hunter2@cluster0.x.mongodb.net/db "
        "AIzaSyA1234567890abcdefghijklmnopqrstuv password=my-very-secret-password"
    )
    assert "hunter2" not in text and "AIzaSy" not in text and "my-very-secret-password" not in text
