"""Groups, item metadata and authorization records.

Stage 3 deliberately stores only item *metadata*. Encrypted file and text
content is added in stage 4, so none of these tables contain secrets yet.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class VaultGroup(models.Model):
    """A flat group of users that can receive access to vault items."""

    name = models.CharField(
        max_length=50,
        unique=True,
        error_messages={"unique": "这个用户组名称已经被使用。"},
        verbose_name="名称",
    )
    description = models.TextField(
        max_length=500, blank=True, default="", verbose_name="说明"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_vault_groups",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["name"]
        verbose_name = "用户组"
        verbose_name_plural = "用户组"

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        if isinstance(self.description, str):
            self.description = self.description.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class GroupMembership(models.Model):
    """Which users belong to a group. One row per user/group pair."""

    group = models.ForeignKey(
        VaultGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="用户组",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vault_group_memberships",
        verbose_name="用户",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="加入操作人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="加入时间")

    class Meta:
        ordering = ["group_id", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"], name="uniq_group_membership"
            )
        ]
        indexes = [
            models.Index(fields=["user", "group"], name="idx_membership_user_group")
        ]
        verbose_name = "组成员"
        verbose_name_plural = "组成员"


class VaultItem(models.Model):
    """Metadata for a future encrypted file or text secret.

    Stage 3 does not store real content. The owner is always an administrator;
    content access is granted through ownership, group grants or user grants.
    """

    class ItemType(models.TextChoices):
        FILE = "file", "文件"
        TEXT = "text", "文字"

    title = models.CharField(max_length=120, verbose_name="标题")
    item_type = models.CharField(
        max_length=8,
        choices=ItemType.choices,
        default=ItemType.TEXT,
        verbose_name="类型",
    )
    description = models.TextField(
        max_length=1000, blank=True, default="", verbose_name="说明"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_vault_items",
        verbose_name="所有者",
    )
    is_archived = models.BooleanField(default=False, verbose_name="已归档")
    archived_at = models.DateTimeField(
        null=True, blank=True, verbose_name="归档时间"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["owner", "is_archived"], name="idx_item_owner_state"),
            models.Index(fields=["is_archived"], name="idx_item_archived"),
        ]
        verbose_name = "内容条目"
        verbose_name_plural = "内容条目"

    def save(self, *args, **kwargs):
        if self.title:
            self.title = self.title.strip()
        if isinstance(self.description, str):
            self.description = self.description.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class GroupGrant(models.Model):
    """Access to one item granted to every member of a group."""

    item = models.ForeignKey(
        VaultItem,
        on_delete=models.CASCADE,
        related_name="group_grants",
        verbose_name="内容条目",
    )
    group = models.ForeignKey(
        VaultGroup,
        # PROTECT is a database-level safety net. The API refuses to delete a
        # group while grants exist instead of silently removing access.
        on_delete=models.PROTECT,
        related_name="grants",
        verbose_name="用户组",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="授权人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="授权时间")

    class Meta:
        ordering = ["group__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "group"], name="uniq_item_group_grant"
            )
        ]
        indexes = [
            models.Index(fields=["group", "item"], name="idx_group_grant_group_item")
        ]
        verbose_name = "组授权"
        verbose_name_plural = "组授权"


class UserGrant(models.Model):
    """Access to one item granted directly to one user."""

    item = models.ForeignKey(
        VaultItem,
        on_delete=models.CASCADE,
        related_name="user_grants",
        verbose_name="内容条目",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vault_user_grants",
        verbose_name="用户",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="授权人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="授权时间")

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "user"], name="uniq_item_user_grant"
            )
        ]
        indexes = [
            models.Index(fields=["user", "item"], name="idx_user_grant_user_item")
        ]
        verbose_name = "用户授权"
        verbose_name_plural = "用户授权"
