"""Shared fixtures for the account test suite."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.models import User
from tests.helpers import TEST_PASSWORD


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    """Keep IP throttles from leaking between tests."""

    cache.clear()


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_user(
        username="admin",
        display_name="管理员",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
    )


@pytest.fixture
def normal_user(db) -> User:
    return User.objects.create_user(
        username="alice",
        display_name="Alice",
        password=TEST_PASSWORD,
        role=User.Role.USER,
    )


@pytest.fixture
def admin_client(admin_user: User) -> Client:
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def user_client(normal_user: User) -> Client:
    client = Client()
    client.force_login(normal_user)
    return client


def csrf_token(client: Client) -> str:
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 204
    token = client.cookies.get("csrftoken")
    assert token is not None
    return token.value
