"""Administrator user-management tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import is_last_active_admin
from tests.conftest import csrf_token
from tests.helpers import NEW_PASSWORD, TEST_PASSWORD

CREATE_PASSWORD = "Created-User-Password-2026!"


def _new_user_payload(username: str = "bob", role: str = User.Role.USER) -> dict:
    return {
        "username": username,
        "display_name": "鲍勃",
        "password": CREATE_PASSWORD,
        "password_confirm": CREATE_PASSWORD,
        "role": role,
    }


@pytest.mark.django_db
def test_admin_can_create_user_with_forced_password_change(admin_client):
    response = admin_client.post(
        "/api/v1/admin/users/",
        _new_user_payload(),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "bob"
    assert data["role"] == User.Role.USER
    assert data["must_change_password"] is True
    assert data["created_by"] == "admin"
    assert "password" not in data

    user = User.objects.get(username="bob")
    assert user.check_password(CREATE_PASSWORD)
    assert user.password.startswith("argon2$")


@pytest.mark.django_db
def test_normal_user_cannot_use_admin_endpoints(user_client, normal_user):
    assert user_client.get("/api/v1/admin/users/").status_code == 403
    assert user_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/disable/",
        {},
        content_type="application/json",
    ).status_code == 403
    assert user_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/reset-password/",
        {
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    ).status_code == 403


@pytest.mark.django_db
def test_duplicate_username_is_rejected_case_insensitively(admin_client):
    first = admin_client.post(
        "/api/v1/admin/users/",
        _new_user_payload("Bob"),
        content_type="application/json",
    )
    assert first.status_code == 201

    second = admin_client.post(
        "/api/v1/admin/users/",
        _new_user_payload("BOB"),
        content_type="application/json",
    )
    assert second.status_code == 400
    assert "username" in second.json()
    assert User.objects.filter(username="bob").count() == 1


@pytest.mark.django_db
def test_weak_password_is_rejected_on_creation(admin_client):
    payload = _new_user_payload("weakuser")
    payload["password"] = "short"
    payload["password_confirm"] = "short"

    response = admin_client.post(
        "/api/v1/admin/users/", payload, content_type="application/json"
    )

    assert response.status_code == 400
    assert User.objects.filter(username="weakuser").exists() is False


@pytest.mark.django_db
def test_user_list_supports_search_and_pagination(admin_client, normal_user):
    for index in range(3):
        User.objects.create_user(
            username=f"user{index}",
            display_name=f"测试用户{index}",
            password=TEST_PASSWORD,
            role=User.Role.USER,
        )

    response = admin_client.get("/api/v1/admin/users/?page_size=2&q=用户")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 3
    assert len(data["results"]) == 2
    assert "password" not in data["results"][0]


@pytest.mark.django_db
def test_disable_invalidates_target_sessions_and_blocks_login(
    admin_client, normal_user
):
    target_client = Client()
    login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert login.status_code == 200

    disabled = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/disable/",
        {},
        content_type="application/json",
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    assert target_client.get("/api/v1/auth/me/").status_code == 401

    blocked_login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert blocked_login.status_code == 400

    enabled = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/enable/",
        {},
        content_type="application/json",
    )
    assert enabled.status_code == 200
    assert enabled.json()["is_active"] is True

    allowed_login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert allowed_login.status_code == 200


@pytest.mark.django_db
def test_admin_cannot_disable_reset_or_change_own_role(admin_client, admin_user):
    disable = admin_client.post(
        f"/api/v1/admin/users/{admin_user.pk}/disable/",
        {},
        content_type="application/json",
    )
    assert disable.status_code == 400

    reset = admin_client.post(
        f"/api/v1/admin/users/{admin_user.pk}/reset-password/",
        {
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    )
    assert reset.status_code == 400

    role = admin_client.post(
        f"/api/v1/admin/users/{admin_user.pk}/role/",
        {"role": User.Role.USER},
        content_type="application/json",
    )
    assert role.status_code == 400


@pytest.mark.django_db
def test_last_admin_protection_service(admin_user):
    assert is_last_active_admin(admin_user) is True

    second = User.objects.create_user(
        username="secondadmin",
        display_name="第二管理员",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
    )
    assert is_last_active_admin(admin_user) is False

    second.is_active = False
    second.save(update_fields=["is_active"])
    assert is_last_active_admin(admin_user) is True


@pytest.mark.django_db
def test_admin_can_demote_another_admin_when_another_remains(
    admin_client, admin_user
):
    second = User.objects.create_user(
        username="secondadmin",
        display_name="第二管理员",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
    )

    response = admin_client.post(
        f"/api/v1/admin/users/{second.pk}/role/",
        {"role": User.Role.USER},
        content_type="application/json",
    )

    assert response.status_code == 200
    second.refresh_from_db()
    assert second.role == User.Role.USER
    assert is_last_active_admin(admin_user) is True


@pytest.mark.django_db
def test_admin_can_promote_user_and_their_session_picks_up_new_role(
    admin_client, user_client, normal_user
):
    response = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/role/",
        {"role": User.Role.ADMIN},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["role"] == User.Role.ADMIN

    # The existing session is not destroyed; permissions are checked per request.
    assert user_client.get("/api/v1/admin/users/").status_code == 200


@pytest.mark.django_db
def test_admin_reset_password_forces_change_and_invalidates_sessions(
    admin_client, normal_user
):
    target_client = Client()
    login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert login.status_code == 200

    reset = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/reset-password/",
        {
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    )
    assert reset.status_code == 200

    assert target_client.get("/api/v1/auth/me/").status_code == 401

    old_login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert old_login.status_code == 400

    temp_login = target_client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": NEW_PASSWORD},
        content_type="application/json",
    )
    assert temp_login.status_code == 200
    assert temp_login.json()["must_change_password"] is True

    blocked = target_client.get("/api/v1/admin/users/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "password_change_required"


@pytest.mark.django_db
def test_admin_can_unlock_user(admin_client, normal_user):
    normal_user.failed_login_attempts = 5
    normal_user.locked_until = timezone.now() + timedelta(minutes=15)
    normal_user.save(update_fields=["failed_login_attempts", "locked_until"])

    response = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/unlock/",
        {},
        content_type="application/json",
    )

    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.locked_until is None
    assert normal_user.failed_login_attempts == 0


@pytest.mark.django_db
def test_admin_can_update_display_name(admin_client, normal_user):
    response = admin_client.patch(
        f"/api/v1/admin/users/{normal_user.pk}/",
        {"display_name": "新名字"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "新名字"


@pytest.mark.django_db
def test_admin_endpoints_require_csrf_for_state_changes(admin_client, normal_user):
    admin_client_csrf = Client(enforce_csrf_checks=True)
    admin_client_csrf.force_login(User.objects.get(username="admin"))
    token = csrf_token(admin_client_csrf)

    blocked = admin_client_csrf.post(
        f"/api/v1/admin/users/{normal_user.pk}/disable/",
        {},
        content_type="application/json",
    )
    assert blocked.status_code == 403
    assert "csrf" in str(blocked.json()).lower()

    allowed = admin_client_csrf.post(
        f"/api/v1/admin/users/{normal_user.pk}/disable/",
        {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 200
