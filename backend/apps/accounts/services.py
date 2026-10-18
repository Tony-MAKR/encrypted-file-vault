"""Account security operations shared by views and tests."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import User


def _max_failed_attempts() -> int:
    return max(1, int(getattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5)))


def _lockout_minutes() -> int:
    return max(1, int(getattr(settings, "LOGIN_LOCKOUT_MINUTES", 15)))


def active_admin_count(exclude_pk: int | None = None) -> int:
    """Count enabled administrators, optionally excluding one user."""

    query = User.objects.filter(is_active=True, role=User.Role.ADMIN)
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    return query.count()


def is_last_active_admin(user: User) -> bool:
    """Return True if disabling/demoting this user would leave no admin."""

    return bool(
        user.is_active
        and user.role == User.Role.ADMIN
        and active_admin_count(exclude_pk=user.pk) == 0
    )


def clear_expired_lock(user: User) -> None:
    """A lock that has expired should not keep counting old failures."""

    if user.locked_until and user.locked_until <= timezone.now():
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])


def register_login_failure(user: User) -> bool:
    """Record one failed attempt and return True when this attempt locks it."""

    if not user.is_active:
        return False

    user.failed_login_attempts += 1
    newly_locked = False
    if user.failed_login_attempts >= _max_failed_attempts():
        user.locked_until = timezone.now() + timedelta(minutes=_lockout_minutes())
        newly_locked = True

    user.save(
        update_fields=["failed_login_attempts", "locked_until", "updated_at"]
    )
    return newly_locked


def reset_login_failures(user: User) -> None:
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])


def delete_user_sessions(user: User, except_session_key: str | None = None) -> None:
    """Invalidate database-backed sessions belonging to ``user``.

    Session rows do not store the user ID as a queryable column, so we decode
    the small number of unexpired sessions. This is acceptable for a small
    single-host deployment and avoids adding a custom session table.
    """

    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now).iterator():
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if data.get("_auth_user_id") != str(user.pk):
            continue
        if except_session_key and session.session_key == except_session_key:
            continue
        session.delete()
