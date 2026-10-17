"""Application configuration for the core app."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "核心基础"

    def ready(self) -> None:
        # Register SQLite PRAGMA setup. The import is intentionally local to
        # avoid touching database connections while the app registry loads.
        from . import signals  # noqa: F401
