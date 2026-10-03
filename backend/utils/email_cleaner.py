import re

from bs4 import BeautifulSoup

_HTML_HINT = re.compile(r"<\s*(html|body|div|p|br|table|span|a|style|head)\b", re.I)


def clean_email_body(body):
    """Convert an email body (HTML or plain text) into clean readable text."""

    if not body:
        return ""

    if _HTML_HINT.search(body):
        soup = BeautifulSoup(body, "html.parser")

        # Styles / scripts are never readable content.
        for tag in soup(["script", "style", "head", "title"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()

    # Plain text: keep paragraphs, tidy whitespace.
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
