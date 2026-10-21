"""Write audit events without ever storing secrets.

Audit failures must not break an already-completed business operation, so the
helper logs a warning and returns ``None`` instead of raising. ``detail`` is
restricted to JSON-safe, explicitly supplied values.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any

from django.db import DatabaseError

from .models import AuditEvent

logger = logging.getLogger("apps.audit")


def _client_ip(request) -> str | None:
    value = (request.META.get("REMOTE_ADDR") or "").strip()
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _safe_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return {}
    try:
        # Round-trip through JSON so callers cannot accidentally store model
        # objects or bytes. Unknown objects raise and are dropped.
        encoded = json.dumps(detail, ensure_ascii=False, default=str)
        value = json.loads(encoded)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def record_audit(
    request,
    action: str,
    *,
    target_type: str = "",
    target_id: int | None = None,
    target_label: str = "",
    result: str = AuditEvent.Result.SUCCESS,
    detail: dict[str, Any] | None = None,
    actor_username: str | None = None,
    actor_role: str | None = None,
) -> AuditEvent | None:
    """Best-effort audit write. Never raises to the caller."""

    user = getattr(request, "user", None)
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    username = actor_username
    role = actor_role
    if username is None:
        username = getattr(user, "username", "") if is_authenticated else ""
    if role is None:
        role = getattr(user, "role", "") if is_authenticated else ""

    try:
        return AuditEvent.objects.create(
            actor=user if is_authenticated else None,
            actor_username=(username or "")[:150],
            actor_role=(role or "")[:16],
            action=(action or "")[:64],
            target_type=(target_type or "")[:32],
            target_id=target_id,
            target_label=(target_label or "")[:200],
            result=result,
            ip_address=_client_ip(request),
            request_id=(getattr(request, "request_id", "") or "")[:64],
            detail=_safe_detail(detail),
        )
    except DatabaseError as exc:
        logger.warning(
            "audit_write_failed action=%s error=%s", action, exc.__class__.__name__
        )
        return None
    except Exception as exc:  # noqa: BLE001 - auditing must not break the app
        logger.warning(
            "audit_write_failed action=%s error=%s", action, exc.__class__.__name__
        )
        return None


def target_user(user) -> dict[str, Any]:
    return {
        "target_type": "user",
        "target_id": user.pk,
        "target_label": user.username,
    }


def target_group(group) -> dict[str, Any]:
    return {
        "target_type": "group",
        "target_id": group.pk,
        "target_label": group.name,
    }


def target_item(item) -> dict[str, Any]:
    return {
        "target_type": "item",
        "target_id": item.pk,
        "target_label": item.title,
    }


def target_backup(record) -> dict[str, Any]:
    return {
        "target_type": "backup",
        "target_id": record.pk,
        "target_label": record.filename,
    }


def target_vault() -> dict[str, Any]:
    return {"target_type": "vault", "target_id": None, "target_label": "保险箱"}
