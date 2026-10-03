"""Manual check: python scripts/check_gmail.py  (reads 5 emails, saves nothing)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.gmail_service import get_emails  # noqa: E402

for i, email in enumerate(get_emails(5), start=1):
    print("\n" + "=" * 60)
    print(f"EMAIL {i}")
    print("=" * 60)
    print(f"From: {email['sender']}")
    print(f"Subject: {email['subject']}")
    print(f"Date: {email['date']}")
    print("\nBody:")
    print(email["body"][:500])
