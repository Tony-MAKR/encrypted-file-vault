"""Shared fixtures for the account test suite."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.models import User
from apps.vault import crypto as vault_crypto
from apps.vault.models import VaultGroup, VaultItem
from tests.helpers import TEST_PASSWORD


@pytest.fixture(autouse=True)
def isolated_vault_storage(tmp_path, settings):
    """Keep tests away from the real key and object directories."""

    settings.VAULT_KEY_FILE = str(tmp_path / "keys" / "master.key.json")
    settings.VAULT_OBJECTS_DIR = str(tmp_path / "vault" / "objects")
    settings.VAULT_TMP_DIR = str(tmp_path / "vault" / "tmp")
    settings.BACKUP_DIR = str(tmp_path / "backups")
    for directory in (
        tmp_path / "keys",
        tmp_path / "vault" / "objects",
        tmp_path / "vault" / "tmp",
        tmp_path / "backups",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    settings.VAULT_KDF_TIME_COST = 1
    settings.VAULT_KDF_MEMORY_COST = 8192
    settings.VAULT_KDF_PARALLELISM = 1
    vault_crypto.reset_state()
    yield
    vault_crypto.reset_state()


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


@pytest.fixture
def second_admin(db) -> User:
    return User.objects.create_user(
        username="admin2",
        display_name="第二管理员",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
    )


@pytest.fixture
def other_user(db) -> User:
    return User.objects.create_user(
        username="bob",
        display_name="Bob",
        password=TEST_PASSWORD,
        role=User.Role.USER,
    )


@pytest.fixture
def other_client(other_user: User) -> Client:
    client = Client()
    client.force_login(other_user)
    return client


@pytest.fixture
def vault_group(db, admin_user: User) -> VaultGroup:
    return VaultGroup.objects.create(
        name="财务组",
        description="负责财务资料",
        created_by=admin_user,
    )


@pytest.fixture
def vault_item(db, admin_user: User) -> VaultItem:
    return VaultItem.objects.create(
        title="数据库密码",
        item_type=VaultItem.ItemType.TEXT,
        description="生产数据库的登录信息",
        owner=admin_user,
    )


def csrf_token(client: Client) -> str:
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 204
    token = client.cookies.get("csrftoken")
    assert token is not None
    return token.value
