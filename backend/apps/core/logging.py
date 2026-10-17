"""Structured logging with request IDs and secret redaction.

Log files are useful for troubleshooting, but a vault application must never
write passwords, tokens or keys to disk. The filters in this module apply a
conservative redaction to both normal messages and exception tracebacks.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import datetime, timezone

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

_SENSITIVE_PATTERN = re.compile(
    r"(?i)"
    r"([\"']?(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)"
    r"[\"']?\s*[:=]\s*)"
    r"((?:Bearer|Basic)\s+[^\s,;]+|\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def set_request_id(value: str) -> Token[str]:
    """Store the current request ID for log records created in this request."""

    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request ID after a request finishes."""

    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


def redact_text(value: str) -> str:
    """Mask values that look like ``password=...`` or ``"token": "..."``."""

    return _SENSITIVE_PATTERN.sub(r"\1***", value)


class RequestIDFilter(logging.Filter):
    """Attach the current request ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RedactSensitiveFilter(logging.Filter):
    """Replace sensitive values in a record's final message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True

        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Write one JSON object per line, suitable for later log processing."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": redact_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class SafeConsoleFormatter(logging.Formatter):
    """Readable development output that also redacts traceback text."""

    default_format = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, **kwargs):
        super().__init__(fmt or self.default_format, datefmt, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))
