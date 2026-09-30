import os
import base64
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from utils.email_cleaner import clean_email_body
from services.mongodb_service import save_email
from services.ai_service import classify_email


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    str(BASE_DIR / "credentials.json")
)

TOKEN_FILE = os.getenv(
    "GOOGLE_TOKEN_FILE",
    str(BASE_DIR / "token.json")
)


# ============================================================
# GMAIL CONFIGURATION
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify"
]


# ============================================================
# GMAIL SERVICE
# ============================================================

def get_gmail_service():
    creds = None

    # Load existing token
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(
                TOKEN_FILE,
                SCOPES
            )
        except Exception as e:
            print("Failed to load Gmail token:", e)
            creds = None

    # Refresh or create credentials
    if not creds or not creds.valid:

        # Refresh existing credentials
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("Gmail token refreshed successfully.")

            except Exception as e:
                print("Failed to refresh Gmail token:", e)
                creds = None

        # Start OAuth flow if no valid credentials
        if not creds or not creds.valid:

            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials file not found: {CREDENTIALS_FILE}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        # Save credentials
        try:
            token_directory = os.path.dirname(TOKEN_FILE)

            if token_directory:
                os.makedirs(token_directory, exist_ok=True)

            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

            print("Gmail token saved successfully.")

        except Exception as e:
            print("Failed to save Gmail token:", e)

    # Build Gmail API service
    return build(
        "gmail",
        "v1",
        credentials=creds
    )


# ============================================================
# EMAIL BODY EXTRACTION
# ============================================================

def get_email_body(payload):
    """
    Extract plain-text body from a Gmail message.
    """

    mime_type = payload.get("mimeType", "")

    # Prefer plain text
    if mime_type == "text/plain":

        body_data = payload.get("body", {}).get("data")

        if body_data:
            try:
                return base64.urlsafe_b64decode(
                    body_data
                ).decode(
                    "utf-8",
                    errors="ignore"
                )
            except Exception as e:
                print("Failed to decode email body:", e)

    # Search multipart sections recursively
    for part in payload.get("parts", []):

        body = get_email_body(part)

        if body:
            return body

    return ""


# ============================================================
# GET EMAIL HEADER
# ============================================================

def get_header(headers, header_name):
    """
    Get a specific Gmail header value.
    """

    header_name = header_name.lower()

    for header in headers:

        if header.get("name", "").lower() == header_name:
            return header.get("value", "")

    return ""


# ============================================================
# GET EMAILS
# ============================================================

def get_emails(max_results=5):

    service = get_gmail_service()

    # Get message IDs
    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            maxResults=max_results
        )
        .execute()
    )

    messages = results.get("messages", [])

    emails = []

    for message in messages:

        try:

            # Get complete email
            email = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message["id"],
                    format="full"
                )
                .execute()
            )

            payload = email.get("payload", {})

            headers = payload.get("headers", [])

            # Extract headers
            sender = get_header(headers, "From")
            subject = get_header(headers, "Subject")
            date = get_header(headers, "Date")

            # Extract body
            body = get_email_body(payload)

            # Clean body
            body = clean_email_body(body)

            # Check unread status
            label_ids = email.get("labelIds", [])

            unread = "UNREAD" in label_ids

            # Create email object
            email_data = {
                "id": message["id"],
                "sender": sender,
                "subject": subject,
                "date": date,
                "body": body,
                "unread": unread
            }

            # ====================================================
            # AI CLASSIFICATION
            # ====================================================

            try:

                classification = classify_email(email_data)

                if classification:
                    email_data.update(classification)

            except Exception as e:

                print(
                    "AI classification failed:",
                    e
                )

            # ====================================================
            # SAVE TO MONGODB
            # ====================================================

            try:

                save_email(email_data)

            except Exception as e:

                print(
                    "Failed to save email to MongoDB:",
                    e
                )

            emails.append(email_data)

        except Exception as e:

            print(
                f"Failed to process email {message.get('id')}:",
                e
            )

    return emails


# ============================================================
# MARK EMAIL AS READ
# ============================================================

def mark_email_as_read(email_id):

    service = get_gmail_service()

    try:

        service.users().messages().modify(
            userId="me",
            id=email_id,
            body={
                "removeLabelIds": ["UNREAD"]
            }
        ).execute()

        return True

    except Exception as e:

        print(
            f"Failed to mark email {email_id} as read:",
            e
        )

        return False