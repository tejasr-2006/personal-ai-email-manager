"""Health / status endpoints (public, expose no private data)."""

from datetime import datetime, timezone

from fastapi import APIRouter

from config.settings import settings
from services import gmail_service, mongodb_service
from services.mongodb_service import DatabaseUnavailable

router = APIRouter(tags=["Health"])

SERVICE_NAME = "Personal AI Email Manager"


@router.get("/")
def home():
    return {
        "message": f"{SERVICE_NAME} is running",
        "status": "running",
        "environment": settings.ENVIRONMENT,
    }


@router.get("/healthz")
def healthz():
    """Fast liveness check (does NOT touch MongoDB / Gmail). Used by Render."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/status")
def status():
    """Deeper check: is each dependency configured and reachable?"""
    if not settings.MONGODB_URI:
        database = "not_configured"
    else:
        try:
            mongodb_service.ping()
            database = "connected"
        except DatabaseUnavailable:
            database = "unavailable"

    checks = {
        "database": database,
        "gmail": "configured" if gmail_service.is_configured() else "not_authorised",
        "gemini": "configured" if settings.GEMINI_API_KEY else "not_configured",
        "api_key_protection": "enabled" if settings.API_KEY else "disabled",
    }
    healthy = database == "connected" and checks["gmail"] == "configured" and checks["gemini"] == "configured"
    return {"status": "ok" if healthy else "degraded", "service": SERVICE_NAME, "checks": checks}
