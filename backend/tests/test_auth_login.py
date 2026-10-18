"""Login, lockout, logout and password-change tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from tests.conftest import csrf_token
from tests.helpers import NEW_PASSWORD, TEST_PASSWORD


@pytest.mark.django_db
def test_login_success_sets_secure_session_cookie(client, normal_user):
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "ALICE", "password": TEST_PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice"
    assert data["role"] == User.Role.USER
    assert "password" not in data

    cookie = response.cookies["sessionid"]
    assert cookie["httponly"] is True
    assert cookie["samesite"].lower() == "lax"
    assert client.session.get("login_at")


@pytest.mark.django_db
def test_wrong_password_uses_generic_error_and_counts_a_failure(client, normal_user):
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": "definitely-wrong-password"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "用户名或密码错误。"
    normal_user.refresh_from_db()
    assert normal_user.failed_login_attempts == 1
    assert "sessionid" not in response.cookies


@pytest.mark.django_db
def test_unknown_username_uses_the_same_error(client):
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "nobody-here", "password": TEST_PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "用户名或密码错误。"


@pytest.mark.django_db
def test_inactive_user_cannot_login(client, normal_user):
    normal_user.is_active = False
    normal_user.save(update_fields=["is_active"])

    response = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "用户名或密码错误。"
    assert "sessionid" not in response.cookies


@pytest.mark.django_db
def test_five_failures_lock_the_account(client, normal_user):
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login/",
            {"username": "alice", "password": "wrong-password"},
            content_type="application/json",
        )
        assert response.status_code == 400

    normal_user.refresh_from_db()
    assert normal_user.failed_login_attempts == 5
    assert normal_user.is_locked()

    blocked = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert blocked.status_code == 423
    assert blocked.json()["code"] == "account_locked"


@pytest.mark.django_db
def test_expired_lock_allows_login_and_resets_failures(client, normal_user):
    normal_user.failed_login_attempts = 5
    normal_user.locked_until = timezone.now() - timedelta(seconds=1)
    normal_user.save(update_fields=["failed_login_attempts", "locked_until"])

    response = client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.failed_login_attempts == 0
    assert normal_user.locked_until is None


@pytest.mark.django_db
def test_admin_can_unlock_a_locked_user(admin_client, normal_user):
    normal_user.failed_login_attempts = 5
    normal_user.locked_until = timezone.now() + timedelta(minutes=15)
    normal_user.save(update_fields=["failed_login_attempts", "locked_until"])

    response = admin_client.post(
        f"/api/v1/admin/users/{normal_user.pk}/unlock/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["is_locked"] is False

    normal_user.refresh_from_db()
    assert normal_user.failed_login_attempts == 0
    assert normal_user.locked_until is None


@pytest.mark.django_db
def test_must_change_password_blocks_other_endpoints(client):
    user = User.objects.create_user(
        username="tempadmin",
        display_name="临时管理员",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
        must_change_password=True,
    )

    login = client.post(
        "/api/v1/auth/login/",
        {"username": "tempadmin", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200

    blocked = client.get("/api/v1/admin/users/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "password_change_required"

    changed = client.post(
        "/api/v1/auth/change-password/",
        {
            "current_password": TEST_PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    )
    assert changed.status_code == 200

    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password(NEW_PASSWORD)

    assert client.get("/api/v1/admin/users/").status_code == 200


@pytest.mark.django_db
def test_change_password_rejects_wrong_current_password(client, normal_user):
    client.force_login(normal_user)

    response = client.post(
        "/api/v1/auth/change-password/",
        {
            "current_password": "wrong-current-password",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    normal_user.refresh_from_db()
    assert normal_user.check_password(TEST_PASSWORD)


@pytest.mark.django_db
def test_change_password_invalidates_other_sessions(normal_user):
    first = Client()
    second = Client()
    login_payload = {"username": "alice", "password": TEST_PASSWORD}

    assert first.post(
        "/api/v1/auth/login/", login_payload, content_type="application/json"
    ).status_code == 200
    assert second.post(
        "/api/v1/auth/login/", login_payload, content_type="application/json"
    ).status_code == 200

    changed = first.post(
        "/api/v1/auth/change-password/",
        {
            "current_password": TEST_PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        content_type="application/json",
    )
    assert changed.status_code == 200

    assert first.get("/api/v1/auth/me/").status_code == 200
    assert second.get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_logout_invalidates_current_session(client, normal_user):
    assert client.post(
        "/api/v1/auth/login/",
        {"username": "alice", "password": TEST_PASSWORD},
        content_type="application/json",
    ).status_code == 200

    response = client.post("/api/v1/auth/logout/")
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_login_requires_csrf_and_accepts_a_valid_token(normal_user):
    client = Client(enforce_csrf_checks=True)
    payload = {"username": "alice", "password": TEST_PASSWORD}

    blocked = client.post(
        "/api/v1/auth/login/", payload, content_type="application/json"
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "csrf_failed"

    token = csrf_token(client)
    allowed = client.post(
        "/api/v1/auth/login/",
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_unauthenticated_requests_get_401(client):
    assert client.get("/api/v1/auth/me/").status_code == 401
    assert client.get("/api/v1/admin/users/").status_code == 401
