"""Encrypted text/file content, recycle bin and purge operations."""

from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from . import crypto
from .models import VaultContent, VaultItem

logger = logging.getLogger("apps.vault")

TEXT_FIELDS = ("url", "username", "password", "notes")
MIME_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
PURGE_CACHE_KEY = "vault:last-trash-purge"


class ContentError(Exception):
    """Base class for content lifecycle errors."""


class ContentTypeMismatch(ContentError):
    pass


class ContentNotFound(ContentError):
    pass


def get_content(item: VaultItem) -> VaultContent | None:
    return VaultContent.objects.filter(item_id=item.pk).first()


def require_content(item: VaultItem) -> VaultContent:
    content = get_content(item)
    if content is None:
        raise ContentNotFound("这条内容还没有加密正文。")
    return content


def sanitize_filename(name: str | None, fallback: str = "download") -> str:
    """Remove path separators and control characters from a display name."""

    value = (name or "").replace("\\", "/").split("/")[-1]
    value = "".join(
        character
        for character in value
        if character >= " " and character not in "\r\n"
    ).strip().strip(".")
    return value[:255] or fallback


def sanitize_mime_type(value: str | None) -> str:
    candidate = (value or "").strip().split(";")[0].strip()
    if len(candidate) <= 100 and MIME_RE.fullmatch(candidate):
        return candidate
    return "application/octet-stream"


def _text_payload_from_values(values: dict) -> dict[str, str]:
    return {
        field: str(values.get(field, "") or "")
        for field in TEXT_FIELDS
    }


def save_text_content(item: VaultItem, actor, values: dict) -> VaultContent:
    """Create or update an encrypted text payload.

    On update, omitted fields keep their old value. An omitted password is
    preserved; ``clear_password=True`` explicitly sets it to an empty string.
    """

    if item.item_type != VaultItem.ItemType.TEXT:
        raise ContentTypeMismatch("这条条目不是文字类型。")

    existing = get_content(item)
    if existing is not None and existing.content_type != VaultItem.ItemType.TEXT:
        raise ContentTypeMismatch("这条条目已有文件内容，不能改成文字内容。")

    master_key = crypto.require_master_key()

    if existing is None:
        merged = _text_payload_from_values(values)
    else:
        old = crypto.decrypt_text(
            master_key,
            item.pk,
            existing.wrapped_dek,
            existing.dek_nonce,
            existing.payload_nonce,
            existing.encrypted_payload,
            existing.plaintext_sha256,
        )
        merged = {
            "url": str(values.get("url", old.get("url", "")) or ""),
            "username": str(
                values.get("username", old.get("username", "")) or ""
            ),
            "notes": str(values.get("notes", old.get("notes", "")) or ""),
            "password": str(old.get("password", "") or ""),
        }
        if values.get("clear_password"):
            merged["password"] = ""
        elif "password" in values:
            merged["password"] = str(values.get("password") or "")

    encrypted = crypto.encrypt_text(master_key, item.pk, merged)

    with transaction.atomic():
        if existing is None:
            existing = VaultContent.objects.create(
                item=item,
                content_type=VaultItem.ItemType.TEXT,
                encryption_version=1,
                key_version=1,
                wrapped_dek=encrypted.wrapped_dek,
                dek_nonce=encrypted.dek_nonce,
                payload_nonce=encrypted.payload_nonce,
                encrypted_payload=encrypted.ciphertext,
                blob_path="",
                ciphertext_size=len(encrypted.ciphertext),
                plaintext_size=encrypted.plaintext_size,
                plaintext_sha256=encrypted.plaintext_sha256,
                encrypted_metadata=b"",
                metadata_nonce=b"",
                created_by=actor,
            )
        else:
            existing.content_type = VaultItem.ItemType.TEXT
            existing.encryption_version = 1
            existing.key_version = 1
            existing.wrapped_dek = encrypted.wrapped_dek
            existing.dek_nonce = encrypted.dek_nonce
            existing.payload_nonce = encrypted.payload_nonce
            existing.encrypted_payload = encrypted.ciphertext
            existing.blob_path = ""
            existing.ciphertext_size = len(encrypted.ciphertext)
            existing.plaintext_size = encrypted.plaintext_size
            existing.plaintext_sha256 = encrypted.plaintext_sha256
            existing.encrypted_metadata = b""
            existing.metadata_nonce = b""
            existing.save(
                update_fields=[
                    "content_type",
                    "encryption_version",
                    "key_version",
                    "wrapped_dek",
                    "dek_nonce",
                    "payload_nonce",
                    "encrypted_payload",
                    "blob_path",
                    "ciphertext_size",
                    "plaintext_size",
                    "plaintext_sha256",
                    "encrypted_metadata",
                    "metadata_nonce",
                    "updated_at",
                ]
            )
    return existing


