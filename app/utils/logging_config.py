"""Structured logging configuration with automatic credential redaction."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import APP_DIR, LOG_PATH

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9._\-]{12,})\b"),
    re.compile(r"(['\"]?api[_-]?key['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}]{6,})", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Remove potential API keys or Bearer tokens from diagnostic strings."""
    if not text:
        return ""
    cleaned = str(text)
    cleaned = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", cleaned)
    cleaned = _SECRET_PATTERNS[1].sub("[REDACTED_KEY]", cleaned)
    cleaned = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", cleaned)
    return cleaned


class SecretRedactingFilter(logging.Filter):
    """Ensure API keys or tokens never reach log files."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def configure_logging(level_name: str = "INFO", log_file: Path | None = None) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    target = log_file or LOG_PATH
    logger = logging.getLogger()
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger.setLevel(level)

    if any(getattr(h, "_sortify_handler", False) for h in logger.handlers):
        for h in logger.handlers:
            if getattr(h, "_sortify_handler", False):
                h.setLevel(level)
        return

    try:
        handler = RotatingFileHandler(
            target, maxBytes=1_500_000, backupCount=3, encoding="utf-8"
        )
        handler._sortify_handler = True  # type: ignore[attr-defined]
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handler.addFilter(SecretRedactingFilter())
        logger.addHandler(handler)
    except OSError:
        # Fallback to NullHandler if filesystem is read-only
        logger.addHandler(logging.NullHandler())
