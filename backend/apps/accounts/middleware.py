"""Session lifetime and forced-password-change enforcement."""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.utils import timezone


def _expired_response() -> JsonResponse:
    return JsonResponse(
        {"detail": "登录已过期，请重新登录。", "code": "session_expired"},
        status=401,
    )


def _parse_session_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = timezone.make_aware(parsed)
    return parsed


class SessionTimeoutMiddleware:
    """Apply idle and absolute session limits to authenticated API requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        if not user.is_active:
            logout(request)
            return _expired_response()

        now = timezone.now()
        session = request.session
        login_at = _parse_session_time(session.get("login_at", ""))
        last_activity = _parse_session_time(session.get("last_activity", ""))

        if login_at is None or last_activity is None:
            login_at = now
            last_activity = now
            session["login_at"] = now.isoformat()
            session["last_activity"] = now.isoformat()

        idle_seconds = int(getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 1800))
        absolute_seconds = int(
            getattr(settings, "SESSION_ABSOLUTE_TIMEOUT_SECONDS", 8 * 60 * 60)
        )

        if (
            (now - last_activity).total_seconds() > idle_seconds
            or (now - login_at).total_seconds() > absolute_seconds
        ):
            logout(request)
            return _expired_response()

        session["last_activity"] = now.isoformat()
        return self.get_response(request)


class MustChangePasswordMiddleware:
    """Block normal API access until a temporary-password user changes it."""

    ALLOWED_PATHS = frozenset(
        {
            "/api/v1/health/",
            "/api/v1/auth/csrf/",
            "/api/v1/auth/login/",
            "/api/v1/auth/logout/",
            "/api/v1/auth/me/",
            "/api/v1/auth/change-password/",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            request.path.startswith("/api/")
            and request.method != "OPTIONS"
            and user
            and user.is_authenticated
            and user.must_change_password
            and request.path not in self.ALLOWED_PATHS
        ):
            return JsonResponse(
                {
                    "detail": "请先修改密码，再使用其他功能。",
                    "code": "password_change_required",
                },
                status=403,
            )
        return self.get_response(request)
