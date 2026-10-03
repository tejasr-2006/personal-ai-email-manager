from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Max length stops someone posting megabytes as a "password".
    password: str = Field(min_length=1, max_length=256)


class AuthStatus(BaseModel):
    authenticated: bool
    expires_at: Optional[str] = None
