"""Validation helpers for security-critical Django settings."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

MIN_SECRET_KEY_LENGTH = 40
_PLACEHOLDER_PREFIXES = (
    "replace-",
    "changeme",
    "change-me",
    "your-secret",
    "django-insecure",
)


def validate_secret_key(value: str | None) -> str:
    """Return a usable Django secret key or fail with an actionable message.

    The setup script writes a random key to ``.env``. We deliberately refuse
    short or placeholder values so a copied example file cannot start the app.
    """

    if value is None or not value.strip():
        raise ImproperlyConfigured(
            "缺少 DJANGO_SECRET_KEY。请先运行 scripts/setup-dev.ps1，"
            "或在 .env 中设置一个至少 40 位的随机值。"
        )

    secret = value.strip()
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY 太短，至少需要 40 位。"
            "请删除 .env 后重新运行 scripts/setup-dev.ps1，或手动生成随机值。"
        )

    if secret.lower().startswith(_PLACEHOLDER_PREFIXES):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY 仍是示例占位值，不能用于启动。"
            "请运行 scripts/setup-dev.ps1 自动生成，或手动替换为随机值。"
        )

    return secret
