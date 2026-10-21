"""Encrypted text and file content endpoints."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import StreamingHttpResponse
from django.middleware.csrf import (
    CSRF_TOKEN_LENGTH,
    InvalidTokenFormat,
    _check_token_format,
    _does_token_match,
    _unmask_cipher_token,
)
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.authentication import SessionAuthentication401
from apps.accounts.permissions import IsAdminRole
from apps.audit.services import record_audit, target_item

from . import content_services, crypto
from .models import VaultItem
from .serializers import (
    ItemDetailSerializer,
    PurgeItemSerializer,
    TextContentWriteSerializer,
)
from .services import can_open_content
from .throttles import VaultPurgeThrottle
from .upload import VaultEncryptingUploadHandler
from .views_admin import _item_with_related

logger = logging.getLogger("apps.vault")

CSRF_FAILED = {
    "detail": "CSRF 校验失败，请刷新页面后重试。",
    "code": "csrf_failed",
}


class SessionAuthenticationNoCsrf(SessionAuthentication401):
    """Authenticate by session without parsing the multipart body.

    The file upload view installs a custom upload handler. Django's normal CSRF
    middleware reads request.POST for multipart requests, which would process
    the upload with the default plaintext-temporary-file handler first. This
    view is csrf_exempt at the middleware level and performs a header-only CSRF
    check after the encrypting handler is installed.
    """

    def enforce_csrf(self, request) -> None:
        return None


def _enforce_header_csrf(request) -> Response | None:
    if getattr(request, "_dont_enforce_csrf_checks", False):
        return None
    secret = request.COOKIES.get(settings.CSRF_COOKIE_NAME)
    if not secret:
        return Response(CSRF_FAILED, status=status.HTTP_403_FORBIDDEN)
    try:
        _check_token_format(secret)
        if len(secret) == CSRF_TOKEN_LENGTH:
            secret = _unmask_cipher_token(secret)
        token = request.META.get(settings.CSRF_HEADER_NAME, "")
        if not token:
            return Response(CSRF_FAILED, status=status.HTTP_403_FORBIDDEN)
        _check_token_format(token)
        if not _does_token_match(token, secret):
            return Response(CSRF_FAILED, status=status.HTTP_403_FORBIDDEN)
    except InvalidTokenFormat:
        return Response(CSRF_FAILED, status=status.HTTP_403_FORBIDDEN)
    return None


def _mapped_error(exc: Exception) -> Response | None:
    if isinstance(exc, crypto.VaultLocked):
        return Response(
            {
                "detail": "保险箱尚未解锁，请联系管理员输入主密码。",
                "code": "vault_locked",
            },
            status=status.HTTP_423_LOCKED,
        )
    if isinstance(exc, crypto.VaultNotInitialized):
        return Response(
            {
                "detail": "保险箱还没有设置主密码。",
                "code": "vault_not_initialized",
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, crypto.ContentIntegrityError):
        logger.warning("content_integrity_error type=%s", type(exc).__name__)
        return Response(
            {
                "detail": "内容损坏或被篡改，无法读取。",
                "code": "content_integrity_failed",
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, content_services.ContentNotFound):
        return Response(
            {"detail": "这条条目还没有加密正文。", "code": "content_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, content_services.ContentTypeMismatch):
        return Response(
            {"detail": str(exc), "code": "content_type_mismatch"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, content_services.ContentError):
        return Response(
            {"detail": str(exc), "code": "content_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _visible_item(item_id: int, user) -> VaultItem:
    """Fetch an active item and require content access; otherwise 404."""

    item = get_object_or_404(
        VaultItem.objects.select_related("owner").filter(
            is_deleted=False, is_archived=False
        ),
        pk=item_id,
    )
    if not can_open_content(user, item):
        raise NotFound("找不到这条内容。")
    return item


def _admin_item(item_id: int) -> VaultItem:
    return get_object_or_404(
        VaultItem.objects.select_related("owner"), pk=item_id
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_text_content(request, item_id: int):
    item = _admin_item(item_id)
    if item.is_deleted:
        return Response(
            {"detail": "回收站中的条目不能编辑内容，请先恢复。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if item.item_type != VaultItem.ItemType.TEXT:
        return Response(
            {"detail": "这条条目不是文字类型。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = content_services.get_content(item)
    if existing is not None and not can_open_content(request.user, item):
        return Response(
            {
                "detail": "你还没有这条内容的访问授权，不能编辑已有内容。",
                "code": "content_permission_required",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = TextContentWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        crypto.require_master_key()
        content_services.save_text_content(
            item, request.user, serializer.validated_data
        )
    except Exception as exc:  # noqa: BLE001 - map known vault errors
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise

    logger.info(
        "text_content_saved actor=%s item_id=%s",
        request.user.username,
        item.pk,
    )
    record_audit(request, "text_saved", **target_item(item))
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([SessionAuthenticationNoCsrf])
@parser_classes([MultiPartParser])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_file_content(request, item_id: int):
    item = _admin_item(item_id)
    if item.is_deleted:
        return Response(
            {"detail": "回收站中的条目不能上传内容，请先恢复。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if item.item_type != VaultItem.ItemType.FILE:
        return Response(
            {"detail": "这条条目不是文件类型。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = content_services.get_content(item)
    if existing is not None and not can_open_content(request.user, item):
        return Response(
            {
                "detail": "你还没有这条内容的访问授权，不能替换已有文件。",
                "code": "content_permission_required",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        crypto.require_master_key()
    except Exception as exc:  # noqa: BLE001
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise

    csrf_error = _enforce_header_csrf(request._request)
    if csrf_error is not None:
        return csrf_error

    dek = secrets.token_bytes(crypto.KEY_SIZE)
    handler = VaultEncryptingUploadHandler(
        request._request,
        item_id=item.pk,
        dek=dek,
        max_size=settings.VAULT_MAX_FILE_SIZE_BYTES,
    )
    # Install the encrypting handler before anything touches request.FILES.
    request._request.upload_handlers = [handler]

    try:
        try:
            upload = request.FILES.get("file")
            if upload is None:
                upload = next(iter(request.FILES.values()), None)
        except RequestDataTooBig:
            handler.cleanup()
            return Response(
                {
                    "detail": f"文件超过 {settings.VAULT_MAX_FILE_SIZE_MB} MB 上限。",
                    "code": "file_too_large",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        except Exception:
            handler.cleanup()
            return Response(
                {"detail": "上传数据无法解析，请重新选择文件。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if upload is None:
            handler.cleanup()
            return Response(
                {"detail": "请选择要上传的文件。", "code": "file_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content_services.save_uploaded_file(
                item, request.user, upload, dek
            )
        except Exception as exc:  # noqa: BLE001
            mapped = _mapped_error(exc)
            if mapped is not None:
                return mapped
            logger.exception(
                "file_content_save_failed actor=%s item_id=%s",
                request.user.username,
                item.pk,
            )
            return Response(
                {
                    "detail": "文件保存失败，本次上传没有生效。",
                    "code": "file_save_failed",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            handler.cleanup()
    finally:
        handler.cleanup()

    logger.info(
        "file_content_saved actor=%s item_id=%s size=%s",
        request.user.username,
        item.pk,
        upload.plaintext_size,
    )
    record_audit(
        request, "file_uploaded", **target_item(item),
        detail={"size": upload.plaintext_size},
    )
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def text_content(request, item_id: int):
    item = _visible_item(item_id, request.user)
    try:
        payload = content_services.get_text_payload(item)
    except Exception as exc:  # noqa: BLE001
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise

    logger.info(
        "text_viewed actor=%s item_id=%s",
        request.user.username,
        item.pk,
    )
    record_audit(request, "text_viewed", **target_item(item))
    return Response(
        {
            "url": payload.get("url", ""),
            "username": payload.get("username", ""),
            "notes": payload.get("notes", ""),
            "has_password": bool(payload.get("password")),
            "updated_at": content_services.require_content(item).updated_at,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reveal_text_password(request, item_id: int):
    item = _visible_item(item_id, request.user)
    try:
        payload = content_services.get_text_payload(item)
    except Exception as exc:  # noqa: BLE001
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise

    password = payload.get("password", "")
    if not password:
        return Response(
            {"detail": "这条内容没有设置密码。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "text_password_revealed actor=%s item_id=%s",
        request.user.username,
        item.pk,
    )
    record_audit(request, "text_revealed", **target_item(item))
    return Response({"password": password})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def audit_text_copy(request, item_id: int):
    item = _visible_item(item_id, request.user)
    logger.info(
        "text_password_copied actor=%s item_id=%s",
        request.user.username,
        item.pk,
    )
    record_audit(request, "text_copied", **target_item(item))
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_file_content(request, item_id: int):
    item = _visible_item(item_id, request.user)
    try:
        content = content_services.require_content(item)
    except Exception as exc:  # noqa: BLE001
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise
    if content.content_type != VaultItem.ItemType.FILE:
        return Response(
            {"detail": "这条条目不是文件类型。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        metadata = content_services.verify_file_content(
            content, settings.VAULT_CHUNK_SIZE
        )
    except Exception as exc:  # noqa: BLE001
        mapped = _mapped_error(exc)
        if mapped is not None:
            return mapped
        raise

    filename = content_services.sanitize_filename(
        metadata.get("filename"), fallback="download"
    )
    mime_type = content_services.sanitize_mime_type(
        metadata.get("content_type")
    )

    logger.info(
        "file_downloaded actor=%s item_id=%s size=%s",
        request.user.username,
        item.pk,
        content.plaintext_size,
    )
    record_audit(
        request, "file_downloaded", **target_item(item),
        detail={"size": content.plaintext_size},
    )
    response = StreamingHttpResponse(
        content_services.stream_file_content(
            content, settings.VAULT_CHUNK_SIZE
        ),
        content_type=mime_type,
    )
    response["Content-Length"] = str(content.plaintext_size)
    response["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(filename)}"
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_trash(request, item_id: int):
    item = _admin_item(item_id)
    content_services.trash_item(item, request.user)
    record_audit(request, "item_trashed", **target_item(item))
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def admin_item_restore(request, item_id: int):
    item = _admin_item(item_id)
    content_services.restore_item(item, request.user)
    record_audit(request, "item_restored", **target_item(item))
    return Response(
        ItemDetailSerializer(
            _item_with_related(item.pk), context={"request": request}
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
@throttle_classes([VaultPurgeThrottle])
def admin_item_purge(request, item_id: int):
    item = _admin_item(item_id)
    if not item.is_deleted:
        return Response(
            {
                "detail": "只有回收站中的条目才能永久删除，请先删除到回收站。",
                "code": "item_not_deleted",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = PurgeItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not request.user.check_password(
        serializer.validated_data["current_password"]
    ):
        logger.warning(
            "item_purge_failed actor=%s item_id=%s reason=bad_password",
            request.user.username,
            item.pk,
        )
        record_audit(
            request, "item_purged", **target_item(item),
            result="failure", detail={"reason": "bad_password"},
        )
        return Response(
            {
                "detail": "登录密码不正确，内容没有被删除。",
                "code": "invalid_password",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    deleted_id = item.pk
    deleted_label = item.title
    content_services.purge_item(item)
    logger.info(
        "item_permanently_deleted actor=%s item_id=%s",
        request.user.username,
        deleted_id,
    )
    record_audit(
        request,
        "item_purged",
        target_type="item",
        target_id=deleted_id,
        target_label=deleted_label,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)
