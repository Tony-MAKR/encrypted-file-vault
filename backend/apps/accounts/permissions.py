"""Access control for administrator-only endpoints."""

from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    message = "需要管理员权限。"

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role == User.Role.ADMIN
        )
