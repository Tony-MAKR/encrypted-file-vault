"""Administrator-only user management endpoints."""

from __future__ import annotations

import logging

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record_audit, target_user

from .models import User
from .permissions import IsAdminRole
from .serializers import (
    ResetPasswordSerializer,
    RoleUpdateSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .services import (
    delete_user_sessions,
    is_last_active_admin,
    reset_login_failures,
)

logger = logging.getLogger("apps.accounts.admin")


class UserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _target_user(user_id: int) -> User:
    return get_object_or_404(User, pk=user_id)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_users(request):
    if request.method == "GET":
        search = (request.query_params.get("q") or "").strip()[:50]
        queryset = User.objects.all().order_by("username")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(display_name__icontains=search)
            )

        paginator = UserPagination()
        page = paginator.paginate_queryset(queryset, request, view=admin_users)
        serializer = UserSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = UserCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        user = User.objects.create_user(
            username=data["username"],
            display_name=data["display_name"],
            password=data["password"],
            role=data.get("role", User.Role.USER),
            must_change_password=True,
            created_by=request.user,
        )
    except IntegrityError:
        return Response(
            {"username": ["这个用户名已经被使用。"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "user_created actor=%s target=%s role=%s",
        request.user.username,
        user.username,
        user.role,
    )
    record_audit(
        request, "user_created", **target_user(user), detail={"role": user.role}
    )
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_detail(request, user_id: int):
    target = _target_user(user_id)

    if request.method == "GET":
        return Response(UserSerializer(target).data)

    serializer = UserUpdateSerializer(target, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    logger.info(
        "user_updated actor=%s target=%s field=display_name",
        request.user.username,
        target.username,
    )
    record_audit(
        request, "user_updated", **target_user(target),
        detail={"fields": sorted(serializer.validated_data)},
    )
    return Response(UserSerializer(target).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_role(request, user_id: int):
    target = _target_user(user_id)
    if target.pk == request.user.pk:
        return Response(
            {"detail": "不能修改自己的角色。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = RoleUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    new_role = serializer.validated_data["role"]

    if (
        target.is_active
        and target.role == User.Role.ADMIN
        and new_role != User.Role.ADMIN
        and is_last_active_admin(target)
    ):
        return Response(
            {"detail": "系统必须至少保留一名启用中的管理员。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target.role != new_role:
        target.role = new_role
        target.save(update_fields=["role", "updated_at"])
        logger.info(
            "user_role_changed actor=%s target=%s role=%s",
            request.user.username,
            target.username,
            new_role,
        )
        record_audit(
            request, "user_role_changed", **target_user(target),
            detail={"role": new_role},
        )

    return Response(UserSerializer(target).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_disable(request, user_id: int):
    target = _target_user(user_id)
    if target.pk == request.user.pk:
        return Response(
            {"detail": "不能停用自己的账号。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target.is_active and is_last_active_admin(target):
        return Response(
            {"detail": "系统必须至少保留一名启用中的管理员。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target.is_active:
        target.is_active = False
        target.save(update_fields=["is_active", "updated_at"])
        delete_user_sessions(target)
        logger.info(
            "user_disabled actor=%s target=%s",
            request.user.username,
            target.username,
        )
        record_audit(request, "user_disabled", **target_user(target))

    return Response(UserSerializer(target).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_enable(request, user_id: int):
    target = _target_user(user_id)
    if not target.is_active:
        target.is_active = True
        target.failed_login_attempts = 0
        target.locked_until = None
        target.save(
            update_fields=[
                "is_active",
                "failed_login_attempts",
                "locked_until",
                "updated_at",
            ]
        )
        logger.info(
            "user_enabled actor=%s target=%s",
            request.user.username,
            target.username,
        )
        record_audit(request, "user_enabled", **target_user(target))

    return Response(UserSerializer(target).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_reset_password(request, user_id: int):
    target = _target_user(user_id)
    if target.pk == request.user.pk:
        return Response(
            {"detail": "请使用“修改密码”修改自己的密码。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ResetPasswordSerializer(
        data=request.data, context={"target_user": target}
    )
    serializer.is_valid(raise_exception=True)

    target.set_password(serializer.validated_data["new_password"])
    target.must_change_password = True
    target.failed_login_attempts = 0
    target.locked_until = None
    target.save(
        update_fields=[
            "password",
            "must_change_password",
            "failed_login_attempts",
            "locked_until",
            "updated_at",
        ]
    )
    delete_user_sessions(target)
    logger.info(
        "user_password_reset actor=%s target=%s",
        request.user.username,
        target.username,
    )
    record_audit(request, "user_password_reset", **target_user(target))
    return Response(
        {"detail": "密码已重置；用户下次登录时必须修改密码。"}
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_user_unlock(request, user_id: int):
    target = _target_user(user_id)
    reset_login_failures(target)
    logger.info(
        "user_unlocked actor=%s target=%s",
        request.user.username,
        target.username,
    )
    record_audit(request, "user_unlocked", **target_user(target))
    return Response(UserSerializer(target).data)
