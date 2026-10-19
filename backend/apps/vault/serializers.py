"""Validation and representation for groups, items and grants."""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import validate_password_value

from .models import VaultContent, VaultGroup, VaultItem
from .services import (
    can_open_content,
    can_view_metadata,
    effective_users_for_item,
)

EMPTY_CONTENT_NOTICE = "这条条目还没有加密正文。"
ENCRYPTED_CONTENT_NOTICE = "内容已加密保存；只有被授权的人可以查看。"


def normalize_tags(values) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise serializers.ValidationError("标签格式不正确。")
    normalized: list[str] = []
    for value in values:
        tag = str(value or "").strip()
        if not tag:
            continue
        if len(tag) > 30:
            raise serializers.ValidationError("每个标签不能超过 30 个字符。")
        if any(ord(character) < 32 for character in tag):
            raise serializers.ValidationError("标签不能包含控制字符。")
        if tag not in normalized:
            normalized.append(tag)
    if len(normalized) > 20:
        raise serializers.ValidationError("标签最多 20 个。")
    return normalized


def _content_of(item: VaultItem) -> VaultContent | None:
    cached = getattr(item, "_vault_content_cache", None)
    if cached is not None:
        return cached
    try:
        content = item.content
    except VaultContent.DoesNotExist:
        content = None
    item._vault_content_cache = content
    return content


