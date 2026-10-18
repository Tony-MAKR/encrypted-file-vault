"""Session authentication that returns 401 for missing credentials."""

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied

CSRF_FAILED_DETAIL = "CSRF 校验失败，请刷新页面后重试。"


class SessionAuthentication401(SessionAuthentication):
    """Use HTTP 401 instead of DRF's default 403 for unauthenticated requests.

    This makes the frontend's session-expired handling unambiguous while still
    using Django's battle-tested session and CSRF implementation.
    """

    def authenticate_header(self, request) -> str:
        return "Session"

    def enforce_csrf(self, request) -> None:
        try:
            super().enforce_csrf(request)
        except PermissionDenied:
            # Keep every CSRF failure in the same JSON shape for the SPA.
            raise PermissionDenied(
                {"detail": CSRF_FAILED_DETAIL, "code": "csrf_failed"}
            ) from None


class CsrfEnforcingSessionAuthentication(SessionAuthentication401):
    """Enforce CSRF even when the request has no authenticated user.

    DRF's SessionAuthentication only checks CSRF after a session user is found.
    That is insufficient for login and first-run setup, which are anonymous but
    still state-changing. Django's CSRFCheck respects the test client's
    ``_dont_enforce_csrf_checks`` flag, so normal tests remain convenient while
    explicit CSRF tests and production requests are protected.
    """

    def authenticate(self, request):
        self.enforce_csrf(request)
        return super().authenticate(request)