def get_text_payload(item: VaultItem) -> dict:
    content = require_content(item)
    if content.content_type != VaultItem.ItemType.TEXT:
        raise ContentTypeMismatch("这条条目不是文字类型。")
    master_key = crypto.require_master_key()
    return crypto.decrypt_text(
        master_key,
        item.pk,
        content.wrapped_dek,
        content.dek_nonce,
        content.payload_nonce,
        content.encrypted_payload,
        content.plaintext_sha256,
    )


def blob_file(content: VaultContent) -> Path:
    if not content.blob_path:
        raise crypto.ContentIntegrityError("内容缺少密文文件路径。")
    base = Path(settings.VAULT_OBJECTS_DIR).resolve()
    candidate = (base / content.blob_path).resolve()
    if candidate != base and base not in candidate.parents:
        raise crypto.ContentIntegrityError("密文文件路径无效。")
    return candidate


def delete_blob(blob_path: str) -> None:
    if not blob_path:
        return
    base = Path(settings.VAULT_OBJECTS_DIR).resolve()
    candidate = (base / blob_path).resolve()
    if candidate != base and base not in candidate.parents:
        logger.warning("blob_delete_rejected path=%s", blob_path)
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        logger.warning("blob_delete_failed path=%s", blob_path)


def save_uploaded_file(
    item: VaultItem,
    actor,
    upload,
    dek: bytes,
) -> VaultContent:
    """Move an encrypted upload into the object store and save its record."""

    if item.item_type != VaultItem.ItemType.FILE:
        raise ContentTypeMismatch("这条条目不是文件类型。")

    existing = get_content(item)
    if existing is not None and existing.content_type != VaultItem.ItemType.FILE:
        raise ContentTypeMismatch("这条条目已有文字内容，不能改成文件内容。")

    master_key = crypto.require_master_key()
    metadata = {
        "filename": sanitize_filename(upload.name),
        "content_type": sanitize_mime_type(upload.content_type),
    }
    encrypted_metadata = crypto.encrypt_metadata(item.pk, dek, metadata)
    wrapped_dek, dek_nonce, _ = crypto.wrap_dek(master_key, item.pk, dek)

    objects_dir = Path(settings.VAULT_OBJECTS_DIR)
    objects_dir.mkdir(parents=True, exist_ok=True)
    final_name = f"{secrets.token_hex(16)}.vault"
    final_path = objects_dir / final_name
    try:
        os.replace(upload.temp_path, final_path)
    except OSError as exc:
        try:
            Path(upload.temp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise ContentError("密文文件保存失败。") from exc

    old_blob = existing.blob_path if existing else ""

    try:
        with transaction.atomic():
            if existing is None:
                existing = VaultContent.objects.create(
                    item=item,
                    content_type=VaultItem.ItemType.FILE,
                    encryption_version=1,
                    key_version=1,
                    wrapped_dek=wrapped_dek,
                    dek_nonce=dek_nonce,
                    payload_nonce=None,
                    encrypted_payload=None,
                    blob_path=final_name,
                    ciphertext_size=upload.ciphertext_size,
                    plaintext_size=upload.plaintext_size,
                    plaintext_sha256=upload.plaintext_sha256,
                    encrypted_metadata=encrypted_metadata.ciphertext,
                    metadata_nonce=encrypted_metadata.nonce,
                    created_by=actor,
                )
            else:
                existing.content_type = VaultItem.ItemType.FILE
                existing.encryption_version = 1
                existing.key_version = 1
                existing.wrapped_dek = wrapped_dek
                existing.dek_nonce = dek_nonce
                existing.payload_nonce = None
                existing.encrypted_payload = None
                existing.blob_path = final_name
                existing.ciphertext_size = upload.ciphertext_size
                existing.plaintext_size = upload.plaintext_size
                existing.plaintext_sha256 = upload.plaintext_sha256
                existing.encrypted_metadata = encrypted_metadata.ciphertext
                existing.metadata_nonce = encrypted_metadata.nonce
                existing.save(
                    update_fields=[
                        "content_type",
                        "encryption_version",
                        "key_version",
                        "wrapped_dek",
                        "dek_nonce",
                        "payload_nonce",
                        "encrypted_payload",
                        "blob_path",
                        "ciphertext_size",
                        "plaintext_size",
                        "plaintext_sha256",
                        "encrypted_metadata",
                        "metadata_nonce",
                        "updated_at",
                    ]
                )
    except Exception:
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    if old_blob and old_blob != final_name:
        delete_blob(old_blob)

    return existing


def load_file_parts(content: VaultContent) -> tuple[bytes, dict]:
    master_key = crypto.require_master_key()
    dek = crypto.unwrap_dek(
        master_key, content.wrapped_dek, content.dek_nonce, content.item_id
    )
    metadata = crypto.decrypt_metadata(
        content.item_id,
        dek,
        content.encrypted_metadata,
        content.metadata_nonce,
    )
    return dek, metadata


def verify_file_content(content: VaultContent, chunk_size: int) -> dict:
    dek, metadata = load_file_parts(content)
    decryptor = crypto.FileDecryptor(
        blob_file(content), dek, content.item_id
    )
    try:
        size = decryptor.verify(chunk_size, content.plaintext_sha256)
    finally:
        decryptor.close()
    if size != content.plaintext_size:
        raise crypto.ContentIntegrityError("文件大小校验值不一致。")
    return metadata


def stream_file_content(content: VaultContent, chunk_size: int):
    dek, _metadata = load_file_parts(content)
    decryptor = crypto.FileDecryptor(
        blob_file(content), dek, content.item_id
    )
    try:
        yield from decryptor.chunks(chunk_size)
    finally:
        decryptor.close()


def trash_item(item: VaultItem, actor) -> VaultItem:
    if not item.is_deleted:
        item.is_deleted = True
        item.deleted_at = timezone.now()
        item.deleted_by = actor
        item.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"]
        )
        logger.info(
            "item_trashed actor=%s item_id=%s",
            getattr(actor, "username", "-"),
            item.pk,
        )
    return item