def _has_content(item: VaultItem) -> bool:
    annotated = getattr(item, "has_content", None)
    if isinstance(annotated, bool):
        return annotated
    return _content_of(item) is not None


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "display_name", "role", "is_active")
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    granted_item_count = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = VaultGroup
        fields = (
            "id",
            "name",
            "description",
            "member_count",
            "granted_item_count",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_member_count(self, obj: VaultGroup) -> int:
        annotated = getattr(obj, "member_count", None)
        return annotated if annotated is not None else obj.memberships.count()

    def get_granted_item_count(self, obj: VaultGroup) -> int:
        annotated = getattr(obj, "granted_item_count", None)
        return annotated if annotated is not None else obj.grants.count()

    def get_created_by(self, obj: VaultGroup) -> str | None:
        return obj.created_by.username if obj.created_by else None


class GroupDetailSerializer(GroupSerializer):
    members = serializers.SerializerMethodField()
    granted_items = serializers.SerializerMethodField()

    class Meta(GroupSerializer.Meta):
        fields = GroupSerializer.Meta.fields + ("members", "granted_items")

    def get_members(self, obj: VaultGroup) -> list[dict]:
        memberships = sorted(
            obj.memberships.all(),
            key=lambda membership: membership.user.username,
        )
        return UserBriefSerializer(
            [membership.user for membership in memberships], many=True
        ).data

    def get_granted_items(self, obj: VaultGroup) -> list[dict]:
        items = sorted(
            (grant.item for grant in obj.grants.all()),
            key=lambda item: (item.title, item.pk),
        )
        return [
            {
                "id": item.pk,
                "title": item.title,
                "item_type": item.item_type,
                "item_type_label": item.get_item_type_display(),
                "category": item.category,
                "tags": item.tags,
                "is_archived": item.is_archived,
                "is_deleted": item.is_deleted,
                "created_at": item.created_at,
            }
            for item in items
        ]


class ItemListSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    item_type_label = serializers.SerializerMethodField()
    grant_count = serializers.SerializerMethodField()
    group_grant_count = serializers.SerializerMethodField()
    user_grant_count = serializers.SerializerMethodField()
    can_open_content = serializers.SerializerMethodField()
    has_content = serializers.SerializerMethodField()
    content_updated_at = serializers.SerializerMethodField()
    content_size = serializers.SerializerMethodField()

    class Meta:
        model = VaultItem
        fields = (
            "id",
            "title",
            "item_type",
            "item_type_label",
            "description",
            "category",
            "tags",
            "owner",
            "is_archived",
            "archived_at",
            "is_deleted",
            "deleted_at",
            "grant_count",
            "group_grant_count",
            "user_grant_count",
            "can_open_content",
            "has_content",
            "content_updated_at",
            "content_size",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_item_type_label(self, obj: VaultItem) -> str:
        return obj.get_item_type_display()

    def get_group_grant_count(self, obj: VaultItem) -> int:
        annotated = getattr(obj, "group_grant_count", None)
        return annotated if annotated is not None else obj.group_grants.count()

    def get_user_grant_count(self, obj: VaultItem) -> int:
        annotated = getattr(obj, "user_grant_count", None)
        return annotated if annotated is not None else obj.user_grants.count()

    def get_grant_count(self, obj: VaultItem) -> int:
        return self.get_group_grant_count(obj) + self.get_user_grant_count(obj)

    def get_can_open_content(self, obj: VaultItem) -> bool:
        request = self.context.get("request")
        return can_open_content(request.user if request else None, obj)

    def get_has_content(self, obj: VaultItem) -> bool:
        return _has_content(obj)

    def get_content_updated_at(self, obj: VaultItem):
        content = _content_of(obj)
        return content.updated_at if content is not None else None

    def get_content_size(self, obj: VaultItem) -> int:
        content = _content_of(obj)
        return content.plaintext_size if content is not None else 0


class ItemDetailSerializer(ItemListSerializer):
    can_view_metadata = serializers.SerializerMethodField()
    group_grants = serializers.SerializerMethodField()
    user_grants = serializers.SerializerMethodField()
    effective_users = serializers.SerializerMethodField()
    effective_user_count = serializers.SerializerMethodField()
    content_state = serializers.SerializerMethodField()
    notice = serializers.SerializerMethodField()

    class Meta(ItemListSerializer.Meta):
        fields = ItemListSerializer.Meta.fields + (
            "can_view_metadata",
            "group_grants",
            "user_grants",
            "effective_users",
            "effective_user_count",
            "content_state",
            "notice",
        )

    def get_can_view_metadata(self, obj: VaultItem) -> bool:
        request = self.context.get("request")
        return can_view_metadata(request.user if request else None, obj)

    def get_group_grants(self, obj: VaultItem) -> list[dict]:
        grants = sorted(obj.group_grants.all(), key=lambda grant: grant.group.name)
        return [
            {
                "id": grant.pk,
                "group_id": grant.group_id,
                "group_name": grant.group.name,
                "granted_by": grant.granted_by.username if grant.granted_by else None,
                "created_at": grant.created_at,
            }
            for grant in grants
        ]

    def get_user_grants(self, obj: VaultItem) -> list[dict]:
        grants = sorted(
            obj.user_grants.all(), key=lambda grant: grant.user.username
        )
        return [
            {
                "id": grant.pk,
                "user_id": grant.user_id,
                "username": grant.user.username,
                "display_name": grant.user.display_name,
                "is_active": grant.user.is_active,
                "granted_by": grant.granted_by.username if grant.granted_by else None,
                "created_at": grant.created_at,
            }
            for grant in grants
        ]

    def get_effective_users(self, obj: VaultItem) -> list[dict]:
        return UserBriefSerializer(effective_users_for_item(obj), many=True).data

    def get_effective_user_count(self, obj: VaultItem) -> int:
        return effective_users_for_item(obj).count()

    def get_content_state(self, obj: VaultItem) -> str:
        return "encrypted" if _has_content(obj) else "empty"

    def get_notice(self, obj: VaultItem) -> str:
        return (
            ENCRYPTED_CONTENT_NOTICE
            if _has_content(obj)
            else EMPTY_CONTENT_NOTICE
        )


class MyItemSerializer(serializers.ModelSerializer):
    """Metadata visible to a normal user who was granted access."""

    owner = UserBriefSerializer(read_only=True)
    item_type_label = serializers.SerializerMethodField()
    content_state = serializers.SerializerMethodField()
    notice = serializers.SerializerMethodField()
    has_content = serializers.SerializerMethodField()
    content_updated_at = serializers.SerializerMethodField()
    content_size = serializers.SerializerMethodField()

    class Meta:
        model = VaultItem
        fields = (
            "id",
            "title",
            "item_type",
            "item_type_label",
            "description",
            "category",
            "tags",
            "owner",
            "content_state",
            "notice",
            "has_content",
            "content_updated_at",
            "content_size",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_item_type_label(self, obj: VaultItem) -> str:
        return obj.get_item_type_display()

    def get_content_state(self, obj: VaultItem) -> str:
        return "encrypted" if _has_content(obj) else "empty"

    def get_notice(self, obj: VaultItem) -> str:
        return (
            ENCRYPTED_CONTENT_NOTICE
            if _has_content(obj)
            else EMPTY_CONTENT_NOTICE
        )

    def get_has_content(self, obj: VaultItem) -> bool:
        return _has_content(obj)

    def get_content_updated_at(self, obj: VaultItem):
        content = _content_of(obj)
        return content.updated_at if content is not None else None

    def get_content_size(self, obj: VaultItem) -> int:
        content = _content_of(obj)
        return content.plaintext_size if content is not None else 0


def _validate_group_name(value: str, instance: VaultGroup | None = None) -> str:
    name = (value or "").strip()
    if not name:
        raise serializers.ValidationError("用户组名称不能为空。")
    queryset = VaultGroup.objects.filter(name=name)
    if instance is not None:
        queryset = queryset.exclude(pk=instance.pk)
    if queryset.exists():
        raise serializers.ValidationError("这个用户组名称已经被使用。")
    return name


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=500, default=""
    )

    def validate_name(self, value: str) -> str:
        return _validate_group_name(value)


class GroupUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )

    def validate_name(self, value: str) -> str:
        return _validate_group_name(value, self.instance)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("没有需要修改的内容。")
        return attrs


def _normalize_ids(attrs: dict, field: str, label: str) -> list[int]:
    values: list[int] = list(attrs.get(f"{field}_ids") or [])
    single = attrs.get(f"{field}_id")
    if single is not None:
        values.append(single)
    unique = list(dict.fromkeys(values))
    if not unique:
        raise serializers.ValidationError(f"请至少选择一个{label}。")
    if len(unique) > 100:
        raise serializers.ValidationError(f"一次最多选择 100 个{label}。")
    return unique


class UserIdsSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False
    )
    user_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs: dict) -> dict:
        return {"user_ids": _normalize_ids(attrs, "user", "用户")}


