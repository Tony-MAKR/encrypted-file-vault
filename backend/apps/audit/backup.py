"""Encrypted backup packages (``.efbak``) and restore helpers.

Package layout after decryption is a ZIP containing:

    manifest.json
    db/db.sqlite3
    keys/master.key.json      (only when the vault has been initialized)
    objects/<random>.vault

The ZIP is encrypted as a whole with AES-256-GCM using a key derived from an
independent backup passphrase (Argon2id). The passphrase is never stored.

File format:

    magic "EFB1" | version | salt | KDF params | base nonce | total size
    then fixed-size encrypted chunks, each followed by a 16-byte GCM tag.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import struct
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.utils import timezone as django_timezone

logger = logging.getLogger("apps.audit.backup")

MAGIC = b"EFB1"
FORMAT_VERSION = 1
SALT_SIZE = 16
KEY_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
MANIFEST_NAME = "manifest.json"
DATABASE_ENTRY = "db/db.sqlite3"
KEY_ENTRY = "keys/master.key.json"
BACKUP_FORMAT_NAME = "encrypted-file-vault-backup"

_HEADER = struct.Struct(">4sB16sIIB12sQ")
_HEADER_SIZE = _HEADER.size  # 50 bytes
_MIN_PASSWORD_LENGTH = 12
_MAX_PASSWORD_LENGTH = 256

_backup_lock = threading.Lock()


class BackupError(Exception):
    """Base class for backup problems safe to show to an administrator."""


class BackupPasswordError(BackupError):
    pass


class BackupIntegrityError(BackupError):
    pass


class BackupVersionError(BackupError):
    pass


class BackupSpaceError(BackupError):
    pass


class BackupBusy(BackupError):
    pass


@dataclass(frozen=True)
class BackupSummary:
    filename: str
    path: Path
    size_bytes: int
    sha256: str
    format_version: int
    app_version: str
    created_at: str
    counts: dict[str, int]


def validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise BackupError("请输入备份口令。")
    value = password.strip()
    if len(value) < _MIN_PASSWORD_LENGTH:
        raise BackupError(f"备份口令至少需要 {_MIN_PASSWORD_LENGTH} 位。")
    if len(value) > _MAX_PASSWORD_LENGTH:
        raise BackupError("备份口令太长。")
    return value


def _derive_key(
    password: str, salt: bytes, time_cost: int, memory_cost: int, parallelism: int
) -> bytes:
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=max(1, int(time_cost)),
        memory_cost=max(8, int(memory_cost)),
        parallelism=max(1, int(parallelism)),
        hash_len=KEY_SIZE,
        type=Argon2Type.ID,
    )


def _kdf_params() -> tuple[int, int, int]:
    return (
        int(getattr(settings, "VAULT_KDF_TIME_COST", 3)),
        int(getattr(settings, "VAULT_KDF_MEMORY_COST", 65536)),
        int(getattr(settings, "VAULT_KDF_PARALLELISM", 4)),
    )


def _chunk_aad(header: bytes, index: int, final: bool) -> bytes:
    return header + struct.pack(">Q", index) + (b"F" if final else b"C")


def _chunk_nonce(base_nonce: bytes, index: int) -> bytes:
    return base_nonce[:4] + struct.pack(">Q", index)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encrypt_zip(source: Path, target: Path, password: str) -> dict[str, object]:
    """Encrypt ``source`` to ``target``; returns header metadata."""

    password = validate_password(password)
    total_size = source.stat().st_size
    salt = secrets.token_bytes(SALT_SIZE)
    base_nonce = secrets.token_bytes(NONCE_SIZE)
    time_cost, memory_cost, parallelism = _kdf_params()
    header = _HEADER.pack(
        MAGIC,
        FORMAT_VERSION,
        salt,
        time_cost,
        memory_cost,
        parallelism,
        base_nonce,
        total_size,
    )
    key = _derive_key(password, salt, time_cost, memory_cost, parallelism)
    aes = AESGCM(key)

    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            writer.write(header)
            remaining = total_size
            index = 0
            while remaining > 0:
                block = reader.read(min(CHUNK_SIZE, remaining))
                if not block:
                    raise BackupIntegrityError("备份数据读取不完整。")
                final = len(block) == remaining
                writer.write(
                    aes.encrypt(
                        _chunk_nonce(base_nonce, index),
                        block,
                        _chunk_aad(header, index, final),
                    )
                )
                remaining -= len(block)
                index += 1
        os.replace(temporary, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "format_version": FORMAT_VERSION,
        "salt": salt,
        "base_nonce": base_nonce,
        "total_size": total_size,
        "sha256": _file_sha256(target),
        "size_bytes": target.stat().st_size,
    }


def decrypt_to_file(source: Path, target: Path, password: str) -> dict[str, object]:
    """Decrypt an ``.efbak`` file. Raises BackupPasswordError on bad tags."""

    try:
        with source.open("rb") as reader:
            header = reader.read(_HEADER_SIZE)
            if len(header) != _HEADER_SIZE:
                raise BackupIntegrityError("备份文件不完整。")
            (
                magic,
                version,
                salt,
                time_cost,
                memory_cost,
                parallelism,
                base_nonce,
                total_size,
            ) = _HEADER.unpack(header)
            if magic != MAGIC:
                raise BackupIntegrityError("不是有效的备份文件。")
            if version != FORMAT_VERSION:
                raise BackupVersionError(
                    f"备份格式版本 {version} 不受支持（当前支持 {FORMAT_VERSION}）。"
                )

            key = _derive_key(
                validate_password(password), salt, time_cost, memory_cost, parallelism
            )
            aes = AESGCM(key)
            remaining = int(total_size)
            index = 0
            with target.open("wb") as writer:
                while remaining > 0:
                    plain_length = min(CHUNK_SIZE, remaining)
                    ciphertext = reader.read(plain_length + TAG_SIZE)
                    if len(ciphertext) != plain_length + TAG_SIZE:
                        raise BackupIntegrityError("备份文件被截断或损坏。")
                    final = plain_length == remaining
                    try:
                        block = aes.decrypt(
                            _chunk_nonce(base_nonce, index),
                            ciphertext,
                            _chunk_aad(header, index, final),
                        )
                    except InvalidTag as exc:
                        raise BackupPasswordError(
                            "备份口令不正确，或备份文件已经损坏。"
                        ) from exc
                    writer.write(block)
                    remaining -= plain_length
                    index += 1
            if reader.read(1):
                raise BackupIntegrityError("备份文件末尾有无法识别的内容。")
    except (BackupError, OSError):
        target.unlink(missing_ok=True)
        raise

    return {
        "format_version": FORMAT_VERSION,
        "total_size": int(total_size),
        "sha256": _file_sha256(target),
    }


def _safe_relative_path(name: str, prefixes: tuple[str, ...]) -> bool:
    if not isinstance(name, str) or not name:
        return False
    if name.startswith(("/", "\\")) or ":" in name:
        return False
    normalized = name.replace("\\", "/")
    if ".." in normalized.split("/"):
        return False
    return any(normalized.startswith(prefix) for prefix in prefixes)


def _validate_manifest(manifest: object) -> dict:
    if not isinstance(manifest, dict):
        raise BackupIntegrityError("备份清单格式不正确。")
    if manifest.get("format") != BACKUP_FORMAT_NAME:
        raise BackupIntegrityError("备份清单标识不正确。")
    try:
        manifest_version = int(manifest.get("format_version", 0))
    except (TypeError, ValueError) as exc:
        raise BackupIntegrityError("备份清单版本不正确。") from exc
    if manifest_version != FORMAT_VERSION:
        raise BackupVersionError("备份清单版本不受支持。")
    database = manifest.get("database")
    if not isinstance(database, dict) or not _safe_relative_path(
        database.get("path", ""), ("db/",)
    ):
        raise BackupIntegrityError("备份清单缺少数据库文件。")
    if not isinstance(database.get("sha256"), str) or not isinstance(
        database.get("size"), int
    ):
        raise BackupIntegrityError("备份清单中的数据库信息不完整。")
    master_key = manifest.get("master_key")
    if master_key is not None:
        if not isinstance(master_key, dict) or not _safe_relative_path(
            master_key.get("path", ""), ("keys/",)
        ):
            raise BackupIntegrityError("备份清单中的密钥文件信息不正确。")
        if not isinstance(master_key.get("sha256"), str) or not isinstance(
            master_key.get("size"), int
        ):
            raise BackupIntegrityError("备份清单中的密钥文件信息不完整。")
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise BackupIntegrityError("备份清单中的密文列表不正确。")
    for entry in objects:
        if (
            not isinstance(entry, dict)
            or not _safe_relative_path(entry.get("path", ""), ("objects/",))
            or not isinstance(entry.get("sha256"), str)
            or not isinstance(entry.get("size"), int)
        ):
            raise BackupIntegrityError("备份清单中的密文信息不正确。")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise BackupIntegrityError("备份清单中的数量信息不正确。")
    return manifest


def _expected_entries(manifest: dict) -> dict[str, dict]:
    entries = {DATABASE_ENTRY: manifest["database"]}
    if manifest.get("master_key") is not None:
        entries[KEY_ENTRY] = manifest["master_key"]
    for entry in manifest["objects"]:
        entries[entry["path"]] = entry
    return entries


def _hash_zip_entry(
    zf: zipfile.ZipFile, name: str, expected_size: int
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with zf.open(name, "r") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
            if size > expected_size:
                raise BackupIntegrityError(f"备份文件大小不一致：{name}")
    return digest.hexdigest(), size


def inspect_backup_zip(zip_path: Path) -> dict:
    """Validate a decrypted ZIP against its manifest; returns the manifest."""

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if len(names) != len(set(names)):
                raise BackupIntegrityError("备份包内有重复文件。")
            if MANIFEST_NAME not in names:
                raise BackupIntegrityError("备份包缺少清单文件。")
            try:
                manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupIntegrityError("备份清单无法读取。") from exc
            manifest = _validate_manifest(manifest)
            expected = _expected_entries(manifest)

            extra = set(names) - set(expected) - {MANIFEST_NAME}
            if extra:
                raise BackupIntegrityError("备份包包含未授权的文件。")
            missing = set(expected) - set(names)
            if missing:
                raise BackupIntegrityError("备份包缺少必要文件。")

            for name, entry in expected.items():
                if zf.getinfo(name).file_size != entry["size"]:
                    raise BackupIntegrityError(f"备份文件大小不一致：{name}")
                digest, size = _hash_zip_entry(zf, name, entry["size"])
                if size != entry["size"] or digest != entry["sha256"]:
                    raise BackupIntegrityError(f"备份文件校验失败：{name}")
    except zipfile.BadZipFile as exc:
        raise BackupIntegrityError("备份包不是有效的压缩文件。") from exc
    return manifest


def extract_backup_zip(
    zip_path: Path, manifest: dict, destination: Path
) -> None:
    """Extract only the manifest-approved files, rejecting unsafe paths."""

    destination.mkdir(parents=True, exist_ok=True)
    expected = _expected_entries(manifest)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name, entry in expected.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            written = 0
            with zf.open(name, "r") as reader, target.open("wb") as writer:
                for block in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(block)
                    digest.update(block)
                    written += len(block)
                    if written > entry["size"]:
                        raise BackupIntegrityError(f"备份文件大小不一致：{name}")
            if written != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise BackupIntegrityError(f"备份文件校验失败：{name}")


def database_counts(database_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    tables = {
        "users": "accounts_user",
        "groups": "vault_vaultgroup",
        "items": "vault_vaultitem",
        "contents": "vault_vaultcontent",
    }
    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro", uri=True
    )
    try:
        for key, table in tables.items():
            try:
                counts[key] = int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
            except sqlite3.DatabaseError:
                counts[key] = 0
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise BackupIntegrityError("备份中的数据库完整性检查未通过。")
    finally:
        connection.close()
    return counts


def _write_manifest(
    staging: Path, database_path: Path, key_path: Path, counts: dict[str, int]
) -> dict:
    objects = []
    objects_dir = staging / "objects"
    if objects_dir.is_dir():
        for path in sorted(objects_dir.glob("*.vault")):
            objects.append(
                {
                    "path": f"objects/{path.name}",
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )

    database_entry = {
        "path": DATABASE_ENTRY,
        "size": database_path.stat().st_size,
        "sha256": _file_sha256(database_path),
    }
    key_entry = None
    if key_path.is_file():
        key_entry = {
            "path": KEY_ENTRY,
            "size": key_path.stat().st_size,
            "sha256": _file_sha256(key_path),
        }

    manifest = {
        "format": BACKUP_FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "app_version": settings.APP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": database_entry,
        "master_key": key_entry,
        "objects": objects,
        "counts": counts,
    }
    (staging / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _unique_backup_path(directory: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"vault-backup-{stamp}.efbak"
    counter = 1
    while candidate.exists():
        candidate = directory / f"vault-backup-{stamp}-{counter}.efbak"
        counter += 1
    return candidate


def _check_disk_space(required: int) -> None:
    usage = shutil.disk_usage(settings.BACKUP_DIR)
    if usage.free < int(required * 1.5) + 10 * 1024 * 1024:
        raise BackupSpaceError(
            "磁盘剩余空间不足，至少需要备份大小的 1.5 倍。请清理空间后重试。"
        )


def _live_database_size() -> int:
    database_name = str(settings.DATABASES["default"]["NAME"])
    database_path = Path(database_name)
    if database_path.is_file():
        return database_path.stat().st_size

    from django.db import connection as django_connection

    django_connection.ensure_connection()
    raw = django_connection.connection
    if raw is None:
        raise BackupError("找不到数据库连接，无法创建备份。")
    page_count = int(raw.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(raw.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def _open_live_database() -> tuple[sqlite3.Connection, bool, int]:
    """Return a connection to the live database, whether to close it, size.

    Production uses a file, but tests (and a future in-memory option) use a
    shared in-memory SQLite database that is only reachable through Django's
    existing connection.
    """

    database_name = str(settings.DATABASES["default"]["NAME"])
    database_path = Path(database_name)
    if database_path.is_file():
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True
        )
        return connection, True, database_path.stat().st_size

    from django.db import connection as django_connection

    django_connection.ensure_connection()
    raw = django_connection.connection
    if raw is None:
        raise BackupError("找不到数据库连接，无法创建备份。")
    page_count = int(raw.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(raw.execute("PRAGMA page_size").fetchone()[0])
    return raw, False, page_count * page_size


def create_backup(
    password: str, *, note: str = "", user=None
) -> BackupSummary:
    """Create an encrypted backup and record it. Raises BackupError."""

    password = validate_password(password)
    if not _backup_lock.acquire(blocking=False):
        raise BackupBusy("已有备份任务正在进行，请稍后再试。")
    try:
        backup_dir = Path(settings.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        tmp_root = Path(settings.VAULT_TMP_DIR)
        tmp_root.mkdir(parents=True, exist_ok=True)
        key_path = Path(settings.VAULT_KEY_FILE)
        objects_dir = Path(settings.VAULT_OBJECTS_DIR)
        object_files = (
            sorted(objects_dir.glob("*.vault")) if objects_dir.is_dir() else []
        )
        estimated = (
            _live_database_size()
            + sum(path.stat().st_size for path in object_files)
            + (key_path.stat().st_size if key_path.is_file() else 0)
        )
        _check_disk_space(estimated)

        work = tmp_root / f"backup-{uuid.uuid4().hex}"
        staging = work / "staging"
        zip_path = work / "backup.zip"
        try:
            (staging / "db").mkdir(parents=True)
            (staging / "objects").mkdir(parents=True)
            key_dir = staging / "keys"

            snapshot = staging / DATABASE_ENTRY
            source, close_source, _database_size = _open_live_database()
            destination = None
            try:
                destination = sqlite3.connect(snapshot)
                if close_source:
                    source.backup(destination)
                else:
                    # A file-backed database uses the online backup API above.
                    # Django's in-memory test database is inside a test
                    # transaction, where backup() can wait forever; a SQL dump
                    # produces the same consistent snapshot for this case.
                    for statement in source.iterdump():
                        destination.execute(statement)
                    destination.commit()
            finally:
                if destination is not None:
                    destination.close()
                if close_source:
                    source.close()

            if key_path.is_file():
                key_dir.mkdir(parents=True)
                shutil.copy2(key_path, staging / KEY_ENTRY)

            for path in object_files:
                shutil.copy2(path, staging / "objects" / path.name)

            counts = database_counts(snapshot)
            manifest = _write_manifest(staging, snapshot, staging / KEY_ENTRY, counts)

            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as zf:
                zf.write(staging / MANIFEST_NAME, MANIFEST_NAME)
                zf.write(snapshot, DATABASE_ENTRY)
                if (staging / KEY_ENTRY).is_file():
                    zf.write(staging / KEY_ENTRY, KEY_ENTRY)
                for entry in manifest["objects"]:
                    zf.write(staging / entry["path"], entry["path"])

            final_path = _unique_backup_path(backup_dir)
            metadata = encrypt_zip(zip_path, final_path, password)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        from .models import BackupRecord

        record = BackupRecord.objects.create(
            filename=final_path.name,
            size_bytes=int(metadata["size_bytes"]),
            sha256=str(metadata["sha256"]),
            format_version=FORMAT_VERSION,
            app_version=settings.APP_VERSION,
            created_by=user,
            note=(note or "")[:200],
        )
        logger.info(
            "backup_created file=%s size=%s", final_path.name, record.size_bytes
        )
        return BackupSummary(
            filename=record.filename,
            path=final_path,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            format_version=FORMAT_VERSION,
            app_version=settings.APP_VERSION,
            created_at=manifest["created_at"],
            counts=counts,
        )
    finally:
        _backup_lock.release()


def verify_backup_file(path: Path, password: str) -> dict:
    """Decrypt and fully verify a backup; returns its manifest."""

    password = validate_password(password)
    work = Path(settings.VAULT_TMP_DIR) / f"verify-{uuid.uuid4().hex}"
    work.mkdir(parents=True, exist_ok=False)
    try:
        zip_path = work / "backup.zip"
        decrypt_to_file(path, zip_path, password)
        manifest = inspect_backup_zip(zip_path)
        extracted = work / "extracted"
        extract_backup_zip(zip_path, manifest, extracted)
        counts = database_counts(extracted / DATABASE_ENTRY)
        if counts != manifest.get("counts"):
            raise BackupIntegrityError("备份中的数量与清单不一致。")
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prepare_restore(path: Path, password: str, work: Path) -> tuple[Path, dict]:
    """Decrypt, verify and extract a backup into ``work``."""

    work.mkdir(parents=True, exist_ok=False)
    zip_path = work / "backup.zip"
    decrypt_to_file(path, zip_path, password)
    manifest = inspect_backup_zip(zip_path)
    extracted = work / "extracted"
    extract_backup_zip(zip_path, manifest, extracted)
    return extracted, manifest


def now_iso() -> str:
    return django_timezone.now().isoformat()


def read_stream_digest(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size
