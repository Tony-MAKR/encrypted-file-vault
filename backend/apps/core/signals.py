"""Database connection setup.

SQLite's defaults are not ideal for a small multi-user application. WAL mode
allows readers and a writer to coexist, foreign keys are off by default in
SQLite, and a busy timeout avoids immediate "database is locked" failures.
"""

from __future__ import annotations

import logging

from django.db.backends.signals import connection_created
from django.dispatch import receiver

logger = logging.getLogger("apps.core.database")


@receiver(connection_created, dispatch_uid="core.configure_sqlite")
def configure_sqlite_connection(sender, connection, **kwargs) -> None:
    if connection.vendor != "sqlite":
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA busy_timeout = 20000;")
            cursor.execute("PRAGMA journal_mode = WAL;")
    except Exception as exc:  # pragma: no cover - depends on the runtime DB
        # A failure here should be visible but must not make the application
        # unusable with an unhelpful crash. The error class is enough for logs.
        logger.warning("无法配置 SQLite 连接参数：%s", exc.__class__.__name__)