class GroupIdsSerializer(serializers.Serializer):
    group_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False
    )
    group_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs: dict) -> dict:
        return {"group_ids": _normalize_ids(attrs, "group", "用户组")}


class ItemCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    item_type = serializers.ChoiceField(choices=VaultItem.ItemType.choices)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, default=""
    )
    category = serializers.CharField(
        required=False, allow_blank=True, max_length=50, default=""
    )
    tags = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=30),
        required=False,
        default=list,
        max_length=20,
    )

    def validate_title(self, value: str) -> str:
        title = (value or "").strip()
        if not title:
            raise serializers.ValidationError("标题不能为空。")
        return title

    def validate_tags(self, value) -> list[str]:
        return normalize_tags(value)


class ItemUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=1000
    )
    category = serializers.CharField(
        required=False, allow_blank=True, max_length=50
    )
    tags = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=30),
        required=False,
        max_length=20,
    )

    def validate_title(self, value: str) -> str:
        title = (value or "").strip()
        if not title:
            raise serializers.ValidationError("标题不能为空。")
        return title

    def validate_tags(self, value) -> list[str]:
        return normalize_tags(value)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("没有需要修改的内容。")
        return attrs


class OwnerTransferSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField(min_value=1)


class PurgeItemSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )


class TextContentWriteSerializer(serializers.Serializer):
    url = serializers.CharField(
        required=False, allow_blank=True, max_length=1000
    )
    username = serializers.CharField(
        required=False, allow_blank=True, max_length=256
    )
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
        trim_whitespace=False,
    )
    notes = serializers.CharField(
        required=False, allow_blank=True, max_length=5000
    )
    clear_password = serializers.BooleanField(required=False, default=False)


class VaultInitializeSerializer(serializers.Serializer):
    master_password = serializers.CharField(
        write_only=True, min_length=12, max_length=128, trim_whitespace=False
    )
    master_password_confirm = serializers.CharField(
        write_only=True, min_length=12, max_length=128, trim_whitespace=False
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["master_password"] != attrs["master_password_confirm"]:
            raise serializers.ValidationError(
                {"master_password_confirm": "两次输入的主密码不一致。"}
            )
        request = self.context.get("request")
        validate_password_value(
            attrs["master_password"],
            request.user if request else None,
        )
        return attrs


class VaultUnlockSerializer(serializers.Serializer):
    master_password = serializers.CharField(
        write_only=True, max_length=128, trim_whitespace=False
    )
