"""Sanitize exception messages before displaying them to users."""

import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"key[=:\s]+\S+", re.IGNORECASE),
    re.compile(r"password[=:\s]+\S+", re.IGNORECASE),
    re.compile(r"mysql\+pymysql://[^\s]+"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
]


def safe_message(exc: Exception) -> str:
    """Return a user-safe version of an exception message with secrets redacted."""
    msg = str(exc)
    for pattern in _SECRET_PATTERNS:
        msg = pattern.sub("[REDACTED]", msg)
    if len(msg) > 500:
        msg = msg[:500] + "..."
    return msg
