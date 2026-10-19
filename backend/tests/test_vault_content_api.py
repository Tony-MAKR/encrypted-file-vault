"""Encrypted content, file upload/download and recycle-bin tests."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.vault import content_services
from apps.vault.models import VaultContent, VaultItem
from tests.conftest import csrf_token
from tests.helpers import (
    MASTER_PASSWORD,
    OTHER_MASTER_PASSWORD,
)


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


def _create_item(admin_client, item_type: str = "text", title: str = "条目") -> dict:
    response = admin_client.post(
        "/api/v1/admin/items/",
        {"title": title, "item_type": item_type, "description": "测试说明"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _grant_user(admin_client, item_id: int, user_id: int) -> None:
    response = admin_client.post(
        f"/api/v1/admin/items/{item_id}/grants/users/",
        {"user_id": user_id},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content


def _put_text(admin_client, item_id: int, payload: dict):
    return admin_client.put(
        f"/api/v1/admin/items/{item_id}/content/text/",
        payload,
        content_type="application/json",
    )


def test_vault_status_initialize_unlock_and_lock(
    admin_client, user_client
):
    status = admin_client.get("/api/v1/vault/status/")
    assert status.status_code == 200
    assert status.json() == {"initialized": False, "unlocked": False}

    assert user_client.get("/api/v1/vault/status/").status_code == 200
    forbidden = user_client.post(
        "/api/v1/vault/initialize/",
        {
            "master_password": MASTER_PASSWORD,
            "master_password_confirm": MASTER_PASSWORD,
        },
        content_type="application/json",
    )
    assert forbidden.status_code == 403

    _initialize(admin_client)
    assert admin_client.get("/api/v1/vault/status/").json() == {
        "initialized": True,
        "unlocked": True,
    }

    repeated = admin_client.post(
        "/api/v1/vault/initialize/",
        {
            "master_password": OTHER_MASTER_PASSWORD,
            "master_password_confirm": OTHER_MASTER_PASSWORD,
        },
        content_type="application/json",
    )
    assert repeated.status_code == 409

    locked = admin_client.post(
        "/api/v1/vault/lock/", {}, content_type="application/json"
    )
    assert locked.status_code == 200
    assert locked.json()["unlocked"] is False

    wrong = admin_client.post(
        "/api/v1/vault/unlock/",
        {"master_password": OTHER_MASTER_PASSWORD},
        content_type="application/json",
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_master_password"

    unlocked = admin_client.post(
        "/api/v1/vault/unlock/",
        {"master_password": MASTER_PASSWORD},
        content_type="application/json",
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["unlocked"] is True


def test_vault_initialize_requires_csrf(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    payload = {
        "master_password": MASTER_PASSWORD,
        "master_password_confirm": MASTER_PASSWORD,
    }

    blocked = client.post(
        "/api/v1/vault/initialize/", payload, content_type="application/json"
    )
    assert blocked.status_code == 403

    token = csrf_token(client)
    allowed = client.post(
        "/api/v1/vault/initialize/",
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 201


def test_text_content_roundtrip_and_permissions(
    admin_client,
    user_client,
    other_client,
    normal_user,
    other_user,
    second_admin,
    caplog,
):
    _initialize(admin_client)
    item = _create_item(admin_client, "text", "数据库密码")
    _grant_user(admin_client, item["id"], normal_user.pk)

    payload = {
        "url": "https://db.example.test",
        "username": "dbadmin",
        "password": "Very-Secret-DB-Password-2026!",
        "notes": "仅测试使用",
    }
    with caplog.at_level(logging.INFO, logger="apps.vault"):
        saved = _put_text(admin_client, item["id"], payload)
        assert saved.status_code == 200, saved.content
        data = saved.json()
        assert data["has_content"] is True
        assert data["content_state"] == "encrypted"
        assert data["content_size"] > 0

        viewed = user_client.get(f"/api/v1/items/{item['id']}/content/text/")
        assert viewed.status_code == 200
        viewed_data = viewed.json()
        assert viewed_data["url"] == payload["url"]
        assert viewed_data["username"] == payload["username"]
        assert viewed_data["notes"] == payload["notes"]
        assert viewed_data["has_password"] is True
        assert "password" not in viewed_data

        revealed = user_client.post(
            f"/api/v1/items/{item['id']}/content/text/reveal/",
            {},
            content_type="application/json",
        )
        assert revealed.status_code == 200
        assert revealed.json()["password"] == payload["password"]

        copied = user_client.post(
            f"/api/v1/items/{item['id']}/content/text/copy-audit/",
            {},
            content_type="application/json",
        )
        assert copied.status_code == 204

    content = VaultContent.objects.get(item_id=item["id"])
    assert content.content_type == VaultItem.ItemType.TEXT
    assert payload["password"].encode() not in bytes(content.encrypted_payload)
    assert payload["url"].encode() not in bytes(content.encrypted_payload)
    assert content.blob_path == ""

    assert (
        other_client.get(f"/api/v1/items/{item['id']}/content/text/").status_code
        == 404
    )
    assert (
        other_client.get(f"/api/v1/items/{item['id']}/").status_code == 404
    )

    second_admin_client = Client()
    second_admin_client.force_login(second_admin)
    # Admins see metadata but not content without an explicit grant.
    assert (
        second_admin_client.get(
            f"/api/v1/admin/items/{item['id']}/"
        ).status_code
        == 200
    )
    assert (
        second_admin_client.get(
            f"/api/v1/items/{item['id']}/content/text/"
        ).status_code
        == 404
    )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "text_password_revealed" in messages
    assert "text_password_copied" in messages
    assert payload["password"] not in messages
    assert "Very-Secret-DB-Password" not in messages


def test_text_edit_preserves_and_clears_password(
    admin_client, user_client, normal_user
):
    _initialize(admin_client)
    item = _create_item(admin_client, "text", "编辑密码")
    _grant_user(admin_client, item["id"], normal_user.pk)
    assert _put_text(
        admin_client,
        item["id"],
        {"url": "old.example", "username": "old", "password": "old-secret"},
    ).status_code == 200

    updated = _put_text(
        admin_client, item["id"], {"url": "new.example", "username": "new"}
    )
    assert updated.status_code == 200
    reveal = user_client.post(
        f"/api/v1/items/{item['id']}/content/text/reveal/",
        {},
        content_type="application/json",
    )
    assert reveal.json()["password"] == "old-secret"

    cleared = _put_text(admin_client, item["id"], {"clear_password": True})
    assert cleared.status_code == 200
    no_password = user_client.post(
        f"/api/v1/items/{item['id']}/content/text/reveal/",
        {},
        content_type="application/json",
    )
    assert no_password.status_code == 400


def test_locked_vault_blocks_content(admin_client, user_client, normal_user):
    _initialize(admin_client)
    item = _create_item(admin_client, "text", "锁定测试")
    _grant_user(admin_client, item["id"], normal_user.pk)
    _put_text(admin_client, item["id"], {"username": "u", "password": "p"})

    admin_client.post("/api/v1/vault/lock/", {}, content_type="application/json")

    blocked = user_client.get(f"/api/v1/items/{item['id']}/content/text/")
    assert blocked.status_code == 423
    assert blocked.json()["code"] == "vault_locked"
    assert "p" not in blocked.json().get("password", "")


def test_file_upload_download_and_tamper(
    admin_client, user_client, other_client, normal_user, other_user
):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "机密文件")
    _grant_user(admin_client, item["id"], normal_user.pk)

    payload = b"FILE-SECRET-MARKER-" + (b"0123456789" * 20000)
    upload = SimpleUploadedFile(
        "机密报表.txt", payload, content_type="text/plain"
    )
    response = admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": upload},
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["has_content"] is True
    assert body["content_size"] == len(payload)

    objects = list(Path(settings.VAULT_OBJECTS_DIR).iterdir())
    assert len(objects) == 1
    blob = objects[0]
    assert blob.name.endswith(".vault")
    blob_bytes = blob.read_bytes()
    assert b"FILE-SECRET-MARKER-" not in blob_bytes
    assert b".txt" not in blob_bytes
    assert list(Path(settings.VAULT_TMP_DIR).iterdir()) == []

    download = user_client.get(f"/api/v1/items/{item['id']}/content/file/")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == payload
    assert download["Cache-Control"] == "no-store"
    disposition = unquote(download["Content-Disposition"])
    assert "机密报表.txt" in disposition
    assert download["Content-Length"] == str(len(payload))

    assert (
        other_client.get(
            f"/api/v1/items/{item['id']}/content/file/"
        ).status_code
        == 404
    )

    # Tampering is detected before any plaintext is sent.
    tampered = bytearray(blob_bytes)
    tampered[17] ^= 0x01
    blob.write_bytes(bytes(tampered))
    broken = user_client.get(f"/api/v1/items/{item['id']}/content/file/")
    assert broken.status_code == 409
    assert broken.json()["code"] == "content_integrity_failed"


def test_file_replacement_removes_old_blob(
    admin_client, user_client, normal_user
):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "替换文件")
    _grant_user(admin_client, item["id"], normal_user.pk)

    first = SimpleUploadedFile("first.txt", b"first-content", "text/plain")
    assert admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": first},
    ).status_code == 200
    first_blob = next(Path(settings.VAULT_OBJECTS_DIR).iterdir())

    second = SimpleUploadedFile("second.txt", b"second-content", "text/plain")
    assert admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": second},
    ).status_code == 200

    objects = list(Path(settings.VAULT_OBJECTS_DIR).iterdir())
    assert len(objects) == 1
    assert objects[0].name != first_blob.name
    download = user_client.get(f"/api/v1/items/{item['id']}/content/file/")
    assert b"".join(download.streaming_content) == b"second-content"


def test_file_size_limit_cleans_partial_upload(admin_client, settings):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "大小限制")
    settings.VAULT_MAX_FILE_SIZE_BYTES = 10
    settings.VAULT_MAX_FILE_SIZE_MB = 0

    upload = SimpleUploadedFile("too-big.bin", b"x" * 32)
    response = admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": upload},
    )

    assert response.status_code == 413
    assert VaultContent.objects.filter(item_id=item["id"]).exists() is False
    objects_dir = Path(settings.VAULT_OBJECTS_DIR)
    temp_dir = Path(settings.VAULT_TMP_DIR)
    assert not objects_dir.exists() or list(objects_dir.iterdir()) == []
    assert not temp_dir.exists() or list(temp_dir.iterdir()) == []


def test_filename_path_traversal_is_sanitized(
    admin_client, user_client, normal_user
):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "文件名安全")
    _grant_user(admin_client, item["id"], normal_user.pk)

    upload = SimpleUploadedFile(
        "../../evil.txt", b"safe-content", "text/plain"
    )
    assert admin_client.post(
        f"/api/v1/admin/items/{item['id']}/content/file/",
        {"file": upload},
    ).status_code == 200

    download = user_client.get(f"/api/v1/items/{item['id']}/content/file/")
    disposition = unquote(download["Content-Disposition"])
    assert "evil.txt" in disposition
    assert "../" not in disposition


def test_admin_content_edit_requires_existing_content_access(
    admin_client, second_admin
):
    _initialize(admin_client)
    item = _create_item(admin_client, "text", "管理员边界")
    assert _put_text(
        admin_client, item["id"], {"username": "owner", "password": "secret"}
    ).status_code == 200

    second_client = Client()
    second_client.force_login(second_admin)
    blocked = second_client.put(
        f"/api/v1/admin/items/{item['id']}/content/text/",
        {"username": "intruder"},
        content_type="application/json",
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "content_permission_required"

    # Adding content to an empty item is allowed for any administrator.
    empty = _create_item(admin_client, "text", "空条目")
    allowed = second_client.put(
        f"/api/v1/admin/items/{empty['id']}/content/text/",
        {"username": "created-by-second-admin"},
        content_type="application/json",
    )
    assert allowed.status_code == 200


def test_trash_restore_and_purge_file(
    admin_client, user_client, normal_user, settings
):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "回收站文件")
    _grant_user(admin_client, item["id"], normal_user.pk)
    upload = SimpleUploadedFile("trash.txt", b"trash-content", "text/plain")
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
    assert trashed.json()["is_deleted"] is True
    assert user_client.get("/api/v1/items/").json()["count"] == 0
    assert (
        user_client.get(f"/api/v1/items/{item['id']}/content/file/").status_code
        == 404
    )

    active = admin_client.get("/api/v1/admin/items/")
    assert active.json()["count"] == 0
    trash = admin_client.get("/api/v1/admin/items/?deleted=only")
    assert trash.json()["count"] == 1

    restored = admin_client.post(
        f"/api/v1/admin/items/{item['id']}/restore/",
        {},
        content_type="application/json",
    )
    assert restored.status_code == 200
    assert restored.json()["is_deleted"] is False
    assert user_client.get("/api/v1/items/").json()["count"] == 1

    # Expired trash is purged together with its ciphertext blob.
    vault_item = VaultItem.objects.get(pk=item["id"])
    vault_item.is_deleted = True
    vault_item.deleted_at = timezone.now() - timedelta(days=31)
    vault_item.save(update_fields=["is_deleted", "deleted_at"])
    purged = content_services.purge_expired_items()

    assert purged == 1
    assert VaultItem.objects.filter(pk=item["id"]).exists() is False
    assert VaultContent.objects.filter(item_id=item["id"]).exists() is False
    assert blob.exists() is False


def test_file_download_without_content_returns_404(
    admin_client, user_client, normal_user
):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "没有正文的文件")
    _grant_user(admin_client, item["id"], normal_user.pk)

    response = user_client.get(f"/api/v1/items/{item['id']}/content/file/")

    assert response.status_code == 404
    assert response.json()["code"] == "content_not_found"


def test_file_upload_requires_csrf_and_master_unlock(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    item = VaultItem.objects.create(
        title="CSRF 文件",
        item_type=VaultItem.ItemType.FILE,
        owner=admin_user,
    )

    # Initialize with the normal client (test client bypasses CSRF by default).
    admin_client = Client()
    admin_client.force_login(admin_user)
    _initialize(admin_client)

    upload = SimpleUploadedFile("a.txt", b"a", "text/plain")
    blocked = client.post(
        f"/api/v1/admin/items/{item.pk}/content/file/",
        {"file": upload},
    )
    assert blocked.status_code == 403

    token = csrf_token(client)
    allowed = client.post(
        f"/api/v1/admin/items/{item.pk}/content/file/",
        {"file": SimpleUploadedFile("a.txt", b"a", "text/plain")},
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 200


def test_content_requires_initialized_and_unlocked_vault(admin_client):
    item = _create_item(admin_client, "text", "未初始化")
    response = _put_text(admin_client, item["id"], {"username": "u"})
    assert response.status_code == 409
    assert response.json()["code"] == "vault_not_initialized"


@pytest.mark.django_db
def test_text_content_rejects_file_item(admin_client):
    _initialize(admin_client)
    item = _create_item(admin_client, "file", "类型不匹配")
    response = _put_text(admin_client, item["id"], {"username": "u"})
    assert response.status_code == 400
    assert "不是文字类型" in response.json()["detail"]
