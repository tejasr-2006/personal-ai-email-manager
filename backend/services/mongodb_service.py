import os
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

# Find project root
BASE_DIR = Path(__file__).resolve().parents[2]

# Load .env from project root
load_dotenv(BASE_DIR / ".env")

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not found in .env")

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10000
)

db = client["personal_ai_email"]
emails_collection = db["emails"]


def save_email(email):
    emails_collection.update_one(
        {"id": email["id"]},
        {"$set": email},
        upsert=True
    )