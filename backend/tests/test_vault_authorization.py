"""Core item and authorization behaviour for stage 3."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.vault.models import (
    GroupGrant,
    GroupMembership,
    UserGrant,
    VaultItem,
)
from apps.vault.services import can_open_content, effective_users_for_item


@pytest.mark.django_db
def test_admin_creates_placeholder_item(admin_client, admin_user):
    response = admin_client.post(
        "/api/v1/admin/items/",
        {
            "title": "  网站管理后台  ",
            "item_type": "text",
            "description": "  账号信息占位  ",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "网站管理后台"
    assert data["description"] == "账号信息占位"
    assert data["owner"]["id"] == admin_user.pk
    assert data["content_state"] == "placeholder"
    assert data["can_open_content"] is True
    assert data["grant_count"] == 0
    assert data["effective_user_count"] == 1
    assert "第 4 阶段" in data["notice"]


@pytest.mark.django_db
def test_normal_user_cannot_create_or_list_admin_items(user_client):
    assert user_client.get("/api/v1/admin/items/").status_code == 403
    assert (
        user_client.post(
            "/api/v1/admin/items/",
            {"title": "不允许", "item_type": "text"},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_admin_updates_metadata_but_cannot_change_item_type(
    admin_client, vault_item
):
    response = admin_client.patch(
        f"/api/v1/admin/items/{vault_item.pk}/",
        {
            "title": "新的数据库密码",
            "description": "更新说明",
            "item_type": "file",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新的数据库密码"
    assert data["item_type"] == VaultItem.ItemType.TEXT


@pytest.mark.django_db
def test_group_grant_gives_only_group_members_access(
    admin_client,
    user_client,
    other_client,
    vault_group,
    vault_item,
    normal_user,
    other_user,
    admin_user,
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=admin_user
    )

    grant = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/groups/",
        {"group_ids": [vault_group.pk]},
        content_type="application/json",
    )
    assert grant.status_code == 201
    assert grant.json()["added"] == [vault_group.pk]

    member_list = user_client.get("/api/v1/items/")
    assert member_list.status_code == 200
    assert member_list.json()["count"] == 1
    assert member_list.json()["results"][0]["title"] == "数据库密码"

    member_detail = user_client.get(f"/api/v1/items/{vault_item.pk}/")
    assert member_detail.status_code == 200
    assert member_detail.json()["content_state"] == "placeholder"

    assert other_client.get("/api/v1/items/").json()["count"] == 0
    assert (
        other_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 404
    )


@pytest.mark.django_db
def test_direct_user_grant_does_not_require_group_membership(
    admin_client, other_client, vault_item, other_user
):
    response = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": other_user.pk},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["added"] == [other_user.pk]
    assert other_client.get("/api/v1/items/").json()["count"] == 1
    assert (
        other_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200
    )


@pytest.mark.django_db
def test_effective_access_is_union_without_duplicates(
    admin_client, vault_group, vault_item, normal_user, other_user, admin_user
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=admin_user
    )
    GroupMembership.objects.create(
        group=vault_group, user=other_user, added_by=admin_user
    )
    GroupGrant.objects.create(
        item=vault_item, group=vault_group, granted_by=admin_user
    )
    # Alice is both a member and directly granted: she must appear once.
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=admin_user
    )

    response = admin_client.get(f"/api/v1/admin/items/{vault_item.pk}/")

    assert response.status_code == 200
    data = response.json()
    usernames = [user["username"] for user in data["effective_users"]]
    assert usernames == ["admin", "alice", "bob"]
    assert data["effective_user_count"] == 3
    assert data["group_grant_count"] == 1
    assert data["user_grant_count"] == 1
    assert effective_users_for_item(vault_item).count() == 3


@pytest.mark.django_db
def test_remove_group_grant_keeps_direct_grant(
    admin_client, user_client, other_client, vault_group, vault_item,
    normal_user, other_user, admin_user,
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=admin_user
    )
    GroupMembership.objects.create(
        group=vault_group, user=other_user, added_by=admin_user
    )
    GroupGrant.objects.create(
        item=vault_item, group=vault_group, granted_by=admin_user
    )
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=admin_user
    )

    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200
    assert other_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200

    removed = admin_client.delete(
        f"/api/v1/admin/items/{vault_item.pk}/grants/groups/{vault_group.pk}/"
    )
    assert removed.status_code == 204

    # Alice keeps access through her personal grant; Bob loses group access.
    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200
    assert other_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 404
    assert GroupGrant.objects.filter(item=vault_item).count() == 0


@pytest.mark.django_db
def test_remove_member_keeps_direct_grant(
    admin_client, user_client, vault_group, vault_item, normal_user, admin_user
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=admin_user
    )
    GroupGrant.objects.create(
        item=vault_item, group=vault_group, granted_by=admin_user
    )
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=admin_user
    )

    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200

    removed = admin_client.delete(
        f"/api/v1/admin/groups/{vault_group.pk}/members/{normal_user.pk}/"
    )
    assert removed.status_code == 204

    # The group grant no longer applies, but the personal grant still does.
    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200
    assert can_open_content(normal_user, vault_item) is True


@pytest.mark.django_db
def test_revoke_direct_grant_removes_access(
    admin_client, user_client, vault_item, normal_user
):
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=vault_item.owner
    )
    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200

    response = admin_client.delete(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/{normal_user.pk}/"
    )

    assert response.status_code == 204
    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 404
    assert user_client.get("/api/v1/items/").json()["count"] == 0


@pytest.mark.django_db
def test_duplicate_grants_are_idempotent(
    admin_client, vault_group, vault_item, normal_user
):
    first_group = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/groups/",
        {"group_id": vault_group.pk},
        content_type="application/json",
    )
    second_group = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/groups/",
        {"group_id": vault_group.pk},
        content_type="application/json",
    )
    assert first_group.status_code == 201
    assert second_group.status_code == 200
    assert second_group.json()["added"] == []
    assert GroupGrant.objects.filter(item=vault_item).count() == 1

    first_user = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": normal_user.pk},
        content_type="application/json",
    )
    second_user = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": normal_user.pk},
        content_type="application/json",
    )
    assert first_user.status_code == 201
    assert second_user.status_code == 200
    assert UserGrant.objects.filter(item=vault_item).count() == 1


@pytest.mark.django_db
def test_inactive_user_cannot_receive_grant(
    admin_client, vault_item, normal_user
):
    normal_user.is_active = False
    normal_user.save(update_fields=["is_active"])

    response = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": normal_user.pk},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "inactive_users"
    assert UserGrant.objects.filter(item=vault_item).count() == 0


@pytest.mark.django_db
def test_archive_hides_item_from_normal_users_and_can_be_restored(
    admin_client, user_client, vault_item, normal_user
):
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=vault_item.owner
    )
    assert user_client.get("/api/v1/items/").json()["count"] == 1

    archived = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/archive/",
        {},
        content_type="application/json",
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    assert user_client.get("/api/v1/items/").json()["count"] == 0
    assert user_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 404

    active_list = admin_client.get("/api/v1/admin/items/")
    assert active_list.json()["count"] == 0
    archived_list = admin_client.get("/api/v1/admin/items/?archived=true")
    assert archived_list.json()["count"] == 1

    restored = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/unarchive/",
        {},
        content_type="application/json",
    )
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False
    assert user_client.get("/api/v1/items/").json()["count"] == 1


@pytest.mark.django_db
def test_owner_transfer_requires_an_active_admin(
    admin_client, vault_item, normal_user, second_admin
):
    to_normal_user = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/owner/",
        {"owner_id": normal_user.pk},
        content_type="application/json",
    )
    assert to_normal_user.status_code == 400

    second_admin.is_active = False
    second_admin.save(update_fields=["is_active"])
    to_inactive_admin = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/owner/",
        {"owner_id": second_admin.pk},
        content_type="application/json",
    )
    assert to_inactive_admin.status_code == 400

    second_admin.is_active = True
    second_admin.save(update_fields=["is_active"])
    transferred = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/owner/",
        {"owner_id": second_admin.pk},
        content_type="application/json",
    )
    assert transferred.status_code == 200
    assert transferred.json()["owner"]["id"] == second_admin.pk

    vault_item.refresh_from_db()
    assert vault_item.owner_id == second_admin.pk


@pytest.mark.django_db
def test_transfer_moves_owner_access_and_keeps_metadata_visible(
    admin_client, vault_item, admin_user, second_admin
):
    transferred = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/owner/",
        {"owner_id": second_admin.pk},
        content_type="application/json",
    )
    assert transferred.status_code == 200
    assert transferred.json()["can_open_content"] is False

    # The previous owner is still an administrator and sees metadata, but no
    # longer gets automatic content access after the transfer.
    metadata = admin_client.get(f"/api/v1/admin/items/{vault_item.pk}/")
    assert metadata.status_code == 200
    assert metadata.json()["can_view_metadata"] is True
    assert metadata.json()["can_open_content"] is False
    assert admin_client.get("/api/v1/items/").json()["count"] == 0

    new_owner_client = Client()
    new_owner_client.force_login(second_admin)
    assert (
        new_owner_client.get(f"/api/v1/items/{vault_item.pk}/").status_code
        == 200
    )


@pytest.mark.django_db
def test_admin_can_see_all_metadata_without_content_access(
    vault_item, second_admin
):
    client = Client()
    client.force_login(second_admin)

    listing = client.get("/api/v1/admin/items/")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["results"][0]["can_open_content"] is False

    detail = client.get(f"/api/v1/admin/items/{vault_item.pk}/")
    assert detail.status_code == 200
    assert detail.json()["can_view_metadata"] is True
    assert detail.json()["can_open_content"] is False

    # The normal-user list does not fall back to "admin sees everything".
    assert client.get("/api/v1/items/").json()["count"] == 0


@pytest.mark.django_db
def test_unauthorized_and_unauthenticated_requests(
    other_client, vault_item
):
    assert other_client.get("/api/v1/items/").json()["count"] == 0
    assert other_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 404

    anonymous = Client()
    assert anonymous.get("/api/v1/items/").status_code == 401
    assert anonymous.get(f"/api/v1/items/{vault_item.pk}/").status_code == 401


@pytest.mark.django_db
def test_disabled_user_cannot_access_granted_item(
    admin_client, vault_item, normal_user
):
    UserGrant.objects.create(
        item=vault_item, user=normal_user, granted_by=vault_item.owner
    )
    target_client = Client()
    target_client.force_login(normal_user)
    assert target_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 200

    disabled = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/disable/",
        {},
        content_type="application/json",
    )
    assert disabled.status_code == 200
    assert target_client.get(f"/api/v1/items/{vault_item.pk}/").status_code == 401

    normal_user.refresh_from_db()
    assert can_open_content(normal_user, vault_item) is False

    detail = admin_client.get(f"/api/v1/admin/items/{vault_item.pk}/")
    assert detail.json()["effective_user_count"] == 1
