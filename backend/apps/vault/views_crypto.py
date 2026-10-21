"""Vault initialization, unlock and lock endpoints."""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.audit.services import record_audit, target_vault

from . import crypto
from .serializers import VaultInitializeSerializer, VaultUnlockSerializer
from .throttles import VaultUnlockThrottle

logger = logging.getLogger("apps.vault")


def status_payload() -> dict:
    return {
        "initialized": crypto.is_initialized(),
        "unlocked": crypto.is_unlocked(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vault_status(request):
    return Response(status_payload())


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def vault_initialize(request):
    if crypto.is_initialized():
        return Response(
            {
                "detail": "保险箱已经初始化，不能重复设置主密码。",
                "code": "vault_already_initialized",
            },
            status=status.HTTP_409_CONFLICT,
        )

    serializer = VaultInitializeSerializer(
        data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    try:
        crypto.initialize(serializer.validated_data["master_password"])
    except crypto.VaultAlreadyInitialized:
        return Response(
            {
                "detail": "保险箱已经初始化，不能重复设置主密码。",
                "code": "vault_already_initialized",
            },
            status=status.HTTP_409_CONFLICT,
        )
    except crypto.VaultError:
        logger.exception(
            "vault_initialize_failed actor=%s", request.user.username
        )
        return Response(
            {
                "detail": "保险箱初始化失败，请检查数据目录权限和磁盘空间。",
                "code": "vault_initialize_failed",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info("vault_initialized actor=%s", request.user.username)
    record_audit(request, "vault_initialized", **target_vault())
    return Response(status_payload(), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
@throttle_classes([VaultUnlockThrottle])
def vault_unlock(request):
    if not crypto.is_initialized():
        return Response(
            {
                "detail": "保险箱还没有设置主密码。",
                "code": "vault_not_initialized",
            },
            status=status.HTTP_409_CONFLICT,
        )

    serializer = VaultUnlockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        crypto.unlock(serializer.validated_data["master_password"])
    except crypto.InvalidMasterPassword:
        logger.warning(
            "vault_unlock_failed actor=%s reason=bad_password",
            request.user.username,
        )
        record_audit(
            request, "vault_unlock_failed", **target_vault(),
            result="failure", detail={"reason": "bad_password"},
        )
        return Response(
            {
                "detail": "主密码不正确。",
                "code": "invalid_master_password",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except crypto.VaultError:
        logger.warning(
            "vault_unlock_failed actor=%s reason=key_file",
            request.user.username,
        )
        record_audit(
            request, "vault_unlock_failed", **target_vault(),
            result="failure", detail={"reason": "key_file"},
        )
        return Response(
            {
                "detail": "密钥文件无法读取或已损坏，请联系维护者。",
                "code": "vault_key_error",
            },
            status=status.HTTP_409_CONFLICT,
        )

    logger.info("vault_unlocked actor=%s", request.user.username)
    record_audit(request, "vault_unlocked", **target_vault())
    return Response(status_payload())


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def vault_lock(request):
    crypto.lock()
    logger.info("vault_locked actor=%s", request.user.username)
    record_audit(request, "vault_locked", **target_vault())
    return Response(status_payload())
