"""Audit, backup and system-status routes."""

from django.urls import path

from . import views

urlpatterns = [
    path("admin/audit/", views.admin_audit, name="admin-audit"),
    path(
        "admin/audit/options/",
        views.admin_audit_options,
        name="admin-audit-options",
    ),
    path("admin/backups/", views.admin_backups, name="admin-backups"),
    path(
        "admin/backups/<int:backup_id>/verify/",
        views.admin_backup_verify,
        name="admin-backup-verify",
    ),
    path(
        "admin/system/status/",
        views.admin_system_status,
        name="admin-system-status",
    ),
]
