"""Custom user model for the encrypted vault.

The project uses a custom user model from the start. That gives us clean fields
for the role, display name, forced password change and login lockout without
bolting a profile table onto Django's generic user table.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

USERNAME_VALIDATOR = RegexValidator(
    regex=r"^[a-z0-9_-]{3,32}$",
    message="用户名只能包含小写字母、数字、下划线和连字符，长度 3–32 位。",
)


class User(AbstractUser):
    """Application user with an explicit administrator/user role."""

    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        USER = "user", "普通用户"

    # Override AbstractUser's username field so login names are short,
    # predictable and case-insensitive (save() lowercases them).
    username = models.CharField(
        max_length=32,
        unique=True,
        validators=[USERNAME_VALIDATOR],
        error_messages={"unique": "这个用户名已经被使用。"},
        help_text="登录名，只能使用小写字母、数字、下划线和连字符。",
        verbose_name="用户名",
    )
    display_name = models.CharField(max_length=50, verbose_name="显示名")
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.USER,
        verbose_name="角色",
    )
    must_change_password = models.BooleanField(default=False, verbose_name="必须修改密码")
    failed_login_attempts = models.PositiveSmallIntegerField(
        default=0, verbose_name="连续登录失败次数"
    )
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="锁定截止时间")
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_users",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["username"]
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def save(self, *args, **kwargs):
        if self.username:
            self.username = self.username.strip().lower()
        if isinstance(self.display_name, str):
            self.display_name = self.display_name.strip()
        super().save(*args, **kwargs)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN

    def __str__(self) -> str:
        return self.display_name or self.username
