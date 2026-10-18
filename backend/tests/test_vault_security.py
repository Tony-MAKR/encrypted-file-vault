"""Security boundaries and audit logging for stage 3."""

from __future__ import annotations

import logging

import pytest
from django.test import Client

from apps.vault.models import VaultItem
from tests.conftest import csrf_token


@pytest.mark.django_db
def test_normal_user_cannot_reach_any_admin_vault_endpoint(
    user_client, vault_group, vault_item, normal_user
):
    assert user_client.get("/api/v1/admin/groups/").status_code == 403
    assert (
        user_client.get(f"/api/v1/admin/groups/{vault_group.pk}/").status_code
        == 403
    )
    assert (
        user_client.post(
            f"/api/v1/admin/groups/{vault_group.pk}/members/",
            {"user_ids": [normal_user.pk]},
            content_type="application/json",
        ).status_code
        == 403
    )
    assert user_client.get("/api/v1/admin/items/").status_code == 403
    assert (
        user_client.get(f"/api/v1/admin/items/{vault_item.pk}/").status_code
        == 403
    )
    assert (
        user_client.post(
            f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
            {"user_id": normal_user.pk},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_item_and_grant_changes_require_csrf(admin_user, vault_item, normal_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)

    blocked_item = client.post(
        "/api/v1/admin/items/",
        {"title": "无令牌条目", "item_type": "text"},
        content_type="application/json",
    )
    assert blocked_item.status_code == 403

    blocked_grant = client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": normal_user.pk},
        content_type="application/json",
    )
    assert blocked_grant.status_code == 403

    token = csrf_token(client)
    allowed_item = client.post(
        "/api/v1/admin/items/",
        {"title": "有令牌条目", "item_type": "text"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed_item.status_code == 201

    allowed_grant = client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": normal_user.pk},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed_grant.status_code == 201


@pytest.mark.django_db
def test_group_member_item_and_grant_events_are_logged(
    admin_client,
    vault_group,
    vault_item,
    normal_user,
    second_admin,
    caplog,
):
    with caplog.at_level(logging.INFO, logger="apps.vault"):
        admin_client.post(
            "/api/v1/admin/groups/",
            {"name": "审计组", "description": "用于日志测试"},
            content_type="application/json",
        )
        admin_client.post(
            f"/api/v1/admin/groups/{vault_group.pk}/members/",
            {"user_ids": [normal_user.pk]},
            content_type="application/json",
        )
        admin_client.post(
            f"/api/v1/admin/items/{vault_item.pk}/grants/groups/",
            {"group_id": vault_group.pk},
            content_type="application/json",
        )
        admin_client.delete(
            f"/api/v1/admin/items/{vault_item.pk}/grants/groups/{vault_group.pk}/"
        )
        admin_client.post(
            f"/api/v1/admin/items/{vault_item.pk}/archive/",
            {},
            content_type="application/json",
        )
        admin_client.post(
            f"/api/v1/admin/items/{vault_item.pk}/unarchive/",
            {},
            content_type="application/json",
        )
        admin_client.post(
            f"/api/v1/admin/items/{vault_item.pk}/owner/",
            {"owner_id": second_admin.pk},
            content_type="application/json",
        )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    for event in (
        "group_created",
        "group_member_added",
        "group_grant_added",
        "group_grant_removed",
        "item_archived",
        "item_unarchived",
        "item_owner_transferred",
    ):
        assert event in messages

    # Item titles/descriptions are metadata, but they should not be needed in
    # logs; passwords and secrets must never appear.
    assert "数据库密码" not in messages
    assert "password" not in messages.lower()
    assert "secret" not in messages.lower()


@pytest.mark.django_db
def test_item_search_and_pagination(admin_client, admin_user):
    for index in range(3):
        VaultItem.objects.create(
            title=f"服务器密码 {index}",
            item_type=VaultItem.ItemType.TEXT,
            owner=admin_user,
        )
    VaultItem.objects.create(
        title="其他资料", item_type=VaultItem.ItemType.FILE, owner=admin_user
    )

    response = admin_client.get(
        "/api/v1/admin/items/?page_size=2&q=服务器&item_type=text"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["results"]) == 2
    assert all("服务器密码" in item["title"] for item in data["results"])


@pytest.mark.django_db
def test_grant_lists_are_limited_to_enabled_accounts(admin_client, vault_item):
    inactive = admin_client.post(
        "/api/v1/admin/users/",
        {
            "username": "inactive1",
            "display_name": "停用用户",
            "password": "Stage3-Password-2026!",
            "password_confirm": "Stage3-Password-2026!",
            "role": "user",
        },
        content_type="application/json",
    )
    assert inactive.status_code == 201
    inactive_id = inactive.json()["id"]
    admin_client.post(
        f"/api/v1/admin/users/{inactive_id}/disable/",
        {},
        content_type="application/json",
    )

    response = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_id": inactive_id},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "inactive_users"