def restore_item(item: VaultItem, actor) -> VaultItem:
    if item.is_deleted:
        item.is_deleted = False
        item.deleted_at = None
        item.deleted_by = None
        item.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"]
        )
        logger.info(
            "item_restored actor=%s item_id=%s",
            getattr(actor, "username", "-"),
            item.pk,
        )
    return item


def purge_item(item: VaultItem) -> None:
    item_id = item.pk
    content = get_content(item)
    blob_path = content.blob_path if content is not None else ""
    with transaction.atomic():
        item.delete()
    if blob_path:
        delete_blob(blob_path)
    logger.info("item_purged item_id=%s", item_id)


def purge_expired_items() -> int:
    retention_days = max(
        1, int(getattr(settings, "VAULT_TRASH_RETENTION_DAYS", 30))
    )
    cutoff = timezone.now() - timedelta(days=retention_days)
    items = list(
        VaultItem.objects.filter(
            is_deleted=True,
            deleted_at__isnull=False,
            deleted_at__lte=cutoff,
        ).select_related("content")
    )
    for item in items:
        purge_item(item)
    return len(items)


def maybe_purge_expired_items() -> int:
    """Run an expired-trash sweep at most once per hour per process."""

    now = timezone.now()
    last = cache.get(PURGE_CACHE_KEY)
    if last is not None:
        try:
            if (now - last).total_seconds() < 3600:
                return 0
        except TypeError:
            pass
    cache.set(PURGE_CACHE_KEY, now, 3600)
    return purge_expired_items()
