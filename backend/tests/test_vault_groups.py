"""User-group management tests for stage 3."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.vault.models import GroupGrant, GroupMembership, VaultGroup
from tests.conftest import csrf_token


@pytest.mark.django_db
def test_admin_creates_group_and_normal_user_is_forbidden(
    admin_client, user_client, admin_user
):
    response = admin_client.post(
        "/api/v1/admin/groups/",
        {"name": "  运维组  ", "description": "  负责服务器  "},
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "运维组"
    assert data["description"] == "负责服务器"
    assert data["created_by"] == admin_user.username
    assert data["member_count"] == 0
    assert data["granted_item_count"] == 0

    forbidden_create = user_client.post(
        "/api/v1/admin/groups/",
        {"name": "普通用户组"},
        content_type="application/json",
    )
    assert forbidden_create.status_code == 403
    assert user_client.get("/api/v1/admin/groups/").status_code == 403


@pytest.mark.django_db
def test_group_name_must_be_unique(admin_client, vault_group):
    response = admin_client.post(
        "/api/v1/admin/groups/",
        {"name": "财务组"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "name" in response.json()
    assert VaultGroup.objects.filter(name="财务组").count() == 1


@pytest.mark.django_db
def test_admin_can_update_group(admin_client, vault_group):
    response = admin_client.patch(
        f"/api/v1/admin/groups/{vault_group.pk}/",
        {"name": "财务与采购组", "description": "新的说明"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["name"] == "财务与采购组"
    assert response.json()["description"] == "新的说明"

    vault_group.refresh_from_db()
    assert vault_group.name == "财务与采购组"


@pytest.mark.django_db
def test_group_update_rejects_duplicate_name(admin_client, vault_group):
    VaultGroup.objects.create(name="运维组", created_by=vault_group.created_by)

    response = admin_client.patch(
        f"/api/v1/admin/groups/{vault_group.pk}/",
        {"name": "运维组"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "name" in response.json()


@pytest.mark.django_db
def test_admin_adds_and_removes_group_members(
    admin_client, vault_group, normal_user, other_user
):
    added = admin_client.post(
        f"/api/v1/admin/groups/{vault_group.pk}/members/",
        {"user_ids": [normal_user.pk, other_user.pk, normal_user.pk]},
        content_type="application/json",
    )

    assert added.status_code == 200
    payload = added.json()
    assert len(payload["added"]) == 2
    assert payload["already_members"] == []
    assert payload["member_count"] == 2
    assert GroupMembership.objects.filter(group=vault_group).count() == 2

    repeated = admin_client.post(
        f"/api/v1/admin/groups/{vault_group.pk}/members/",
        {"user_ids": [normal_user.pk]},
        content_type="application/json",
    )
    assert repeated.status_code == 200
    assert repeated.json()["added"] == []
    assert repeated.json()["already_members"] == [normal_user.pk]
    assert GroupMembership.objects.filter(group=vault_group).count() == 2

    removed = admin_client.delete(
        f"/api/v1/admin/groups/{vault_group.pk}/members/{normal_user.pk}/"
    )
    assert removed.status_code == 204
    assert GroupMembership.objects.filter(
        group=vault_group, user=normal_user
    ).exists() is False


@pytest.mark.django_db
def test_inactive_user_cannot_be_added_to_group(
    admin_client, vault_group, normal_user
):
    normal_user.is_active = False
    normal_user.save(update_fields=["is_active"])

    response = admin_client.post(
        f"/api/v1/admin/groups/{vault_group.pk}/members/",
        {"user_ids": [normal_user.pk]},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "inactive_users"
    assert GroupMembership.objects.filter(group=vault_group).count() == 0


@pytest.mark.django_db
def test_unknown_user_cannot_be_added_to_group(admin_client, vault_group):
    response = admin_client.post(
        f"/api/v1/admin/groups/{vault_group.pk}/members/",
        {"user_ids": [999999]},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "unknown_users"


@pytest.mark.django_db
def test_delete_group_without_grants_removes_memberships(
    admin_client, vault_group, normal_user
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=vault_group.created_by
    )

    response = admin_client.delete(f"/api/v1/admin/groups/{vault_group.pk}/")

    assert response.status_code == 204
    assert VaultGroup.objects.filter(pk=vault_group.pk).exists() is False
    assert GroupMembership.objects.filter(group_id=vault_group.pk).count() == 0


@pytest.mark.django_db
def test_delete_group_with_grants_is_refused(
    admin_client, vault_group, vault_item, admin_user
):
    GroupGrant.objects.create(
        item=vault_item, group=vault_group, granted_by=admin_user
    )

    response = admin_client.delete(f"/api/v1/admin/groups/{vault_group.pk}/")

    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "group_has_grants"
    assert data["affected_item_count"] == 1
    assert VaultGroup.objects.filter(pk=vault_group.pk).exists() is True


@pytest.mark.django_db
def test_group_detail_lists_members_and_granted_items(
    admin_client, vault_group, normal_user, vault_item, admin_user
):
    GroupMembership.objects.create(
        group=vault_group, user=normal_user, added_by=admin_user
    )
    GroupGrant.objects.create(
        item=vault_item, group=vault_group, granted_by=admin_user
    )

    response = admin_client.get(f"/api/v1/admin/groups/{vault_group.pk}/")

    assert response.status_code == 200
    data = response.json()
    assert [member["username"] for member in data["members"]] == ["alice"]
    assert [item["title"] for item in data["granted_items"]] == ["数据库密码"]
    assert data["member_count"] == 1
    assert data["granted_item_count"] == 1


@pytest.mark.django_db
def test_group_list_supports_search_and_pagination(admin_client, admin_user):
    for index in range(3):
        VaultGroup.objects.create(
            name=f"测试组{index}",
            description=f"第 {index} 组",
            created_by=admin_user,
        )
    VaultGroup.objects.create(name="其他组", created_by=admin_user)

    response = admin_client.get("/api/v1/admin/groups/?page_size=2&q=测试组")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["results"]) == 2


@pytest.mark.django_db
def test_group_creation_requires_csrf(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)

    blocked = client.post(
        "/api/v1/admin/groups/",
        {"name": "无令牌组"},
        content_type="application/json",
    )
    assert blocked.status_code == 403

    token = csrf_token(client)
    allowed = client.post(
        "/api/v1/admin/groups/",
        {"name": "有令牌组"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 201
    assert VaultGroup.objects.filter(name="有令牌组").exists() is True
