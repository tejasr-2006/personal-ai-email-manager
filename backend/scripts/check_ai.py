"""Manual check: python scripts/check_ai.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_service import classify_email  # noqa: E402

email = {
    "sender": "company@example.com",
    "subject": "Internship Application Deadline",
    "body": "Please complete your internship application before September 30, 2026.",
}

print(json.dumps(classify_email(email), indent=2))
print("\n'classification_source' should be 'ai'. 'fallback' means Gemini was not reachable.")
