"""Append-only audit events and backup history.

Neither table stores passwords, master passwords, keys, plaintext content or
original file names. ``detail`` is a small structured dictionary written by
trusted code only.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """One recorded operation. Records are never edited through the API."""

    class Result(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILURE = "failure", "失败"
        DENIED = "denied", "被拒绝"

    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="发生时间"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name="操作人",
    )
    actor_username = models.CharField(
        max_length=150, blank=True, default="", db_index=True, verbose_name="用户名快照"
    )
    actor_role = models.CharField(
        max_length=16, blank=True, default="", verbose_name="角色快照"
    )
    action = models.CharField(
        max_length=64, blank=True, default="", db_index=True, verbose_name="操作"
    )
    target_type = models.CharField(
        max_length=32, blank=True, default="", verbose_name="对象类型"
    )
    target_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="对象编号"
    )
    target_label = models.CharField(
        max_length=200, blank=True, default="", verbose_name="对象标签"
    )
    result = models.CharField(
        max_length=16,
        choices=Result.choices,
        default=Result.SUCCESS,
        verbose_name="结果",
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, verbose_name="来源地址"
    )
    request_id = models.CharField(
        max_length=64, blank=True, default="", verbose_name="请求编号"
    )
    detail = models.JSONField(default=dict, blank=True, verbose_name="安全细节")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["action", "created_at"], name="audit_action_time_idx"
            ),
            models.Index(
                fields=["actor_username", "created_at"],
                name="audit_actor_time_idx",
            ),
        ]
        verbose_name = "审计记录"
        verbose_name_plural = "审计记录"

    def __str__(self) -> str:
        return f"{self.actor_username or 'system'} {self.action}"


class BackupRecord(models.Model):
    """Metadata about a created backup package. No passphrase is stored."""

    class Status(models.TextChoices):
        CREATED = "created", "已创建"
        VERIFIED = "verified", "已验证"
        FAILED = "failed", "验证失败"

    filename = models.CharField(max_length=255, verbose_name="文件名")
    size_bytes = models.BigIntegerField(default=0, verbose_name="大小")
    sha256 = models.CharField(max_length=64, blank=True, default="", verbose_name="SHA-256")
    format_version = models.PositiveSmallIntegerField(
        default=1, verbose_name="格式版本"
    )
    app_version = models.CharField(
        max_length=32, blank=True, default="", verbose_name="应用版本"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="创建时间"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backup_records",
        verbose_name="创建人",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="状态",
    )
    verified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="最近验证时间"
    )
    note = models.CharField(
        max_length=200, blank=True, default="", verbose_name="说明"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "备份记录"
        verbose_name_plural = "备份记录"

    def __str__(self) -> str:
        return self.filename
