"""Logging must never persist obvious secrets."""

import json
import logging

from apps.core.logging import JsonFormatter, RedactSensitiveFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="tests.redaction",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_password_and_token_are_redacted():
    record = _record("login attempt password=hunter2 token=abc123")
    RedactSensitiveFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert "hunter2" not in payload["message"]
    assert "abc123" not in payload["message"]
    assert "password=***" in payload["message"]
    assert "token=***" in payload["message"]


def test_json_style_secrets_and_bearer_tokens_are_redacted():
    record = _record(
        'request body {"password": "hunter2", "token": "abc123"} '
        "Authorization: Bearer supersecret-value"
    )
    RedactSensitiveFilter().filter(record)

    output = JsonFormatter().format(record)

    assert "hunter2" not in output
    assert "abc123" not in output
    assert "supersecret-value" not in output
    assert "***" in output


def test_ordinary_text_is_not_changed():
    message = "health check completed successfully"
    record = _record(message)
    RedactSensitiveFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == message


def test_exception_text_is_redacted():
    record = _record("request failed")
    try:
        raise ValueError('token="secret-value"')
    except ValueError:
        record.exc_info = __import__("sys").exc_info()

    output = JsonFormatter().format(record)

    assert "secret-value" not in output
    assert "***" in output
