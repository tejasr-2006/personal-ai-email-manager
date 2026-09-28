import os
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from utils.email_cleaner import clean_email_body
from services.mongodb_service import save_email
from services.ai_service import classify_email

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_gmail_service():
    creds = None

    if os.path.exists("../token.json"):
        creds = Credentials.from_authorized_user_file(
            "../token.json",
            SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "../credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("../token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_email_body(payload):
    """Extract plain-text body from an email."""

    if "parts" in payload:
        for part in payload["parts"]:
            body = get_email_body(part)
            if body:
                return body

    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded = base64.urlsafe_b64decode(
            body_data
        ).decode("utf-8", errors="ignore")

        return decoded

    return ""


def get_emails(max_results=5):
    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    emails = []

    for message in messages:
        email = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="full"
        ).execute()

        headers = email["payload"].get("headers", [])

        sender = ""
        subject = ""
        date = ""

        for header in headers:
            name = header["name"].lower()

            if name == "from":
                sender = header["value"]

            elif name == "subject":
                subject = header["value"]

            elif name == "date":
                date = header["value"]

        body = get_email_body(email["payload"])
        body = clean_email_body(body)


        email_data = {
            "id": message["id"],
            "sender": sender,
            "subject": subject,
            "date": date,
            "body": body,
            "unread": "UNREAD" in email.get("labelIds", [])
        }

        try:
            classification = classify_email(email_data)

            email_data.update(classification)

        except Exception as e:
             print("AI classification failed:", e)

        save_email(email_data)

        emails.append(email_data)

    return emails

def mark_email_as_read(email_id):
    service = get_gmail_service()

    service.users().messages().modify(
        userId="me",
        id=email_id,
        body={
            "removeLabelIds": ["UNREAD"]
        }
    ).execute()