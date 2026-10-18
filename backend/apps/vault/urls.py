"""Group, item and authorization API routes."""

from django.urls import path

from . import views_admin, views_items

urlpatterns = [
    path("admin/groups/", views_admin.admin_groups, name="admin-groups"),
    path(
        "admin/groups/<int:group_id>/",
        views_admin.admin_group_detail,
        name="admin-group-detail",
    ),
    path(
        "admin/groups/<int:group_id>/members/",
        views_admin.admin_group_members,
        name="admin-group-members",
    ),
    path(
        "admin/groups/<int:group_id>/members/<int:user_id>/",
        views_admin.admin_group_member_detail,
        name="admin-group-member-detail",
    ),
    path("admin/items/", views_admin.admin_items, name="admin-items"),
    path(
        "admin/items/<int:item_id>/",
        views_admin.admin_item_detail,
        name="admin-item-detail",
    ),
    path(
        "admin/items/<int:item_id>/archive/",
        views_admin.admin_item_archive,
        name="admin-item-archive",
    ),
    path(
        "admin/items/<int:item_id>/unarchive/",
        views_admin.admin_item_unarchive,
        name="admin-item-unarchive",
    ),
    path(
        "admin/items/<int:item_id>/owner/",
        views_admin.admin_item_owner,
        name="admin-item-owner",
    ),
    path(
        "admin/items/<int:item_id>/grants/groups/",
        views_admin.admin_item_group_grants,
        name="admin-item-group-grants",
    ),
    path(
        "admin/items/<int:item_id>/grants/groups/<int:group_id>/",
        views_admin.admin_item_group_grant_detail,
        name="admin-item-group-grant-detail",
    ),
    path(
        "admin/items/<int:item_id>/grants/users/",
        views_admin.admin_item_user_grants,
        name="admin-item-user-grants",
    ),
    path(
        "admin/items/<int:item_id>/grants/users/<int:user_id>/",
        views_admin.admin_item_user_grant_detail,
        name="admin-item-user-grant-detail",
    ),
    path("items/", views_items.my_items, name="my-items"),
    path("items/<int:item_id>/", views_items.my_item_detail, name="my-item-detail"),
]
