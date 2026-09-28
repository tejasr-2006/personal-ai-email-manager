from services.gmail_service import get_emails


emails = get_emails(5)

for i, email in enumerate(emails, start=1):

    print("\n" + "=" * 60)
    print(f"EMAIL {i}")
    print("=" * 60)

    print(f"From: {email['sender']}")
    print(f"Subject: {email['subject']}")
    print(f"Date: {email['date']}")

    print("\nBody:")
    print(email["body"][:1000])