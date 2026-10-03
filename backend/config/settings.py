"""
Central configuration.

Every setting comes from an environment variable (or a local .env file).
Nothing secret is hard-coded here. Import the ready-made object:

    from config.settings import settings
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

# Load backend/.env first, then fall back to a .env in the project root
# (older versions of this project kept it there). Real environment
# variables (e.g. on Render) always win because override=False.
for _env_file in (BACKEND_DIR / ".env", PROJECT_ROOT / ".env"):
    if _env_file.is_file():
        load_dotenv(_env_file, override=False)


# ------------------------------------------------------------------
# small helpers for reading environment variables safely
# ------------------------------------------------------------------

def _get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _get_int(name: str, default: int, minimum: int = 1, maximum: int = 10_000) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    # Trailing slashes are a common mistake and would never match the
    # browser's Origin header, so strip them.
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def _resolve_file(env_name: str, filename: str) -> str:
    """Explicit env var > backend/<file> > project-root/<file> (legacy)."""
    explicit = _get_str(env_name)
    if explicit:
        return explicit
    for folder in (BACKEND_DIR, PROJECT_ROOT):
        candidate = folder / filename
        if candidate.is_file():
            return str(candidate)
    return str(BACKEND_DIR / filename)


DEFAULT_DEV_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:4173",   # Vite preview
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


@dataclass
class Settings:
    # --- general ---
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000
    ENABLE_DOCS: bool = True

    # --- CORS / API protection ---
    ALLOWED_ORIGINS: List[str] = field(default_factory=lambda: list(DEFAULT_DEV_ORIGINS))
    ALLOWED_ORIGIN_REGEX: str = ""
    API_KEY: str = ""

    # --- MongoDB ---
    MONGODB_URI: str = ""
    MONGODB_DB_NAME: str = "personal_ai_email"
    MONGODB_COLLECTION: str = "emails"

    # --- Gemini ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_TIMEOUT_SECONDS: int = 30
    GEMINI_MAX_RETRIES: int = 2

    # --- Gmail ---
    GOOGLE_CREDENTIALS_FILE: str = ""
    GOOGLE_TOKEN_FILE: str = ""
    GOOGLE_TOKEN_JSON: str = ""
    GMAIL_QUERY: str = "in:inbox"

    # --- sync behaviour ---
    SYNC_MAX_EMAILS: int = 20
    SYNC_MAX_EMAILS_LIMIT: int = 100
    SYNC_TIME_BUDGET_SECONDS: int = 60
    SYNC_RECLASSIFY_LIMIT: int = 5
    MAX_BODY_CHARS: int = 10_000
    LIST_DEFAULT_LIMIT: int = 500

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def secret_values(self) -> List[str]:
        """Literal secrets, used by the log formatter to redact them."""
        values = [self.MONGODB_URI, self.GEMINI_API_KEY, self.API_KEY, self.GOOGLE_TOKEN_JSON]
        return [v for v in values if v and len(v) >= 8]


def load_settings() -> Settings:
    environment = _get_str("ENVIRONMENT", _get_str("ENV", "development")).lower()
    origins_were_set = bool(_get_str("ALLOWED_ORIGINS"))

    settings = Settings(
        ENVIRONMENT=environment,
        LOG_LEVEL=_get_str("LOG_LEVEL", "INFO").upper(),
        PORT=_get_int("PORT", 8000, 1, 65535),
        ENABLE_DOCS=_get_bool("ENABLE_DOCS", environment != "production"),
        ALLOWED_ORIGINS=_get_list("ALLOWED_ORIGINS", DEFAULT_DEV_ORIGINS),
        ALLOWED_ORIGIN_REGEX=_get_str("ALLOWED_ORIGIN_REGEX"),
        API_KEY=_get_str("API_KEY"),
        MONGODB_URI=_get_str("MONGODB_URI"),
        MONGODB_DB_NAME=_get_str("MONGODB_DB_NAME", "personal_ai_email"),
        MONGODB_COLLECTION=_get_str("MONGODB_COLLECTION", "emails"),
        GEMINI_API_KEY=_get_str("GEMINI_API_KEY"),
        GEMINI_MODEL=_get_str("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        GEMINI_TIMEOUT_SECONDS=_get_int("GEMINI_TIMEOUT_SECONDS", 30, 5, 120),
        GEMINI_MAX_RETRIES=_get_int("GEMINI_MAX_RETRIES", 2, 0, 5),
        GOOGLE_CREDENTIALS_FILE=_resolve_file("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        GOOGLE_TOKEN_FILE=_resolve_file("GOOGLE_TOKEN_FILE", "token.json"),
        GOOGLE_TOKEN_JSON=_get_str("GOOGLE_TOKEN_JSON"),
        GMAIL_QUERY=_get_str("GMAIL_QUERY", "in:inbox"),
        SYNC_MAX_EMAILS=_get_int("SYNC_MAX_EMAILS", 20, 1, 500),
        SYNC_MAX_EMAILS_LIMIT=_get_int("SYNC_MAX_EMAILS_LIMIT", 100, 1, 500),
        SYNC_TIME_BUDGET_SECONDS=_get_int("SYNC_TIME_BUDGET_SECONDS", 60, 10, 600),
        SYNC_RECLASSIFY_LIMIT=_get_int("SYNC_RECLASSIFY_LIMIT", 5, 0, 50),
        MAX_BODY_CHARS=_get_int("MAX_BODY_CHARS", 10_000, 500, 100_000),
        LIST_DEFAULT_LIMIT=_get_int("LIST_DEFAULT_LIMIT", 500, 1, 5000),
    )
    settings._origins_were_set = origins_were_set  # used only for a startup warning
    return settings


settings = load_settings()
