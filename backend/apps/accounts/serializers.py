"""Validation and representation for account APIs."""

from __future__ import annotations

import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User

USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,32}$")


def normalize_username(value: str) -> str:
    return (value or "").strip().lower()


def validate_username_value(value: str) -> str:
    username = normalize_username(value)
    if not USERNAME_RE.fullmatch(username):
        raise serializers.ValidationError(
            "用户名只能包含小写字母、数字、下划线和连字符，长度 3–32 位。"
        )
    return username


def validate_display_name_value(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise serializers.ValidationError("显示名不能为空。")
    if len(name) > 50:
        raise serializers.ValidationError("显示名不能超过 50 个字符。")
    return name


def validate_password_value(password: str | None, user: User | None = None) -> str:
    if not password:
        raise serializers.ValidationError("密码不能为空。")
    if len(password) > 128:
        raise serializers.ValidationError("密码不能超过 128 个字符。")
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return password


class UserSerializer(serializers.ModelSerializer):
    is_locked = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "display_name",
            "role",
            "is_active",
            "must_change_password",
            "is_locked",
            "last_login",
            "date_joined",
            "created_at",
            "updated_at",
            "created_by",
        )
        read_only_fields = fields

    def get_is_locked(self, obj: User) -> bool:
        return obj.is_locked()

    def get_created_by(self, obj: User) -> str | None:
        return obj.created_by.username if obj.created_by else None


class SetupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    display_name = serializers.CharField(max_length=50)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    password_confirm = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate_username(self, value: str) -> str:
        username = validate_username_value(value)
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError("这个用户名已经被使用。")
        return username

    def validate_display_name(self, value: str) -> str:
        return validate_display_name_value(value)

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "两次输入的密码不一致。"}
            )
        candidate = User(
            username=attrs["username"], display_name=attrs["display_name"]
        )
        validate_password_value(attrs["password"], candidate)
        return attrs


class UserCreateSerializer(SetupSerializer):
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.USER)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_username(self, value: str) -> str:
        return normalize_username(value)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    new_password_confirm = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "当前密码不正确。"}
            )
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "两次输入的新密码不一致。"}
            )
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": "新密码不能与当前密码相同。"}
            )
        validate_password_value(attrs["new_password"], user)
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    new_password_confirm = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate(self, attrs: dict) -> dict:
        target = self.context["target_user"]
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "两次输入的新密码不一致。"}
            )
        validate_password_value(attrs["new_password"], target)
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("display_name",)

    def validate_display_name(self, value: str) -> str:
        return validate_display_name_value(value)


class RoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=User.Role.choices)
