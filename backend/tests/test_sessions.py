"""Session idle/absolute timeout and inactive-account tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from tests.helpers import TEST_PASSWORD


def _login(client, username: str) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_idle_timeout_requires_login_again(client, normal_user):
    _login(client, "alice")

    session = client.session
    session["last_activity"] = (
        timezone.now() - timedelta(minutes=31)
    ).isoformat()
    session.save()

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"
    assert client.get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_absolute_timeout_requires_login_again(client, normal_user):
    _login(client, "alice")

    session = client.session
    session["login_at"] = (timezone.now() - timedelta(hours=9)).isoformat()
    session["last_activity"] = timezone.now().isoformat()
    session.save()

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"


@pytest.mark.django_db
def test_activity_refreshes_idle_timestamp(client, normal_user):
    _login(client, "alice")

    old_activity = timezone.now() - timedelta(minutes=10)
    session = client.session
    session["last_activity"] = old_activity.isoformat()
    session.save()

    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200

    refreshed = client.session.get("last_activity")
    assert refreshed is not None
    assert refreshed != old_activity.isoformat()


@pytest.mark.django_db
def test_inactive_user_session_is_rejected(client, normal_user):
    _login(client, "alice")

    normal_user.is_active = False
    normal_user.save(update_fields=["is_active"])

    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    # Depending on Django's backend, an inactive user may already be treated
    # as anonymous before the custom middleware sees the session.
    assert response.json().get("code") in {None, "session_expired"}
