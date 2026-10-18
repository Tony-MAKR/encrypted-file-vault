"""First-run setup tests."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.accounts.models import User
from tests.helpers import SETUP_PASSWORD


def _payload(**overrides):
    data = {
        "username": "firstadmin",
        "display_name": "第一位管理员",
        "password": SETUP_PASSWORD,
        "password_confirm": SETUP_PASSWORD,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_setup_status_is_true_when_there_are_no_users(client):
    response = client.get("/api/v1/setup/status/")

    assert response.status_code == 200
    assert response.json() == {"needs_setup": True}


@pytest.mark.django_db
def test_setup_creates_an_admin_and_closes_the_endpoint(client):
    response = client.post(
        "/api/v1/setup/", _payload(), content_type="application/json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "firstadmin"
    assert data["display_name"] == "第一位管理员"
    assert data["role"] == User.Role.ADMIN
    assert data["must_change_password"] is False
    assert "password" not in data

    user = User.objects.get(username="firstadmin")
    assert user.check_password(SETUP_PASSWORD)
    assert user.password.startswith("argon2$")

    status_response = client.get("/api/v1/setup/status/")
    assert status_response.json() == {"needs_setup": False}

    second_response = client.post(
        "/api/v1/setup/",
        _payload(username="secondadmin"),
        content_type="application/json",
    )
    assert second_response.status_code == 409
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_setup_rejects_remote_requests(client):
    response = client.post(
        "/api/v1/setup/",
        _payload(),
        content_type="application/json",
        REMOTE_ADDR="192.168.1.50",
    )

    assert response.status_code == 403
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_setup_rejects_password_mismatch_without_creating_a_user(client):
    response = client.post(
        "/api/v1/setup/",
        _payload(password_confirm="Different-Password-2026!"),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_setup_rejects_weak_password(client):
    response = client.post(
        "/api/v1/setup/",
        _payload(password="short", password_confirm="short"),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_setup_rejects_invalid_username(client):
    response = client.post(
        "/api/v1/setup/",
        _payload(username="Bad User!"),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_setup_requires_csrf_token():
    client = Client(enforce_csrf_checks=True)

    blocked = client.post(
        "/api/v1/setup/", _payload(), content_type="application/json"
    )
    assert blocked.status_code == 403
    assert User.objects.count() == 0

    token = client.cookies.get("csrftoken")
    if token is None:
        csrf_response = client.get("/api/v1/auth/csrf/")
        assert csrf_response.status_code == 204
        token = client.cookies.get("csrftoken")

    assert token is not None
    allowed = client.post(
        "/api/v1/setup/",
        _payload(),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token.value,
    )
    assert allowed.status_code == 201
    assert User.objects.count() == 1
