import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import settings
from conftest import PASSWORD, make_email
from services import auth_service

SESSION_COOKIE = "eml_session"


def login(client, password=PASSWORD):
    return client.post("/auth/login", json={"password": password})


# ---- 1 / 2: login ---------------------------------------------------------

def test_login_succeeds_with_correct_password(anon_client):
    response = login(anon_client)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert SESSION_COOKIE in anon_client.cookies


def test_login_fails_with_wrong_password(anon_client):
    response = login(anon_client, "wrong-password")
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect password."}
    assert SESSION_COOKIE not in anon_client.cookies


def test_login_rejects_empty_or_oversized_input(anon_client):
    assert anon_client.post("/auth/login", json={}).status_code == 422
    assert anon_client.post("/auth/login", json={"password": ""}).status_code == 422
    assert anon_client.post("/auth/login", json={"password": "x" * 5000}).status_code == 422


def test_login_is_disabled_when_auth_is_not_configured(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD", "")
    assert login(anon_client).status_code == 503
    monkeypatch.setattr(settings, "AUTH_PASSWORD", PASSWORD)
    monkeypatch.setattr(settings, "SESSION_SECRET", "too-short")     # < 32 chars
    assert login(anon_client).status_code == 503


def test_repeated_failures_lock_out_even_the_right_password(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 3)
    for _ in range(3):
        assert login(anon_client, "nope").status_code == 401
    locked = login(anon_client)                       # correct password, but locked
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers
    assert SESSION_COOKIE not in anon_client.cookies


# ---- 3 / 4: protection ----------------------------------------------------

PROTECTED = [
    ("GET", "/emails/"), ("GET", "/emails/high-priority"), ("GET", "/emails/action-required"),
    ("GET", "/emails/category/job"), ("GET", "/emails/briefing"), ("POST", "/emails/sync"),
    ("PATCH", "/emails/abc123/read"), ("GET", "/status"), ("GET", "/auth/me"),
]


def test_unauthenticated_requests_get_401_everywhere(anon_client, collection):
    collection.insert_one(make_email())
    for method, path in PROTECTED:
        response = anon_client.request(method, path)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
        assert "recruiter" not in response.text.lower()          # no data leaked


def test_authenticated_user_can_list_emails(anon_client, collection):
    collection.insert_one(make_email("mine"))
    login(anon_client)
    response = anon_client.get("/emails/")
    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == ["mine"]


def test_me_reports_session(anon_client):
    login(anon_client)
    response = anon_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["authenticated"] is True and response.json()["expires_at"]


def test_a_different_browser_has_no_access(make_client, collection):
    """The 'someone else opens my Vercel URL' scenario."""
    collection.insert_one(make_email())
    owner, stranger = make_client(), make_client()
    login(owner)
    assert owner.get("/emails/").status_code == 200
    assert stranger.get("/emails/").status_code == 401
    assert stranger.get("/auth/me").status_code == 401


def test_forged_cookie_values_are_rejected(anon_client):
    for fake in ("garbage", "A" * 43, "x" * 500, ""):
        anon_client.cookies.clear()
        anon_client.cookies.set(SESSION_COOKIE, fake)
        assert anon_client.get("/emails/").status_code == 401


# ---- 5 / 6: logout and expiry ---------------------------------------------

def test_logout_invalidates_the_session_server_side(anon_client, sessions):
    login(anon_client)
    stolen_cookie = anon_client.cookies.get(SESSION_COOKIE)
    assert sessions.count_documents({}) == 1

    assert anon_client.post("/auth/logout").status_code == 200
    assert sessions.count_documents({}) == 0

    # Even a copy of the old cookie is now useless:
    anon_client.cookies.clear()
    anon_client.cookies.set(SESSION_COOKIE, stolen_cookie)
    assert anon_client.get("/emails/").status_code == 401
    assert anon_client.get("/auth/me").status_code == 401


def test_logout_without_session_is_harmless(anon_client):
    assert anon_client.post("/auth/logout").status_code == 200


def test_expired_session_is_rejected_and_removed(anon_client, sessions):
    login(anon_client)
    sessions.update_many({}, {"$set": {"expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)}})
    assert anon_client.get("/emails/").status_code == 401
    assert sessions.count_documents({}) == 0


def test_changing_session_secret_logs_everyone_out(anon_client, monkeypatch):
    login(anon_client)
    assert anon_client.get("/emails/").status_code == 200
    monkeypatch.setattr(settings, "SESSION_SECRET", "z" * 48)
    assert anon_client.get("/emails/").status_code == 401


def test_session_token_is_not_stored_in_plain_text(anon_client, sessions):
    login(anon_client)
    token = anon_client.cookies.get(SESSION_COOKIE)
    stored = sessions.find_one({})
    assert token not in str(stored)
    assert stored["sid_hash"] == auth_service._hash_token(token)


def test_every_login_gets_a_new_session_id(make_client):
    a, b = make_client(), make_client()
    login(a), login(b)
    assert a.cookies.get(SESSION_COOKIE) != b.cookies.get(SESSION_COOKIE)


# ---- cookie flags ---------------------------------------------------------

def test_cookie_is_httponly_and_has_expiry(anon_client):
    header = login(anon_client).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert f"max-age={settings.SESSION_MAX_AGE_SECONDS}" in header
    assert "path=/" in header


def test_production_cookie_is_secure_and_samesite_none(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")
    header = login(anon_client).headers["set-cookie"].lower()
    assert "secure" in header and "samesite=none" in header and "httponly" in header


def test_production_settings_default_to_secure_cookie(monkeypatch):
    from config import settings as settings_module
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.delenv("COOKIE_SAMESITE", raising=False)
    loaded = settings_module.load_settings()
    assert loaded.COOKIE_SECURE is True and loaded.COOKIE_SAMESITE == "none"
    assert loaded.ENABLE_DOCS is False
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("COOKIE_SECURE", "false")          # SameSite=None without Secure is invalid
    assert settings_module.load_settings().COOKIE_SECURE is True


def test_logout_clears_cookie_with_matching_attributes(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    login(anon_client)
    header = anon_client.post("/auth/logout").headers["set-cookie"].lower()
    assert "max-age=0" in header and "samesite=none" in header and "secure" in header


def test_private_responses_are_not_cacheable(client):
    assert client.get("/emails/").headers["cache-control"] == "no-store"
    assert client.get("/auth/me").headers["cache-control"] == "no-store"


# ---- CSRF (needed because the production cookie is SameSite=None) ------------------

def test_state_changing_requests_from_other_origins_are_refused(make_client, collection):
    collection.insert_one(make_email("e1", unread=True))
    owner = make_client()
    login(owner)
    cookie = owner.cookies.get(SESSION_COOKIE)

    # An evil page makes the victim's browser send the cookie along:
    attacker = make_client(origin="https://evil.example")
    attacker.cookies.set(SESSION_COOKIE, cookie)
    assert attacker.post("/emails/sync").status_code == 403
    assert attacker.patch("/emails/e1/read").status_code == 403
    assert attacker.post("/auth/logout").status_code == 403
    assert attacker.post("/auth/login", json={"password": PASSWORD}).status_code == 403
    assert collection.find_one({"id": "e1"})["unread"] is True

    # ...and no Origin header at all is refused too:
    no_origin = make_client(origin=None)
    no_origin.cookies.set(SESSION_COOKIE, cookie)
    assert no_origin.post("/emails/sync").status_code == 403
    # Reading still depends on CORS (the evil page cannot read the response).
    assert no_origin.get("/emails/").status_code == 200


# ---- 7: secrets never reach the browser ---------------------------------------------

def test_no_secret_is_ever_returned_by_the_api(make_client, collection, monkeypatch):
    secrets_in_env = {
        "API_KEY": "api-key-value-0123456789",
        "GEMINI_API_KEY": "gemini-key-value-0123456789",
        "MONGODB_URI": "mongodb+srv://user:dbpassword123@cluster.example.net",
        "GOOGLE_TOKEN_JSON": '{"refresh_token": "1//refresh-token-value-0123456789"}',
    }
    for name, value in secrets_in_env.items():
        monkeypatch.setattr(settings, name, value)
    collection.insert_one(make_email())

    client = make_client()
    everything = []
    resp = login(client)
    everything += [resp.text, str(dict(resp.headers))]
    wrong = login(make_client(), "bad")
    everything += [wrong.text, str(dict(wrong.headers))]
    for path in ("/", "/healthz", "/status", "/auth/me", "/emails/", "/emails/briefing", "/emails/nope/read"):
        r = client.get(path)
        everything += [r.text, str(dict(r.headers))]
    r = client.post("/emails/sync")
    everything += [r.text, str(dict(r.headers))]

    blob = "\n".join(everything)
    for value in list(secrets_in_env.values()) + [PASSWORD, settings.SESSION_SECRET]:
        assert value not in blob, f"secret leaked: {value[:12]}..."
    # the session cookie itself is only ever delivered via Set-Cookie (HttpOnly), never in a body
    assert client.cookies.get(SESSION_COOKIE) not in resp.text


def test_frontend_source_contains_no_secrets_or_api_key_variables():
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if not frontend.exists():
        return
    forbidden = ["VITE_API_KEY", "X-API-Key", "x-api-key", "MONGODB_URI", "GEMINI_API_KEY",
                 "GOOGLE_TOKEN_JSON", "SESSION_SECRET", "AUTH_PASSWORD", "mongodb+srv", "AIza"]
    files = [p for p in frontend.rglob("*")
             if p.is_file() and "node_modules" not in p.parts and "dist" not in p.parts
             and p.suffix in {".js", ".jsx", ".html", ".json", ".css", ".example", ".md", ""}
             and p.name != "package-lock.json"]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for word in forbidden:
            assert word not in text, f"{word!r} found in {path.relative_to(frontend)}"
    # and nothing auth-related is ever written to / read from browser storage
    # (only actual storage calls are checked, not comments)
    for path in (frontend / "src").glob("*.jsx"):
        text = path.read_text(encoding="utf-8")
        for call in re.findall(r"(?:localStorage|sessionStorage)\.(?:get|set|remove)Item\(([^)]*)\)", text):
            assert not re.search(r"password|token|session|auth|cookie|key", call, re.I), f"{path.name}: {call}"
