import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def classify_email(email):

    prompt = f"""
Classify this email for a student's personal email manager.

From: {email['sender']}
Subject: {email['subject']}
Body: {email['body'][:1500]}

Priority rules:
- HIGH: internships, placements, jobs, recruitment, interviews,
  assessments, application deadlines, scholarships, important academic opportunities.
- MEDIUM: career newsletters, job alerts without urgent deadlines,
  general education announcements, courses and certifications.
- LOW: promotions, shopping, social media, marketing and newsletters.

Also detect whether the email requires an action.

Possible action types:
- deadline
- interview
- assessment
- application
- payment
- academic
- none

When an important date or deadline is clearly mentioned, extract it as YYYY-MM-DD.
If no specific date is mentioned, return null.

Return ONLY valid JSON:

{{
    "category": "internship|placement|job|recruitment|education|finance|promotion|social|newsletter|personal|other",
    "priority": "high|medium|low",
    "summary": "short summary",
    "action_required": true,
    "action_type": "deadline|interview|assessment|application|payment|academic|none",
    "action_text": "short description of what the user needs to do",
    "deadline": "YYYY-MM-DD or null"
}}
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.5-flash-lite:generateContent"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=90
    )

    response.raise_for_status()

    result = response.json()

    text = result["candidates"][0]["content"]["parts"][0]["text"]

    text = text.replace("```json", "").replace("```", "").strip()

    result = json.loads(text)

    high_priority_categories = {
        "internship",
        "placement",
        "job",
        "recruitment"
    }

    if result["category"] in high_priority_categories:
        result["priority"] = "high"

    if result.get("action_type") in {
        "deadline",
        "interview",
        "assessment",
        "application"
    }:
        result["action_required"] = True

    return result

def generate_daily_briefing(emails):

    if not emails:
        return "No emails available for today's briefing."

    email_text = "\n\n".join(
        f"Subject: {email.get('subject', '')}\n"
        f"Category: {email.get('category', '')}\n"
        f"Priority: {email.get('priority', '')}\n"
        f"Action: {email.get('action_text', 'None')}"
        for email in emails
    )

    prompt = f"""
Create a short daily briefing for a student's email inbox.

Focus on:
- High priority emails
- Important actions
- Deadlines
- Interviews or assessments
- Important academic or career opportunities

Emails:
{email_text}

Return a concise briefing with:
1. Important emails
2. Actions to take
3. Upcoming deadlines

Do not invent information.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.5-flash-lite:generateContent"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=90
    )

    response.raise_for_status()

    result = response.json()

    return result["candidates"][0]["content"]["parts"][0]["text"]