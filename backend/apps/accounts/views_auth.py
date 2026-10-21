"""First-run setup and authentication endpoints."""

from __future__ import annotations

import logging

from django.contrib.auth import (
    authenticate,
    update_session_auth_hash,
)
from django.contrib.auth import (
    login as django_login,
)
from django.contrib.auth import (
    logout as django_logout,
)
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record_audit, target_user

from .authentication import CsrfEnforcingSessionAuthentication
from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    SetupSerializer,
    UserSerializer,
)
from .services import (
    clear_expired_lock,
    delete_user_sessions,
    register_login_failure,
    reset_login_failures,
)
from .throttles import LoginRateThrottle, SetupRateThrottle

logger = logging.getLogger("apps.accounts.auth")


def _login_error(
    message: str = "用户名或密码错误。",
    code: str | None = None,
    http_status: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    payload = {"detail": message}
    if code:
        payload["code"] = code
    return Response(payload, status=http_status)


def _is_loopback(request) -> bool:
    # Deliberately do not trust X-Forwarded-For. Setup must be performed while
    # the server is accessed locally, before any reverse proxy is introduced.
    return request.META.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}


@api_view(["GET"])
@permission_classes([AllowAny])
def setup_status(request) -> Response:
    return Response({"needs_setup": not User.objects.exists()})


@require_GET
@ensure_csrf_cookie
def csrf_token_view(request) -> HttpResponse:
    """Give the SPA a CSRF cookie before it submits any form."""

    return HttpResponse(status=204)


def csrf_failure(request, reason: str = "") -> JsonResponse:
    """Return JSON, rather than an HTML page, for CSRF failures."""

    return JsonResponse(
        {
            "detail": "CSRF 校验失败，请刷新页面后重试。",
            "code": "csrf_failed",
        },
        status=403,
    )


@api_view(["POST"])
@authentication_classes([CsrfEnforcingSessionAuthentication])
@permission_classes([AllowAny])
@throttle_classes([SetupRateThrottle])
def setup(request) -> Response:
    if not _is_loopback(request):
        logger.warning("setup_rejected reason=remote_address")
        return Response(
            {"detail": "首次设置只能在本机完成。"},
            status=status.HTTP_403_FORBIDDEN,
        )

    if User.objects.exists():
        return Response(
            {"detail": "系统已经完成初始化。"},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = SetupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        with transaction.atomic():
            if User.objects.exists():
                return Response(
                    {"detail": "系统已经完成初始化。"},
                    status=status.HTTP_409_CONFLICT,
                )
            user = User.objects.create_user(
                username=serializer.validated_data["username"],
                display_name=serializer.validated_data["display_name"],
                password=serializer.validated_data["password"],
                role=User.Role.ADMIN,
                must_change_password=False,
            )
    except IntegrityError:
        # Another concurrent setup request won the race.
        return Response(
            {"detail": "系统已经完成初始化。"},
            status=status.HTTP_409_CONFLICT,
        )

    logger.info("setup_completed username=%s", user.username)
    record_audit(request, "setup_completed", **target_user(user))
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes([CsrfEnforcingSessionAuthentication])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request) -> Response:
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data["username"]
    password = serializer.validated_data["password"]
    user = User.objects.filter(username=username).first()

    if user is None:
        logger.warning("login_failed username=%s reason=unknown_user", username)
        record_audit(
            request,
            "login_failed",
            result="failure",
            actor_username=username,
            detail={"reason": "unknown_user"},
        )
        return _login_error()

    clear_expired_lock(user)

    if user.is_locked():
        logger.warning("login_blocked username=%s reason=locked", username)
        record_audit(
            request,
            "login_blocked",
            result="denied",
            actor_username=username,
            detail={"reason": "locked"},
        )
        return _login_error(
            "尝试次数过多，请稍后再试。",
            code="account_locked",
            http_status=423,
        )

    if not user.is_active:
        logger.warning("login_failed username=%s reason=inactive", username)
        record_audit(
            request,
            "login_failed",
            result="denied",
            actor_username=username,
            detail={"reason": "inactive"},
        )
        return _login_error()

    authenticated = authenticate(request, username=username, password=password)
    if authenticated is None:
        register_login_failure(user)
        logger.warning("login_failed username=%s reason=bad_credentials", username)
        record_audit(
            request,
            "login_failed",
            result="failure",
            actor_username=username,
            detail={"reason": "bad_credentials"},
        )
        return _login_error()

    reset_login_failures(authenticated)
    django_login(request, authenticated)

    now = timezone.now()
    request.session["login_at"] = now.isoformat()
    request.session["last_activity"] = now.isoformat()

    logger.info("login_succeeded username=%s", authenticated.username)
    record_audit(request, "login_succeeded", **target_user(authenticated))
    return Response(UserSerializer(authenticated).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request) -> Response:
    username = request.user.username
    record_audit(request, "logout", **target_user(request.user))
    django_logout(request)
    logger.info("logout username=%s", username)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request) -> Response:
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request) -> Response:
    serializer = ChangePasswordSerializer(
        data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    user = request.user
    user.set_password(serializer.validated_data["new_password"])
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password", "updated_at"])

    # Keep this session usable, but drop every other session for this account.
    update_session_auth_hash(request, user)
    delete_user_sessions(user, except_session_key=request.session.session_key)
    logger.info("password_changed username=%s", user.username)
    record_audit(request, "password_changed", **target_user(user))
    return Response({"detail": "密码已修改。"})
