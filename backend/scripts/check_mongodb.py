"""Manual check: python scripts/check_mongodb.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import mongodb_service  # noqa: E402

try:
    mongodb_service.ping()
    print("MongoDB connected successfully! Stored emails:", mongodb_service.count_emails())
except Exception as exc:  # noqa: BLE001
    print("MongoDB connection failed:", exc)
