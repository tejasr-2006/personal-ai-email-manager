import base64

from services.gmail_service import get_email_body, parse_message


def b64(text: str, pad: bool = True) -> str:
    data = base64.urlsafe_b64encode(text.encode()).decode()
    return data if pad else data.rstrip("=")


def message(payload, **extra):
    base = {"id": "m1", "threadId": "t1", "labelIds": ["INBOX", "UNREAD"],
            "internalDate": "1790000000000", "snippet": "snip", "payload": payload}
    base.update(extra)
    return base


def test_plain_text_without_base64_padding():
    # Original code crashed/returned "" on unpadded data like this.
    payload = {"mimeType": "text/plain", "body": {"data": b64("Hello world!!", pad=False)}}
    assert "Hello world" in get_email_body(payload)


def test_html_only_email_is_parsed():
    payload = {"mimeType": "text/html", "body": {"data": b64("<html><body><p>Big <b>news</b></p></body></html>")}}
    parsed = parse_message(message({**payload, "headers": []}))
    assert parsed["body"] == "Big news"


def test_multipart_prefers_plain_text():
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": b64("<p>html version</p>")}},
        {"mimeType": "text/plain", "body": {"data": b64("plain version")}},
    ]}
    assert get_email_body(payload) == "plain version"


def test_nested_multipart():
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("deep text")}}]},
        {"mimeType": "application/pdf", "body": {"attachmentId": "x"}},
    ]}
    assert get_email_body(payload) == "deep text"


def test_headers_flags_and_metadata():
    payload = {"mimeType": "text/plain", "body": {"data": b64("hi")}, "headers": [
        {"name": "From", "value": "Ann <ann@example.com>"},
        {"name": "subject", "value": "Hello"},
        {"name": "Date", "value": "Fri, 02 Oct 2026 10:00:00 +0000"},
    ]}
    parsed = parse_message(message(payload))
    assert parsed["sender_email"] == "ann@example.com"
    assert parsed["subject"] == "Hello"
    assert parsed["unread"] is True
    assert parsed["internal_date"] == 1790000000000
    assert parsed["thread_id"] == "t1"


def test_garbage_body_does_not_crash():
    payload = {"mimeType": "text/plain", "body": {"data": "!!!not-base64!!!"}}
    assert get_email_body(payload) == ""
