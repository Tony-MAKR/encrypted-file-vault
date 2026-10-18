"""Account and administrator API routes."""

from django.urls import path

from . import views_admin, views_auth

urlpatterns = [
    path("setup/status/", views_auth.setup_status, name="setup-status"),
    path("setup/", views_auth.setup, name="setup"),
    path("auth/csrf/", views_auth.csrf_token_view, name="csrf-token"),
    path("auth/login/", views_auth.login_view, name="login"),
    path("auth/logout/", views_auth.logout_view, name="logout"),
    path("auth/me/", views_auth.me, name="me"),
    path("auth/change-password/", views_auth.change_password, name="change-password"),
    path("admin/users/", views_admin.admin_users, name="admin-users"),
    path(
        "admin/users/<int:user_id>/",
        views_admin.admin_user_detail,
        name="admin-user-detail",
    ),
    path(
        "admin/users/<int:user_id>/role/",
        views_admin.admin_user_role,
        name="admin-user-role",
    ),
    path(
        "admin/users/<int:user_id>/disable/",
        views_admin.admin_user_disable,
        name="admin-user-disable",
    ),
    path(
        "admin/users/<int:user_id>/enable/",
        views_admin.admin_user_enable,
        name="admin-user-enable",
    ),
    path(
        "admin/users/<int:user_id>/reset-password/",
        views_admin.admin_user_reset_password,
        name="admin-user-reset-password",
    ),
    path(
        "admin/users/<int:user_id>/unlock/",
        views_admin.admin_user_unlock,
        name="admin-user-unlock",
    ),
]
