"""Stage 7: read-only deployment security check."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import BackupRecord


@pytest.mark.django_db
def test_security_check_reports_passes_and_warnings(settings):
    settings.DEBUG = False
    output = StringIO()

    call_command("security_check", stdout=output)

    text = output.getvalue()
    assert "[通过] 调试开关" in text
    assert "[通过] Django 密钥" in text
    assert "[通过] 数据目录" in text
    assert "[警告] 最近备份" in text
    assert "检查完成" in text


@pytest.mark.django_db
def test_security_check_fails_when_debug_is_on(settings):
    settings.DEBUG = True
    output = StringIO()

    with pytest.raises(CommandError):
        call_command("security_check", stdout=output)

    assert "[失败] 调试开关" in output.getvalue()


@pytest.mark.django_db
def test_security_check_recognises_recent_backup(admin_user, settings):
    BackupRecord.objects.create(
        filename="vault-backup-test.efbak",
        size_bytes=1024,
        sha256="a" * 64,
        created_by=admin_user,
    )
    settings.DEBUG = False
    output = StringIO()

    call_command("security_check", stdout=output)

    assert "[通过] 最近备份" in output.getvalue()
