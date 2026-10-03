"""Optional shared-secret protection for the API."""

import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from config.settings import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    If API_KEY is set in the environment, every protected request must send
    a matching `X-API-Key` header. If API_KEY is empty the check is skipped
    (handy for local development).
    """
    expected = settings.API_KEY
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )
