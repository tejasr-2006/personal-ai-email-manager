"""
Data models.

`Classification` validates what the AI returns. The other models describe
what the API sends back to the frontend.
"""

import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

# The frontend and database use lowercase priorities ("high", "medium", "low").
# The AI may answer HIGH / MEDIUM / LOW - validation lowercases it.
PRIORITIES = ("high", "medium", "low")
ACTION_TYPES = (
    "deadline",
    "interview",
    "assessment",
    "application",
    "payment",
    "academic",
    "none",
)
CATEGORIES = (
    "internship",
    "placement",
    "job",
    "recruitment",
    "education",
    "finance",
    "promotion",
    "social",
    "newsletter",
    "personal",
    "other",
)
# Action types that always mean "the user has to do something".
STRONG_ACTION_TYPES = {"deadline", "interview", "assessment", "application"}
# Categories that are always important for this student-focused app.
HIGH_PRIORITY_CATEGORIES = {"internship", "placement", "job", "recruitment"}


def _clean_text(value: Any, max_length: int) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:max_length]


class Classification(BaseModel):
    """Validated AI output. Raises pydantic.ValidationError if unusable."""

    category: str = "other"
    priority: str
    summary: str = ""
    action_required: bool = False
    action_type: str = "none"
    action_text: str = ""
    deadline: Optional[str] = None

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v):
        v = _clean_text(v, 40).lower()
        return v if v in CATEGORIES else "other"

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, v):
        v = _clean_text(v, 20).lower()
        if v not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        return v

    @field_validator("action_type", mode="before")
    @classmethod
    def _action_type(cls, v):
        v = _clean_text(v, 40).lower()
        return v if v in ACTION_TYPES else "none"

    @field_validator("action_required", mode="before")
    @classmethod
    def _action_required(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in {"true", "yes", "1"}
        return bool(v)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v):
        return _clean_text(v, 300)

    @field_validator("action_text", mode="before")
    @classmethod
    def _action_text(cls, v):
        return _clean_text(v, 200)

    @field_validator("deadline", mode="before")
    @classmethod
    def _deadline(cls, v):
        v = _clean_text(v, 20)
        if not v or v.lower() in {"null", "none", "n/a"}:
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            return None
        return v


# ----------------------------------------------------------------------
# API response models
# ----------------------------------------------------------------------

class EmailOut(BaseModel):
    """One email as the frontend sees it (MongoDB `_id` is never exposed)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    thread_id: Optional[str] = None
    sender: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    date: Optional[str] = None
    internal_date: Optional[int] = None
    snippet: Optional[str] = None
    body: Optional[str] = None
    labels: List[str] = []
    unread: bool = False

    category: Optional[str] = None
    priority: Optional[str] = None
    summary: Optional[str] = None
    action_required: bool = False
    action_type: Optional[str] = None
    action_text: Optional[str] = None
    deadline: Optional[str] = None
    classification_source: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


class MarkReadResponse(BaseModel):
    message: str
    gmail_updated: bool


class BriefingResponse(BaseModel):
    briefing: str


class SyncResponse(BaseModel):
    message: str
    status: str            # "completed" | "partial" | "in_progress"
    count: int             # new emails saved by this sync
    new: int
    skipped: int           # already stored, not processed again
    reclassified: int      # earlier fallback classifications retried with AI
    fallback_classified: int
    failed: int
