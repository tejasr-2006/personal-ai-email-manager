import json

import pytest
from pydantic import ValidationError

from models.email import Classification
from services import ai_service
from services.ai_service import (
    AIServiceError,
    _parse_json_object,
    classify_email,
    fallback_classify,
    validate_classification,
)

EMAIL = {"sender": "x@y.com", "subject": "Internship Application Deadline",
         "body": "Complete your internship application before September 30, 2026."}


def test_parse_json_handles_code_fences_and_prose():
    assert _parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_object('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        _parse_json_object("no json here")
    with pytest.raises(ValueError):
        _parse_json_object("[1, 2]")


def test_validation_normalises_case_and_bad_values():
    result = validate_classification(
        {"category": "SOCIAL", "priority": "MEDIUM", "summary": " hi  there ",
         "action_required": "true", "action_type": "banana", "deadline": "31/12/2026"},
        EMAIL,
    )
    assert result["category"] == "social"
    assert result["priority"] == "medium"
    assert result["summary"] == "hi there"
    assert result["action_required"] is True
    assert result["action_type"] == "none"      # unknown value -> none
    assert result["deadline"] is None            # not YYYY-MM-DD -> None


def test_validation_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        Classification(priority="urgent!!")


def test_career_category_forces_high_and_strong_action_forces_required():
    result = validate_classification(
        {"category": "job", "priority": "low", "action_required": False, "action_type": "interview"},
        EMAIL,
    )
    assert result["priority"] == "high"
    assert result["action_required"] is True
    assert result["action_text"]  # filled in


def test_classify_uses_ai_when_valid(monkeypatch):
    reply = json.dumps({"category": "internship", "priority": "HIGH", "summary": "Apply soon",
                        "action_required": True, "action_type": "application",
                        "action_text": "Apply", "deadline": "2026-09-30"})
    monkeypatch.setattr(ai_service, "_call_gemini", lambda *a, **k: reply)
    result = classify_email(EMAIL)
    assert result["classification_source"] == "ai"
    assert result["priority"] == "high"
    assert result["deadline"] == "2026-09-30"


@pytest.mark.parametrize("bad_reply", ["not json at all", "{}", '{"priority": "whatever"}', "[]"])
def test_classify_falls_back_on_invalid_ai_output(monkeypatch, bad_reply):
    monkeypatch.setattr(ai_service, "_call_gemini", lambda *a, **k: bad_reply)
    result = classify_email(EMAIL)
    assert result["classification_source"] == "fallback"
    assert result["priority"] in {"high", "medium", "low"}


def test_classify_falls_back_when_ai_is_down(monkeypatch):
    def boom(*a, **k):
        raise AIServiceError("down")
    monkeypatch.setattr(ai_service, "_call_gemini", boom)
    assert classify_email(EMAIL)["classification_source"] == "fallback"


def test_classify_without_api_key_uses_fallback():
    assert classify_email(EMAIL)["classification_source"] == "fallback"


def test_fallback_rules():
    result = fallback_classify(EMAIL)
    assert result["priority"] == "high"
    assert result["action_type"] == "application"
    assert result["deadline"] == "2026-09-30"

    assert fallback_classify({"subject": "Interview on Monday", "body": ""})["action_type"] == "interview"
    assert fallback_classify({"subject": "50% off sale! unsubscribe", "body": ""})["priority"] == "low"
    assert fallback_classify({"subject": "Invoice payment due", "body": ""})["action_type"] == "payment"


def test_all_outputs_have_required_keys():
    keys = {"category", "priority", "summary", "action_required", "action_type"}
    assert keys <= set(fallback_classify({"subject": "", "body": ""}))
