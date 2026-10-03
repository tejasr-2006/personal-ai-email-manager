"""Pagination and error translation, using a fake Gmail client."""

import pytest
from googleapiclient.errors import HttpError

from services import gmail_service
from services.gmail_service import GmailAPIError, list_message_ids


class FakeRequest:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self, num_retries=0):
        if self.error:
            raise self.error
        return self.result


class FakeResp(dict):
    def __init__(self, status):
        super().__init__(status=status)
        self.status = status
        self.reason = "x"


class FakeMessages:
    """Serves 250 messages in pages, like Gmail."""

    def __init__(self):
        self.calls = []

    def list(self, **params):
        self.calls.append(params)
        start = int(params.get("pageToken", 0))
        size = params["maxResults"]
        batch = [{"id": f"id{i}"} for i in range(start, min(start + size, 250))]
        result = {"messages": batch}
        if start + size < 250:
            result["nextPageToken"] = str(start + size)
        return FakeRequest(result)


class FakeService:
    def __init__(self):
        self.messages_api = FakeMessages()

    def users(self):
        return self

    def messages(self):
        return self.messages_api


def test_pagination_follows_next_page_token():
    service = FakeService()
    ids = list_message_ids(service, 230, "in:inbox")
    assert len(ids) == 230 and len(set(ids)) == 230
    sizes = [c["maxResults"] for c in service.messages_api.calls]
    assert sizes == [100, 100, 30]                 # never asks for more than needed
    assert all(c["q"] == "in:inbox" for c in service.messages_api.calls)


def test_stops_when_mailbox_is_smaller_than_requested():
    assert len(list_message_ids(FakeService(), 1000)) == 250


@pytest.mark.parametrize("status,expected", [(403, "rejected"), (429, "rate limit"), (404, "not found"), (500, "status 500")])
def test_http_errors_become_gmail_api_error_without_leaking_details(status, expected):
    error = HttpError(FakeResp(status), b'{"error": {"message": "SECRET INTERNAL DETAIL"}}')
    with pytest.raises(GmailAPIError) as info:
        gmail_service._execute(FakeRequest(error=error))
    assert expected in str(info.value).lower()
    assert "SECRET" not in str(info.value)
    assert info.value.status == status


def test_network_error_becomes_gmail_api_error():
    with pytest.raises(GmailAPIError):
        gmail_service._execute(FakeRequest(error=OSError("connection reset")))


def test_missing_token_raises_helpful_auth_error(monkeypatch, tmp_path):
    monkeypatch.setattr(gmail_service, "_creds", None)
    monkeypatch.setattr(gmail_service.settings, "GOOGLE_TOKEN_JSON", "")
    monkeypatch.setattr(gmail_service.settings, "GOOGLE_TOKEN_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(gmail_service.GmailAuthError) as info:
        gmail_service.get_credentials()
    assert "gmail_auth.py" in str(info.value)
    assert gmail_service.is_configured() is False


def test_token_from_env_var_is_loaded(monkeypatch):
    import json
    token = {"token": "ya29.fake", "refresh_token": "1//fake", "client_id": "id",
             "client_secret": "secret", "token_uri": "https://oauth2.googleapis.com/token",
             "scopes": gmail_service.SCOPES}
    monkeypatch.setattr(gmail_service, "_creds", None)
    monkeypatch.setattr(gmail_service.settings, "GOOGLE_TOKEN_JSON", json.dumps(token))
    creds = gmail_service._load_token()
    assert creds is not None and creds.refresh_token == "1//fake"
    assert gmail_service.is_configured() is True


def test_corrupt_token_env_var_does_not_crash(monkeypatch):
    monkeypatch.setattr(gmail_service.settings, "GOOGLE_TOKEN_JSON", "{not json")
    assert gmail_service._load_token() is None
