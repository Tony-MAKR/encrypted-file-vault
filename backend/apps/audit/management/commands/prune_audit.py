"""Delete audit records older than the retention period."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.audit.models import AuditEvent


class Command(BaseCommand):
    help = "删除超过保留期的审计记录，并写入一条清理记录。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="保留天数；默认读取 AUDIT_RETENTION_DAYS。",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只显示将删除的数量，不实际删除。",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = int(getattr(settings, "AUDIT_RETENTION_DAYS", 180))
        if days < 1 or days > 3650:
            raise CommandError("保留天数必须在 1 到 3650 之间。")

        cutoff = timezone.now() - timedelta(days=days)
        queryset = AuditEvent.objects.filter(created_at__lt=cutoff)
        count = queryset.count()

        if count == 0:
            self.stdout.write("没有需要清理的审计记录。")
            return

        first = queryset.order_by("created_at").first()
        last = queryset.order_by("-created_at").first()
        self.stdout.write(
            f"将清理 {count} 条早于 {cutoff.isoformat()} 的记录"
            f"（{first.created_at.isoformat()} 至 {last.created_at.isoformat()}）。"
        )

        if options["dry_run"]:
            self.stdout.write("这是试运行，没有删除任何记录。")
            return

        deleted, _ = queryset.delete()
        AuditEvent.objects.create(
            actor=None,
            actor_username="system",
            actor_role="",
            action="audit_pruned",
            target_type="audit",
            target_label="审计记录",
            result=AuditEvent.Result.SUCCESS,
            detail={
                "deleted": deleted,
                "retention_days": days,
                "cutoff": cutoff.isoformat(),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"已清理 {deleted} 条审计记录，并写入清理记录。")
        )
