"""Stage 7: append-only audit records, query API and retention cleanup."""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditEvent
from tests.helpers import MASTER_PASSWORD, TEST_PASSWORD


def _audit(action: str) -> AuditEvent:
    return AuditEvent.objects.filter(action=action).order_by("-id").first()


@pytest.mark.django_db
def test_login_success_and_logout_are_audited(client, normal_user):
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 200

    event = _audit("login_succeeded")
    assert event is not None
    assert event.actor_username == "alice"
    assert event.actor_role == "user"
    assert event.result == AuditEvent.Result.SUCCESS
    assert event.ip_address == "127.0.0.1"
    assert event.request_id

    logout = client.post("/api/v1/auth/logout/")
    assert logout.status_code == 204
    event = _audit("logout")
    assert event is not None
    assert event.actor_username == "alice"


@pytest.mark.django_db
def test_failed_login_is_audited_without_the_password(client, normal_user):
    secret = "Never-Log-This-Password-123!"
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": secret},
        content_type="application/json",
    )
    assert response.status_code == 400

    event = _audit("login_failed")
    assert event is not None
    assert event.result == AuditEvent.Result.FAILURE
    assert event.actor_username == "alice"
    assert event.detail == {"reason": "bad_credentials"}
    assert secret not in json.dumps(event.detail, ensure_ascii=False)


