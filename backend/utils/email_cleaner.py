from bs4 import BeautifulSoup


def clean_email_body(body):
    """Convert HTML email into clean readable text."""

    if not body:
        return ""

    soup = BeautifulSoup(body, "html.parser")

    text = soup.get_text(
        separator=" ",
        strip=True
    )

    return text