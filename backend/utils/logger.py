"""Logging setup with automatic secret redaction."""

import logging
import re
import sys

from config.settings import settings

_REDACTIONS = [
    # mongodb://user:pass@host  ->  mongodb://***@host
    (re.compile(r"(mongodb(?:\+srv)?://)[^\s'\"@/]+@"), r"\1***@"),
    # Google API keys, OAuth access / refresh tokens
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "***"),
    (re.compile(r"ya29\.[0-9A-Za-z_\-]+"), "***"),
    (re.compile(r"1//[0-9A-Za-z_\-]{20,}"), "***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1***"),
]


def redact(text: str) -> str:
    """Remove anything that looks like a secret from a log line."""
    for secret in settings.secret_values:
        text = text.replace(secret, "***")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging() -> None:
    """Configure root logging once (safe to call several times)."""
    root = logging.getLogger()
    if getattr(root, "_email_manager_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)  # Render collects stdout
    handler.setFormatter(
        RedactingFormatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    root._email_manager_configured = True

    # Keep third-party libraries quiet unless something is wrong.
    for noisy in ("googleapiclient.discovery_cache", "urllib3", "httpx", "pymongo"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
