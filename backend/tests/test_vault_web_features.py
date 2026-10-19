"""Stage 5: category/tags, filters/options and permanent deletion."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.vault.models import VaultContent, VaultItem
from tests.conftest import csrf_token
from tests.helpers import MASTER_PASSWORD, TEST_PASSWORD


def _initialize(admin_client) -> None:
    response = admin_client.post(
        "/api/v1/vault/initialize/",
        {
            "master_password": MASTER_PASSWORD,
            "master_password_confirm": MASTER_PASSWORD,
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content


def _create_item(admin_client, **overrides) -> dict:
    payload = {
        "title": "测试条目",
        "item_type": "text",
        "description": "",
        **overrides,
    }
    response = admin_client.post(
        "/api/v1/admin/items/", payload, content_type="application/json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def _grant(admin_client, item_id: int, user_id: int) -> None:
    response = admin_client.post(
        f"/api/v1/admin/items/{item_id}/grants/users/",
        {"user_id": user_id},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content


def test_category_and_tags_roundtrip(admin_client):
    item = _create_item(
        admin_client,
        title="带分类的条目",
        category="  财务  ",
        tags=["重要", " 生产 ", "重要", ""],
    )

    assert item["category"] == "财务"
    assert item["tags"] == ["重要", "生产"]

    detail = admin_client.get(f"/api/v1/admin/items/{item['id']}/")
    assert detail.status_code == 200
    assert detail.json()["category"] == "财务"
    assert detail.json()["tags"] == ["重要", "生产"]

    updated = admin_client.patch(
        f"/api/v1/admin/items/{item['id']}/",
        {"category": "运维", "tags": ["服务器", "财务"]},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["category"] == "运维"
    assert updated.json()["tags"] == ["服务器", "财务"]


def test_tag_validation_limits(admin_client):
    too_long_response = admin_client.post(
        "/api/v1/admin/items/",
        {"title": "标签过长", "item_type": "text", "tags": ["x" * 31]},
        content_type="application/json",
    )
    assert too_long_response.status_code == 400

    too_many = admin_client.post(
        "/api/v1/admin/items/",
        {
            "title": "标签太多",
            "item_type": "text",
            "tags": [f"tag{index}" for index in range(21)],
        },
        content_type="application/json",
    )
    assert too_many.status_code == 400


def test_search_and_filters(admin_client, user_client, normal_user):
    financial = _create_item(
        admin_client,
        title="生产数据库",
        category="财务",
        tags=["服务器", "生产"],
    )
    ops = _create_item(
        admin_client,
        title="测试数据库",
        category="运维",
        tags=["测试"],
    )
    _grant(admin_client, financial["id"], normal_user.pk)
    _grant(admin_client, ops["id"], normal_user.pk)

    by_text = admin_client.get("/api/v1/admin/items/?q=服务器")
    assert by_text.status_code == 200
    assert by_text.json()["count"] == 1
    assert by_text.json()["results"][0]["id"] == financial["id"]

    by_category = admin_client.get("/api/v1/admin/items/?category=财务")
    assert by_category.json()["count"] == 1
    assert by_category.json()["results"][0]["id"] == financial["id"]

    by_tag = admin_client.get("/api/v1/admin/items/?tag=生产")
    assert by_tag.json()["count"] == 1
    assert by_tag.json()["results"][0]["id"] == financial["id"]

    combined = admin_client.get(
        "/api/v1/admin/items/?category=财务&tag=服务器&q=数据库"
    )
    assert combined.json()["count"] == 1
    assert combined.json()["results"][0]["id"] == financial["id"]

    user_filtered = user_client.get("/api/v1/items/?tag=服务器")
    assert user_filtered.status_code == 200
    assert user_filtered.json()["count"] == 1
    assert user_filtered.json()["results"][0]["id"] == financial["id"]

    options = admin_client.get("/api/v1/admin/item-options/")
    assert options.status_code == 200
    assert options.json()["categories"] == ["财务", "运维"]
    assert set(options.json()["tags"]) == {"服务器", "生产", "测试"}

    user_options = user_client.get("/api/v1/items/options/")
    assert user_options.status_code == 200
    assert set(user_options.json()["categories"]) == {"财务", "运维"}


def test_tag_options_only_include_visible_items(
    admin_client, user_client, normal_user, other_client
):
    visible = _create_item(
        admin_client, title="可见", category="可见分类", tags=["可见标签"]
    )
    _create_item(
        admin_client, title="不可见", category="不可见分类", tags=["不可见标签"]
    )
    _grant(admin_client, visible["id"], normal_user.pk)

    visible_options = user_client.get("/api/v1/items/options/").json()
    assert visible_options["categories"] == ["可见分类"]
    assert visible_options["tags"] == ["可见标签"]

    other_options = other_client.get("/api/v1/items/options/").json()
    assert other_options == {"categories": [], "tags": []}


def test_permanent_delete_requires_password_and_removes_blob(
    admin_client, caplog
):
    _initialize(admin_client)
    item = _create_item(admin_client, title="永久删除文件", item_type="file")
    upload = SimpleUploadedFile("purge.txt", b"purge-content", "text/plain")
    assert admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": upload},
    ).status_code == 200
    blob = next(Path(settings.VAULT_OBJECTS_DIR).iterdir())

    trashed = admin_client.post(
        f"/api/v1/admin/items/{item['id']}/trash/",
        {},
        content_type="application/json",
    )
    assert trashed.status_code == 200

    with caplog.at_level(logging.INFO, logger="apps.vault"):
        wrong = admin_client.post(
            f"/api/v1/admin/items/{item['id']}/purge/",
            {"current_password": "Wrong-Login-Password-2026!"},
            content_type="application/json",
        )
        assert wrong.status_code == 400
        assert wrong.json()["code"] == "invalid_password"
        assert VaultItem.objects.filter(pk=item["id"]).exists() is True
        assert blob.exists() is True

        correct = admin_client.post(
            f"/api/v1/admin/items/{item['id']}/purge/",
            {"current_password": TEST_PASSWORD},
            content_type="application/json",
        )
        assert correct.status_code == 204

    assert VaultItem.objects.filter(pk=item["id"]).exists() is False
    assert VaultContent.objects.filter(item_id=item["id"]).exists() is False
    assert blob.exists() is False

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "item_permanently_deleted" in messages
    assert "Wrong-Login-Password" not in messages
    assert TEST_PASSWORD not in messages


def test_purge_rejects_active_item_and_normal_user(
    admin_client, user_client, normal_user
):
    item = _create_item(admin_client, title="活跃条目")

    active = admin_client.post(
        f"/api/v1/admin/items/{item['id']}/purge/",
        {"current_password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert active.status_code == 400
    assert active.json()["code"] == "item_not_deleted"

    assert user_client.post(
        f"/api/v1/admin/items/{item['id']}/purge/",
        {"current_password": TEST_PASSWORD},
        content_type="application/json",
    ).status_code == 403


def test_purge_requires_csrf(admin_client, admin_user):
    item = _create_item(admin_client, title="CSRF 永久删除")
    admin_client.post(
        f"/api/v1/admin/items/{item['id']}/trash/",
        {},
        content_type="application/json",
    )

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(admin_user)
    blocked = csrf_client.post(
        f"/api/v1/admin/items/{item['id']}/purge/",
        {"current_password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert blocked.status_code == 403

    token = csrf_token(csrf_client)
    allowed = csrf_client.post(
        f"/api/v1/admin/items/{item['id']}/purge/",
        {"current_password": TEST_PASSWORD},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 204


def test_admin_dashboard_counts_and_recent_items(
    admin_client, user_client, normal_user
):
    _initialize(admin_client)
    active = _create_item(
        admin_client, title="活跃内容", category="分类", tags=["标签"]
    )
    _put_text(admin_client, active["id"], {"username": "u", "password": "p"})
    trashed = _create_item(admin_client, title="回收站内容")
    admin_client.post(
        f"/api/v1/admin/items/{trashed['id']}/trash/",
        {},
        content_type="application/json",
    )
    _grant(admin_client, active["id"], normal_user.pk)

    response = admin_client.get("/api/v1/admin/dashboard/")

    assert response.status_code == 200
    data = response.json()
    assert data["users"] >= 2
    assert data["groups"] == 0
    assert data["active_items"] == 1
    assert data["encrypted_items"] == 1
    assert data["trash_items"] == 1
    assert data["recent_items"][0]["id"] == active["id"]
    assert user_client.get("/api/v1/admin/dashboard/").status_code == 403

    mine = user_client.get("/api/v1/items/dashboard/")
    assert mine.status_code == 200
    assert mine.json()["visible_items"] == 1
    assert mine.json()["recent_items"][0]["id"] == active["id"]


def _put_text(admin_client, item_id: int, payload: dict):
    return admin_client.put(
        f"/api/v1/admin/items/{item_id}/content/text/",
        payload,
        content_type="application/json",
    )


def test_migrated_style_item_defaults_to_empty_category_and_tags(
    admin_client, admin_user
):
    # This mirrors an existing item created before stage 5, where the columns
    # were added with defaults.
    item = VaultItem.objects.create(
        title="旧条目",
        item_type=VaultItem.ItemType.TEXT,
        owner=admin_user,
    )

    detail = admin_client.get(f"/api/v1/admin/items/{item.pk}/")
    assert detail.status_code == 200
    assert detail.json()["category"] == ""
    assert detail.json()["tags"] == []
