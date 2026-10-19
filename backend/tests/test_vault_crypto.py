"""Cryptographic primitives, key file and integrity tests."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.vault import crypto
from tests.helpers import MASTER_PASSWORD, OTHER_MASTER_PASSWORD


def _initialize() -> bytes:
    crypto.initialize(MASTER_PASSWORD)
    return crypto.require_master_key()


def test_key_file_is_created_once_and_contains_no_plaintext():
    _initialize()

    key_path = Path(settings.VAULT_KEY_FILE)
    assert key_path.is_file()
    raw = key_path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["format"] == crypto.KEY_FILE_FORMAT
    assert payload["cipher"]["name"] == "AES-256-GCM"
    assert MASTER_PASSWORD not in raw
    assert payload["kdf"]["name"] == "argon2id"
    assert "wrapped_key" in payload["cipher"]
    assert "master_key" not in payload
    assert payload["kdf"]["memory_cost"] >= 8

    with pytest.raises(crypto.VaultAlreadyInitialized):
        crypto.initialize(OTHER_MASTER_PASSWORD)


def test_lock_and_unlock_cycle():
    _initialize()
    assert crypto.is_initialized() is True
    assert crypto.is_unlocked() is True

    crypto.lock()
    assert crypto.is_unlocked() is False
    with pytest.raises(crypto.VaultLocked):
        crypto.require_master_key()

    crypto.unlock(MASTER_PASSWORD)
    assert crypto.is_unlocked() is True
    assert crypto.require_master_key()


def test_wrong_master_password_is_rejected():
    _initialize()
    crypto.lock()

    with pytest.raises(crypto.InvalidMasterPassword):
        crypto.unlock(OTHER_MASTER_PASSWORD)
    assert crypto.is_unlocked() is False


def test_text_encryption_roundtrip_and_tamper_detection():
    master_key = _initialize()
    payload = {
        "url": "https://db.example.test",
        "username": "vault-admin",
        "password": "Super-Secret-Value-2026!",
        "notes": "not in logs",
    }

    encrypted = crypto.encrypt_text(master_key, 42, payload)

    assert b"Super-Secret-Value-2026!" not in encrypted.ciphertext
    assert b"db.example.test" not in encrypted.ciphertext
    assert len(encrypted.plaintext_sha256) == 32

    decrypted = crypto.decrypt_text(
        master_key,
        42,
        encrypted.wrapped_dek,
        encrypted.dek_nonce,
        encrypted.payload_nonce,
        encrypted.ciphertext,
        encrypted.plaintext_sha256,
    )
    assert decrypted == payload

    tampered = bytearray(encrypted.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(crypto.ContentIntegrityError):
        crypto.decrypt_text(
            master_key,
            42,
            encrypted.wrapped_dek,
            encrypted.dek_nonce,
            encrypted.payload_nonce,
            bytes(tampered),
            encrypted.plaintext_sha256,
        )


def test_text_ciphertext_is_bound_to_the_item_id():
    master_key = _initialize()
    encrypted = crypto.encrypt_text(
        master_key, 7, {"url": "", "username": "u", "password": "p", "notes": ""}
    )

    with pytest.raises(crypto.ContentIntegrityError):
        crypto.decrypt_text(
            master_key,
            8,
            encrypted.wrapped_dek,
            encrypted.dek_nonce,
            encrypted.payload_nonce,
            encrypted.ciphertext,
            encrypted.plaintext_sha256,
        )


def test_file_encryption_roundtrip_and_integrity(tmp_path):
    master_key = _initialize()
    item_id = 99
    wrapped, nonce, dek = crypto.wrap_dek(master_key, item_id)
    assert crypto.unwrap_dek(master_key, wrapped, nonce, item_id) == dek

    plaintext = (b"KNOWN-PLAINTEXT-MARKER\n" * 5000) + b"tail"
    destination = tmp_path / "blob.vault"
    result = crypto.encrypt_file(
        dek,
        item_id,
        io.BytesIO(plaintext),
        destination,
        chunk_size=8192,
    )

    assert result.plaintext_size == len(plaintext)
    assert result.ciphertext_size == destination.stat().st_size
    blob = destination.read_bytes()
    assert crypto.MAGIC in blob[:8]
    assert b"KNOWN-PLAINTEXT-MARKER" not in blob
    assert b"tail" not in blob

    restored = crypto.read_file_plaintext(
        destination,
        dek,
        item_id,
        result.plaintext_sha256,
        chunk_size=4096,
    )
    assert restored == plaintext

    tampered = bytearray(blob)
    tampered[crypto.HEADER_SIZE + 1] ^= 0x01
    destination.write_bytes(bytes(tampered))
    with pytest.raises(crypto.ContentIntegrityError):
        crypto.read_file_plaintext(
            destination,
            dek,
            item_id,
            result.plaintext_sha256,
            chunk_size=4096,
        )


def test_file_ciphertext_is_bound_to_item_id(tmp_path):
    master_key = _initialize()
    _wrapped, _nonce, dek = crypto.wrap_dek(master_key, 1)
    destination = tmp_path / "bound.vault"
    result = crypto.encrypt_file(
        dek, 1, io.BytesIO(b"bound-content"), destination, chunk_size=16
    )

    with pytest.raises(crypto.ContentIntegrityError):
        crypto.read_file_plaintext(
            destination, dek, 2, result.plaintext_sha256, chunk_size=16
        )


def test_metadata_roundtrip():
    master_key = _initialize()
    _wrapped, _nonce, dek = crypto.wrap_dek(master_key, 5)
    encrypted = crypto.encrypt_metadata(
        5,
        dek,
        {"filename": "报表 2026.xlsx", "content_type": "application/vnd.ms-excel"},
    )

    assert b"report" not in encrypted.ciphertext
    assert b".xlsx" not in encrypted.ciphertext
    metadata = crypto.decrypt_metadata(
        5, dek, encrypted.ciphertext, encrypted.nonce
    )
    assert metadata["filename"] == "报表 2026.xlsx"

    with pytest.raises(crypto.ContentIntegrityError):
        crypto.decrypt_metadata(
            6, dek, encrypted.ciphertext, encrypted.nonce
        )
