from services.ai_service import classify_email

email = {
    "sender": "company@example.com",
    "subject": "Internship Application Deadline",
    "body": "Please complete your internship application before September 30, 2026."
}

result = classify_email(email)

print(result)