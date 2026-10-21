"""Read-only deployment security checks.

The command never changes configuration or data. It prints one line per check
and exits with status 1 when any check fails.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.audit.models import BackupRecord

_PLACEHOLDER_PREFIXES = (
    "replace-",
    "changeme",
    "change-me",
    "your-secret",
    "django-insecure",
)


class Command(BaseCommand):
    help = "检查调试开关、密钥、目录、备份和磁盘空间等部署安全项。"

    def handle(self, *args, **options):
        results: list[tuple[str, str, str]] = []

        def add(status: str, title: str, message: str) -> None:
            results.append((status, title, message))

        # 1. Debug flag
        if settings.DEBUG:
            add("fail", "调试开关", "DEBUG 处于开启状态，生产环境必须关闭。")
        else:
            add("pass", "调试开关", "DEBUG 已关闭。")

        # 2. Django secret key
        secret = str(getattr(settings, "SECRET_KEY", "") or "")
        if len(secret.strip()) < 40 or secret.strip().lower().startswith(
            _PLACEHOLDER_PREFIXES
        ):
            add("fail", "Django 密钥", "SECRET_KEY 太短或仍是占位值。")
        else:
            add("pass", "Django 密钥", "SECRET_KEY 长度和格式正常。")

        # 3. Allowed hosts
        if "*" in [str(host) for host in settings.ALLOWED_HOSTS]:
            add("fail", "允许的主机名", "ALLOWED_HOSTS 不能使用通配符。")
        else:
            add("pass", "允许的主机名", "ALLOWED_HOSTS 使用明确的主机名。")

        # 4. Data directories
        directories = {
            "数据目录": Path(settings.DATA_DIR),
            "数据库目录": Path(settings.DB_DIR),
            "密文目录": Path(settings.VAULT_OBJECTS_DIR),
            "密钥目录": Path(settings.KEYS_DIR),
            "备份目录": Path(settings.BACKUP_DIR),
            "临时目录": Path(settings.VAULT_TMP_DIR),
        }
        missing = [name for name, path in directories.items() if not path.is_dir()]
        if missing:
            add("fail", "数据目录", f"缺少目录：{'、'.join(missing)}。")
        else:
            unwritable = [
                name for name, path in directories.items() if not os.access(path, os.W_OK)
            ]
            if unwritable:
                add("fail", "数据目录", f"目录不可写：{'、'.join(unwritable)}。")
            else:
                add("pass", "数据目录", "数据库、密文、密钥、备份目录均存在且可写。")

        # 5. Key file permissions
        key_path = Path(settings.VAULT_KEY_FILE)
        if not key_path.is_file():
            add("warn", "主密钥文件", "尚未初始化保险箱，未找到主密钥文件。")
        elif os.name == "nt":
            add(
                "info",
                "主密钥文件",
                "Windows 权限位不可靠，请用文件属性确认只有当前用户可访问。",
            )
        else:
            mode = key_path.stat().st_mode
            if mode & 0o077:
                add("warn", "主密钥文件", "文件权限过宽，建议设置为仅所有者可读写。")
            else:
                add("pass", "主密钥文件", "文件权限仅所有者可读写。")

        # 6. Latest backup age
        reminder_days = int(getattr(settings, "BACKUP_REMINDER_DAYS", 7))
        latest = BackupRecord.objects.order_by("-created_at", "-id").first()
        if latest is None:
            add("warn", "最近备份", "还没有创建过备份，请尽快创建并离线保存。")
        else:
            days = max(0, (timezone.now() - latest.created_at).days)
            if days > reminder_days:
                add(
                    "warn",
                    "最近备份",
                    f"最近一次备份在 {days} 天前（建议不超过 {reminder_days} 天）。",
                )
            else:
                add("pass", "最近备份", f"最近一次备份在 {days} 天前。")

        # 7. Disk space
        try:
            free = shutil.disk_usage(settings.BACKUP_DIR).free
            free_gb = free / (1024**3)
            if free < 500 * 1024 * 1024:
                add("fail", "磁盘空间", f"备份目录所在磁盘仅剩 {free_gb:.1f} GB。")
            elif free < 2 * 1024 * 1024 * 1024:
                add("warn", "磁盘空间", f"磁盘剩余 {free_gb:.1f} GB，建议清理空间。")
            else:
                add("pass", "磁盘空间", f"磁盘剩余 {free_gb:.1f} GB。")
        except OSError as exc:
            add("warn", "磁盘空间", f"无法读取磁盘空间：{exc.__class__.__name__}。")

        # 8. Audit retention
        retention = int(getattr(settings, "AUDIT_RETENTION_DAYS", 180))
        if 30 <= retention <= 3650:
            add("pass", "审计保留期", f"当前保留 {retention} 天。")
        else:
            add("warn", "审计保留期", f"保留天数 {retention} 不在建议范围 30–3650 内。")

        # 9. HTTPS readiness
        if getattr(settings, "SESSION_COOKIE_SECURE", False):
            add("pass", "HTTPS", "安全 Cookie 已启用。")
        else:
            add(
                "warn",
                "HTTPS",
                "当前为本机 HTTP 模式；开放局域网或公网前必须启用 HTTPS。",
            )

        # 10. Built frontend
        dist_index = Path(settings.FRONTEND_DIST_DIR) / "index.html"
        if dist_index.is_file():
            add("pass", "网页资源", "前端构建产物存在。")
        else:
            add("warn", "网页资源", "未找到前端构建产物，请运行 npm run build。")

        symbols = {
            "pass": ("[通过]", self.style.SUCCESS),
            "warn": ("[警告]", self.style.WARNING),
            "fail": ("[失败]", self.style.ERROR),
            "info": ("[提示]", self.style.NOTICE),
        }
        for status, title, message in results:
            label, color = symbols[status]
            self.stdout.write(f"{color(label)} {title}：{message}")

        failures = sum(1 for status, _title, _message in results if status == "fail")
        warnings = sum(1 for status, _title, _message in results if status == "warn")
        self.stdout.write("")
        self.stdout.write(f"检查完成：{failures} 项失败，{warnings} 项警告。")
        if failures:
            raise CommandError("存在失败项，请按上面的提示处理后重新检查。")
