"""Small, framework-level middleware used by every request."""

from __future__ import annotations

import logging
import time
import uuid

from apps.core.logging import reset_request_id, set_request_id

access_logger = logging.getLogger("apps.core.access")


class RequestIDMiddleware:
    """Attach a request ID to logs and to the response.

    An incoming X-Request-ID is accepted only when it is short enough to be
    safe; otherwise a random ID is generated. Query strings are not logged so
    that future tokens in URLs cannot leak into log files.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        candidate = request.headers.get("X-Request-ID", "").strip()
        request_id = candidate if 0 < len(candidate) <= 64 else uuid.uuid4().hex
        request.request_id = request_id
        token = set_request_id(request_id)
        started = time.monotonic()

        try:
            response = self.get_response(request)
        except Exception:
            access_logger.exception(
                "request failed: %s %s", request.method, request.path
            )
            raise
        else:
            elapsed_ms = (time.monotonic() - started) * 1000
            access_logger.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.path,
                response.status_code,
                elapsed_ms,
            )
            response["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware:
    """Add headers that Django's built-in middleware does not cover."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
