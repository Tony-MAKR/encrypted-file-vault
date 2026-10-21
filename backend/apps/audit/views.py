"""Administrator audit, backup and system-status endpoints."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, time
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.models import User
from apps.vault import crypto

from . import backup as backup_service
from .actions import (
    ACTION_CATALOG,
    CATEGORY_LABELS,
    RESULT_LABELS,
)
from .models import AuditEvent, BackupRecord
from .serializers import (
    AuditEventSerializer,
    BackupCreateSerializer,
    BackupRecordSerializer,
    BackupVerifySerializer,
)
from .services import (
    record_audit,
    target_backup,
)

logger = logging.getLogger("apps.audit")


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class BackupPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class BackupActionThrottle(UserRateThrottle):
    scope = "backup_action"
    rate = "10/min"

    def allow_request(self, request, view):
        # Reading the backup list is harmless; only creating and verifying
        # (which test a passphrase) are rate limited.
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)


def _require_admin(request) -> None:
    """Hide these pages from normal users entirely."""

    user = request.user
    if not (
        user
        and user.is_authenticated
        and user.is_active
        and user.role == User.Role.ADMIN
    ):
        raise NotFound("找不到这个页面。")


def _parse_date(value: str, *, end: bool) -> datetime | None:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (AttributeError, ValueError):
        return None
    current = timezone.get_current_timezone()
    moment = datetime.combine(parsed, time.max if end else time.min)
    return timezone.make_aware(moment, current)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_audit(request):
    _require_admin(request)

    queryset = AuditEvent.objects.all()
    search = (request.query_params.get("q") or "").strip()[:50]
    action = (request.query_params.get("action") or "").strip()[:64]
    category = (request.query_params.get("category") or "").strip()[:32]
    result = (request.query_params.get("result") or "").strip()[:16]
    date_from = (request.query_params.get("date_from") or "").strip()
    date_to = (request.query_params.get("date_to") or "").strip()

    if search:
        queryset = queryset.filter(
            Q(actor_username__icontains=search)
            | Q(target_label__icontains=search)
        )
    if action:
        queryset = queryset.filter(action=action)
    elif category:
        allowed = [
            key for key, (_label, cat) in ACTION_CATALOG.items() if cat == category
        ]
        queryset = queryset.filter(action__in=allowed)
    if result in AuditEvent.Result.values:
        queryset = queryset.filter(result=result)

    parsed_from = _parse_date(date_from, end=False) if date_from else None
    parsed_to = _parse_date(date_to, end=True) if date_to else None
    if parsed_from is not None:
        queryset = queryset.filter(created_at__gte=parsed_from)
    if parsed_to is not None:
        queryset = queryset.filter(created_at__lte=parsed_to)

    queryset = queryset.order_by("-created_at", "-id")
    paginator = AuditPagination()
    page = paginator.paginate_queryset(queryset, request, view=admin_audit)
    serializer = AuditEventSerializer(page, many=True)
    response = paginator.get_paginated_response(serializer.data)

    record_audit(
        request,
        "audit_viewed",
        detail={
            "q": search,
            "action": action,
            "category": category,
            "result": result,
            "date_from": date_from,
            "date_to": date_to,
            "returned": len(serializer.data),
        },
    )
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_audit_options(request):
    _require_admin(request)
    categories = []
    for key, label in CATEGORY_LABELS.items():
        actions = [
            {"value": action, "label": display_label}
            for action, (display_label, action_category) in ACTION_CATALOG.items()
            if action_category == key
        ]
        if actions:
            categories.append(
                {"value": key, "label": label, "actions": actions}
            )
    return Response(
        {
            "categories": categories,
            "results": [
                {"value": key, "label": label}
                for key, label in RESULT_LABELS.items()
            ],
        }
    )


def _backup_summary() -> dict:
    now = timezone.now()
    latest = BackupRecord.objects.order_by("-created_at", "-id").first()
    reminder_days = int(getattr(settings, "BACKUP_REMINDER_DAYS", 7))
    days_since = None
    reminder_due = True
    if latest is not None:
        days_since = max(0, (now - latest.created_at).days)
        reminder_due = days_since > reminder_days
    return {
        "last_backup_at": latest.created_at.isoformat() if latest else None,
        "last_filename": latest.filename if latest else "",
        "last_status": latest.status if latest else "",
        "days_since_last_backup": days_since,
        "reminder_days": reminder_days,
        "reminder_due": reminder_due,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([BackupActionThrottle])
def admin_backups(request):
    _require_admin(request)

    if request.method == "GET":
        records = BackupRecord.objects.select_related("created_by").order_by(
            "-created_at", "-id"
        )
        paginator = BackupPagination()
        page = paginator.paginate_queryset(records, request, view=admin_backups)
        serializer = BackupRecordSerializer(page, many=True)
        payload = paginator.get_paginated_response(serializer.data).data
        payload["summary"] = _backup_summary()
        payload["backup_reminder_days"] = int(
            getattr(settings, "BACKUP_REMINDER_DAYS", 7)
        )
        return Response(payload)

    serializer = BackupCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        result = backup_service.create_backup(
            data["passphrase"], note=data.get("note", ""), user=request.user
        )
    except backup_service.BackupSpaceError as exc:
        record_audit(
            request,
            "backup_created",
            result=AuditEvent.Result.FAILURE,
            detail={"reason": "insufficient_space"},
        )
        return Response(
            {"detail": str(exc), "code": "insufficient_space"},
            status=status.HTTP_507_INSUFFICIENT_STORAGE,
        )
    except backup_service.BackupBusy as exc:
        return Response(
            {"detail": str(exc), "code": "backup_busy"},
            status=status.HTTP_409_CONFLICT,
        )
    except backup_service.BackupError as exc:
        record_audit(
            request,
            "backup_created",
            result=AuditEvent.Result.FAILURE,
            detail={"reason": "backup_error"},
        )
        return Response(
            {"detail": str(exc), "code": "backup_failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.exception("backup_create_failed actor=%s", request.user.username)
        record_audit(
            request,
            "backup_created",
            result=AuditEvent.Result.FAILURE,
            detail={"reason": "unexpected"},
        )
        return Response(
            {
                "detail": "备份创建失败，请检查磁盘空间和目录权限。",
                "code": "backup_failed",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    record = BackupRecord.objects.filter(filename=result.filename).first()
    if record is not None:
        record_audit(
            request,
            "backup_created",
            **target_backup(record),
            detail={
                "size_bytes": result.size_bytes,
                "sha256": result.sha256,
                "counts": result.counts,
            },
        )
    return Response(
        {
            "detail": "备份已创建。请把备份文件复制到另一块硬盘或另一台电脑。",
            "backup": BackupRecordSerializer(record).data if record else None,
            "sha256": result.sha256,
            "counts": result.counts,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([BackupActionThrottle])
def admin_backup_verify(request, backup_id: int):
    _require_admin(request)
    record = BackupRecord.objects.filter(pk=backup_id).first()
    if record is None:
        raise NotFound("找不到这个备份记录。")

    path = Path(settings.BACKUP_DIR) / record.filename
    if not path.is_file():
        return Response(
            {
                "detail": "备份文件已不在备份目录中，请检查文件是否被移动。",
                "code": "backup_file_missing",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = BackupVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        manifest = backup_service.verify_backup_file(
            path, serializer.validated_data["passphrase"]
        )
    except backup_service.BackupPasswordError as exc:
        record.status = BackupRecord.Status.FAILED
        record.save(update_fields=["status"])
        record_audit(
            request,
            "backup_verify_failed",
            **target_backup(record),
            result=AuditEvent.Result.FAILURE,
            detail={"reason": "bad_passphrase"},
        )
        return Response(
            {"detail": str(exc), "code": "invalid_backup_passphrase"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except backup_service.BackupError as exc:
        record.status = BackupRecord.Status.FAILED
        record.save(update_fields=["status"])
        record_audit(
            request,
            "backup_verify_failed",
            **target_backup(record),
            result=AuditEvent.Result.FAILURE,
            detail={"reason": "integrity"},
        )
        return Response(
            {"detail": str(exc), "code": "backup_integrity_failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.exception("backup_verify_failed actor=%s", request.user.username)
        return Response(
            {"detail": "备份验证失败，请稍后重试。", "code": "backup_verify_failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    record.status = BackupRecord.Status.VERIFIED
    record.verified_at = timezone.now()
    record.save(update_fields=["status", "verified_at"])
    record_audit(
        request,
        "backup_verified",
        **target_backup(record),
        detail={"counts": manifest.get("counts", {})},
    )
    return Response(
        {
            "detail": "备份验证通过。",
            "created_at": manifest.get("created_at"),
            "app_version": manifest.get("app_version"),
            "counts": manifest.get("counts", {}),
            "object_count": len(manifest.get("objects", [])),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_system_status(request):
    _require_admin(request)

    database_path = Path(settings.DATABASES["default"]["NAME"])
    objects_dir = Path(settings.VAULT_OBJECTS_DIR)
    objects = list(objects_dir.glob("*.vault")) if objects_dir.is_dir() else []
    backup_dir = Path(settings.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(backup_dir)
    summary = _backup_summary()

    return Response(
        {
            "version": settings.APP_VERSION,
            "database_size_bytes": (
                database_path.stat().st_size if database_path.is_file() else 0
            ),
            "object_count": len(objects),
            "object_size_bytes": sum(path.stat().st_size for path in objects),
            "disk_free_bytes": usage.free,
            "audit_count": AuditEvent.objects.count(),
            "vault": {
                "initialized": crypto.is_initialized(),
                "unlocked": crypto.is_unlocked(),
            },
            "backup": summary,
            "trash_retention_days": int(
                getattr(settings, "VAULT_TRASH_RETENTION_DAYS", 30)
            ),
            "audit_retention_days": int(
                getattr(settings, "AUDIT_RETENTION_DAYS", 180)
            ),
        }
    )
