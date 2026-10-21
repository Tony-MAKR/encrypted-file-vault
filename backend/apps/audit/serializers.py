"""Serializers for audit records, backup history and backup actions."""

from __future__ import annotations

from rest_framework import serializers

from .actions import action_category, action_label
from .models import AuditEvent, BackupRecord


class AuditEventSerializer(serializers.ModelSerializer):
    action_label = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    result_label = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "actor_username",
            "actor_role",
            "action",
            "action_label",
            "category",
            "target_type",
            "target_id",
            "target_label",
            "result",
            "result_label",
            "ip_address",
            "request_id",
            "detail",
        ]

    def get_action_label(self, obj: AuditEvent) -> str:
        return action_label(obj.action)

    def get_category(self, obj: AuditEvent) -> str:
        return action_category(obj.action)


class BackupRecordSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=""
    )
    file_exists = serializers.SerializerMethodField()

    class Meta:
        model = BackupRecord
        fields = [
            "id",
            "filename",
            "size_bytes",
            "sha256",
            "format_version",
            "app_version",
            "created_at",
            "created_by_username",
            "status",
            "status_label",
            "verified_at",
            "note",
            "file_exists",
        ]

    def get_file_exists(self, obj: BackupRecord) -> bool:
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BACKUP_DIR) / obj.filename).is_file()


class BackupCreateSerializer(serializers.Serializer):
    passphrase = serializers.CharField(
        min_length=12,
        max_length=256,
        trim_whitespace=True,
        error_messages={
            "min_length": "备份口令至少需要 12 位。",
            "max_length": "备份口令太长。",
            "blank": "请输入备份口令。",
        },
    )
    passphrase_confirm = serializers.CharField(
        min_length=1,
        max_length=256,
        trim_whitespace=True,
        error_messages={"blank": "请再次输入备份口令。"},
    )
    note = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["passphrase"] != attrs["passphrase_confirm"]:
            raise serializers.ValidationError(
                {"passphrase_confirm": "两次输入的备份口令不一致。"}
            )
        return attrs


class BackupVerifySerializer(serializers.Serializer):
    passphrase = serializers.CharField(
        min_length=1,
        max_length=256,
        trim_whitespace=True,
        error_messages={"blank": "请输入备份口令。"},
    )