@pytest.mark.django_db
def test_admin_user_actions_are_audited(admin_client, admin_user):
    response = admin_client.post(
        "/api/v1/admin/users/",
        {
            "username": "audited-user",
            "display_name": "被审计用户",
            "password": "Audited-User-Password-2026!",
            "password_confirm": "Audited-User-Password-2026!",
            "role": "user",
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content

    event = _audit("user_created")
    assert event is not None
    assert event.actor_username == admin_user.username
    assert event.target_type == "user"
    assert event.target_label == "audited-user"
    assert event.detail == {"role": "user"}


@pytest.mark.django_db
def test_content_view_and_download_are_audited(
    admin_client, user_client, normal_user, vault_item, settings
):
    settings.VAULT_KDF_TIME_COST = 1
    settings.VAULT_KDF_MEMORY_COST = 8192
    settings.VAULT_KDF_PARALLELISM = 1

    response = admin_client.post(
        "/api/v1/vault/initialize/",
        {
            "master_password": MASTER_PASSWORD,
            "master_password_confirm": MASTER_PASSWORD,
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content

    save = admin_client.put(
        f"/api/v1/admin/items/{vault_item.pk}/content/text/",
        {
            "url": "https://example.test",
            "username": "dbuser",
            "password": "Super-Secret-Value-2026!",
            "notes": "仅测试",
        },
        content_type="application/json",
    )
    assert save.status_code == 200, save.content

    grant = admin_client.post(
        f"/api/v1/admin/items/{vault_item.pk}/grants/users/",
        {"user_ids": [normal_user.pk]},
        content_type="application/json",
    )
    assert grant.status_code == 201, grant.content

    view = user_client.get(f"/api/v1/items/{vault_item.pk}/content/text/")
    assert view.status_code == 200
    reveal = user_client.post(
        f"/api/v1/items/{vault_item.pk}/content/text/reveal/"
    )
    assert reveal.status_code == 200

    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"text_saved", "grant_user_added", "text_viewed", "text_revealed"} <= actions

    for event in AuditEvent.objects.all():
        serialized = json.dumps(
            {
                "detail": event.detail,
                "target_label": event.target_label,
                "actor_username": event.actor_username,
            },
            ensure_ascii=False,
        )
        assert "Super-Secret-Value-2026!" not in serialized
        assert "dbuser" not in serialized


@pytest.mark.django_db
def test_audit_api_is_admin_only_and_records_the_query(admin_client, user_client):
    AuditEvent.objects.create(
        actor_username="alice",
        action="login_succeeded",
        result=AuditEvent.Result.SUCCESS,
    )

    denied = user_client.get("/api/v1/admin/audit/")
    assert denied.status_code == 404

    response = admin_client.get("/api/v1/admin/audit/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert data["results"][0]["action_label"] == "登录成功"
    assert _audit("audit_viewed") is not None


@pytest.mark.django_db
def test_audit_filters(admin_client):
    AuditEvent.objects.create(
        actor_username="alice", action="login_succeeded", result="success"
    )
    AuditEvent.objects.create(
        actor_username="bob", action="login_failed", result="failure"
    )
    AuditEvent.objects.create(
        actor_username="bob", action="item_created", result="success"
    )

    by_actor = admin_client.get("/api/v1/admin/audit/?q=bob").json()
    assert {row["actor_username"] for row in by_actor["results"]} == {"bob"}

    by_result = admin_client.get(
        "/api/v1/admin/audit/?result=failure"
    ).json()
    assert by_result["count"] == 1
    assert by_result["results"][0]["action"] == "login_failed"

    by_category = admin_client.get(
        "/api/v1/admin/audit/?category=auth"
    ).json()
    assert {row["action"] for row in by_category["results"]} == {
        "login_succeeded",
        "login_failed",
    }

    by_action = admin_client.get(
        "/api/v1/admin/audit/?action=item_created"
    ).json()
    assert by_action["count"] == 1
    assert by_action["results"][0]["actor_username"] == "bob"

    options = admin_client.get("/api/v1/admin/audit/options/")
    assert options.status_code == 200
    assert any(item["value"] == "auth" for item in options.json()["categories"])


@pytest.mark.django_db
def test_audit_date_filters(admin_client):
    recent = AuditEvent.objects.create(
        actor_username="alice", action="login_succeeded"
    )
    old = AuditEvent.objects.create(
        actor_username="alice", action="login_succeeded"
    )
    AuditEvent.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    today = timezone.localdate().isoformat()

    today_rows = admin_client.get(
        f"/api/v1/admin/audit/?date_from={today}&date_to={today}"
    ).json()
    ids = {row["id"] for row in today_rows["results"]}
    assert recent.pk in ids
    assert old.pk not in ids


@pytest.mark.django_db
def test_prune_audit_dry_run_and_real(admin_client):
    old = AuditEvent.objects.create(
        actor_username="alice", action="login_succeeded"
    )
    AuditEvent.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=400)
    )
    recent = AuditEvent.objects.create(
        actor_username="alice", action="login_succeeded"
    )

    dry_output = StringIO()
    call_command("prune_audit", "--days", "180", "--dry-run", stdout=dry_output)
    assert "试运行" in dry_output.getvalue()
    assert AuditEvent.objects.filter(pk=old.pk).exists()

    output = StringIO()
    call_command("prune_audit", "--days", "180", stdout=output)
    assert not AuditEvent.objects.filter(pk=old.pk).exists()
    assert AuditEvent.objects.filter(pk=recent.pk).exists()

    pruned = _audit("audit_pruned")
    assert pruned is not None
    assert pruned.actor_username == "system"
    assert pruned.detail["deleted"] >= 1


@pytest.mark.django_db
def test_system_status_is_admin_only(admin_client, user_client):
    response = admin_client.get("/api/v1/admin/system/status/")
    assert response.status_code == 200
    data = response.json()
    assert data["version"]
    assert "backup" in data
    assert "reminder_due" in data["backup"]
    assert "vault" in data
    assert "disk_free_bytes" in data

    assert user_client.get("/api/v1/admin/system/status/").status_code == 404


@pytest.mark.django_db
def test_audit_records_survive_actor_deletion(admin_client, other_user):
    response = admin_client.post(
        f"/api/v1/admin/users/{other_user.pk}/disable/"
    )
    assert response.status_code == 200

    event = _audit("user_disabled")
    assert event is not None
    event.actor.delete()
    event.refresh_from_db()
    assert event.actor is None
    assert event.actor_username
