"""Master key management and AES-256-GCM envelope encryption.

Key hierarchy:

    master password -> Argon2id -> key-encryption key (KEK)
    KEK -> unwraps the random master key (memory only)
    master key -> unwraps each item's random data-encryption key (DEK)
    DEK -> encrypts the text payload or file blob

The master key file stores only the wrapped master key, the KDF salt/params and
the wrapping nonce. The master password is never written to disk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

MAGIC = b"EFV1"
FORMAT_VERSION = 1
NONCE_SIZE = 12
KEY_SIZE = 32
TAG_SIZE = 16
HEADER_SIZE = len(MAGIC) + 1 + NONCE_SIZE

MASTER_KEY_AAD = b"encrypted-file-vault-master-key-v1"
KEY_FILE_FORMAT = "encrypted-file-vault-master-key"

_state_lock = threading.RLock()
_master_key: bytes | None = None
_initialize_lock = threading.Lock()


class VaultError(Exception):
    """Base class for vault key/content errors."""


class VaultNotInitialized(VaultError):
    pass


class VaultAlreadyInitialized(VaultError):
    pass


class VaultLocked(VaultError):
    pass


class InvalidMasterPassword(VaultError):
    pass


class ContentIntegrityError(VaultError):
    pass


@dataclass(frozen=True)
class EncryptedText:
    wrapped_dek: bytes
    dek_nonce: bytes
    payload_nonce: bytes
    ciphertext: bytes
    plaintext_sha256: bytes
    plaintext_size: int


@dataclass(frozen=True)
class FileEncryptionResult:
    nonce: bytes
    plaintext_size: int
    ciphertext_size: int
    plaintext_sha256: bytes


@dataclass(frozen=True)
class EncryptedMetadata:
    ciphertext: bytes
    nonce: bytes


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str, field: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed key file is untrusted
        raise ContentIntegrityError(f"密钥文件字段 {field} 无效。") from exc


def _key_file() -> Path:
    return Path(settings.VAULT_KEY_FILE)


def _derive_kek(
    password: str,
    salt: bytes,
    time_cost: int,
    memory_cost: int,
    parallelism: int,
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


def _write_private_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass

    temporary = path.with_name(f"{path.name}.tmp-{secrets.token_hex(8)}")
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def is_initialized() -> bool:
    return _key_file().is_file()


def is_unlocked() -> bool:
    with _state_lock:
        return _master_key is not None


def require_master_key() -> bytes:
    with _state_lock:
        if _master_key is None:
            if not is_initialized():
                raise VaultNotInitialized("保险箱尚未初始化。")
            raise VaultLocked("保险箱尚未解锁。")
        return _master_key


def reset_state() -> None:
    """Clear the in-memory key. Used by tests and the lock endpoint."""

    global _master_key
    with _state_lock:
        _master_key = None


def lock() -> None:
    reset_state()


def initialize(password: str) -> None:
    """Create the master key file once and unlock it in memory."""

    global _master_key
    with _initialize_lock:
        with _state_lock:
            if _key_file().is_file():
                raise VaultAlreadyInitialized("保险箱已经初始化。")

            master_key = secrets.token_bytes(KEY_SIZE)
            salt = secrets.token_bytes(16)
            time_cost = int(getattr(settings, "VAULT_KDF_TIME_COST", 3))
            memory_cost = int(getattr(settings, "VAULT_KDF_MEMORY_COST", 65536))
            parallelism = int(getattr(settings, "VAULT_KDF_PARALLELISM", 4))
            kek = _derive_kek(
                password, salt, time_cost, memory_cost, parallelism
            )
            nonce = secrets.token_bytes(NONCE_SIZE)
            wrapped = AESGCM(kek).encrypt(nonce, master_key, MASTER_KEY_AAD)
            payload = {
                "format": KEY_FILE_FORMAT,
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "kdf": {
                    "name": "argon2id",
                    "salt": _b64encode(salt),
                    "time_cost": time_cost,
                    "memory_cost": memory_cost,
                    "parallelism": parallelism,
                    "hash_len": KEY_SIZE,
                },
                "cipher": {
                    "name": "AES-256-GCM",
                    "nonce": _b64encode(nonce),
                    "wrapped_key": _b64encode(wrapped),
                },
            }
            _write_private_file(_key_file(), payload)
            _master_key = master_key


def unlock(password: str) -> None:
    """Derive the KEK and unwrap the master key into memory."""

    global _master_key
    path = _key_file()
    if not path.is_file():
        raise VaultNotInitialized("保险箱尚未初始化。")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError("密钥文件无法读取或格式无效。") from exc

    if (
        payload.get("format") != KEY_FILE_FORMAT
        or int(payload.get("version", 0)) != 1
    ):
        raise ContentIntegrityError("密钥文件版本不受支持。")

    kdf = payload.get("kdf") or {}
    cipher = payload.get("cipher") or {}
    try:
        salt = _b64decode(kdf["salt"], "salt")
        nonce = _b64decode(cipher["nonce"], "nonce")
        wrapped = _b64decode(cipher["wrapped_key"], "wrapped_key")
    except KeyError as exc:
        raise ContentIntegrityError("密钥文件缺少必要字段。") from exc

    kek = _derive_kek(
        password,
        salt,
        kdf.get("time_cost", 3),
        kdf.get("memory_cost", 65536),
        kdf.get("parallelism", 4),
    )
    try:
        master_key = AESGCM(kek).decrypt(nonce, wrapped, MASTER_KEY_AAD)
    except InvalidTag as exc:
        raise InvalidMasterPassword("主密码不正确。") from exc

    with _state_lock:
        _master_key = master_key


def _aad(context: str, item_id: int) -> bytes:
    return f"vault-{context}-v1|{int(item_id)}".encode("ascii")


def wrap_dek(
    master_key: bytes, item_id: int, dek: bytes | None = None
) -> tuple[bytes, bytes, bytes]:
    key = dek if dek is not None else secrets.token_bytes(KEY_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    wrapped = AESGCM(master_key).encrypt(
        nonce, key, b"vault-dek-v1|" + str(int(item_id)).encode()
    )
    return wrapped, nonce, key


def unwrap_dek(
    master_key: bytes, wrapped: bytes, nonce: bytes, item_id: int
) -> bytes:
    try:
        return AESGCM(master_key).decrypt(
            nonce,
            bytes(wrapped),
            b"vault-dek-v1|" + str(int(item_id)).encode(),
        )
    except InvalidTag as exc:
        raise ContentIntegrityError("数据钥匙无法解开，内容可能已损坏。") from exc


def encrypt_text(
    master_key: bytes, item_id: int, payload: dict
) -> EncryptedText:
    plaintext = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    wrapped_dek, dek_nonce, dek = wrap_dek(master_key, item_id)
    payload_nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = AESGCM(dek).encrypt(
        payload_nonce, plaintext, _aad("text", item_id)
    )
    return EncryptedText(
        wrapped_dek=wrapped_dek,
        dek_nonce=dek_nonce,
        payload_nonce=payload_nonce,
        ciphertext=ciphertext,
        plaintext_sha256=hashlib.sha256(plaintext).digest(),
        plaintext_size=len(plaintext),
    )


def decrypt_text(
    master_key: bytes,
    item_id: int,
    wrapped_dek: bytes,
    dek_nonce: bytes,
    payload_nonce: bytes,
    ciphertext: bytes,
    plaintext_sha256: bytes,
) -> dict:
    dek = unwrap_dek(master_key, wrapped_dek, dek_nonce, item_id)
    try:
        plaintext = AESGCM(dek).decrypt(
            bytes(payload_nonce), bytes(ciphertext), _aad("text", item_id)
        )
    except InvalidTag as exc:
        raise ContentIntegrityError("文字内容完整性校验失败。") from exc
    if hashlib.sha256(plaintext).digest() != bytes(plaintext_sha256):
        raise ContentIntegrityError("文字内容校验值不一致。")
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError("文字内容格式无效。") from exc
    if not isinstance(payload, dict):
        raise ContentIntegrityError("文字内容格式无效。")
    return payload


def encrypt_metadata(
    item_id: int, dek: bytes, metadata: dict
) -> EncryptedMetadata:
    plaintext = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = AESGCM(dek).encrypt(
        nonce, plaintext, _aad("metadata", item_id)
    )
    return EncryptedMetadata(ciphertext=ciphertext, nonce=nonce)


def decrypt_metadata(
    item_id: int,
    dek: bytes,
    ciphertext: bytes,
    nonce: bytes,
) -> dict:
    try:
        plaintext = AESGCM(dek).decrypt(
            bytes(nonce), bytes(ciphertext), _aad("metadata", item_id)
        )
    except InvalidTag as exc:
        raise ContentIntegrityError("文件信息完整性校验失败。") from exc
    try:
        metadata = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError("文件信息格式无效。") from exc
    if not isinstance(metadata, dict):
        raise ContentIntegrityError("文件信息格式无效。")
    return metadata


class FileEncryptor:
    """Incremental file encryptor writing the EFV1 blob format.

    The caller creates one per upload. Only the current plaintext chunk is held
    in memory. The final blob is ``magic | version | nonce | ciphertext | tag``.
    """

    def __init__(self, dek: bytes, item_id: int, destination: Path):
        self.destination = Path(destination)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self._handle: BinaryIO | None = self.destination.open("wb")
        self.nonce = secrets.token_bytes(NONCE_SIZE)
        self._encryptor = Cipher(
            algorithms.AES(dek), modes.GCM(self.nonce)
        ).encryptor()
        self._encryptor.authenticate_additional_data(_aad("file", item_id))
        self._handle.write(MAGIC + struct.pack(">B", FORMAT_VERSION) + self.nonce)
        self._sha = hashlib.sha256()
        self._plaintext_size = 0
        self._finalized = False

    def update(self, chunk: bytes) -> None:
        if self._finalized:
            raise VaultError("加密流已经结束。")
        if not chunk:
            return
        if self._handle is None:
            raise VaultError("加密输出已经关闭。")
        self._sha.update(chunk)
        self._plaintext_size += len(chunk)
        encrypted = self._encryptor.update(chunk)
        if encrypted:
            self._handle.write(encrypted)

    def finalize(self) -> FileEncryptionResult:
        if self._finalized:
            raise VaultError("加密流已经结束。")
        self._finalized = True
        if self._handle is None:
            raise VaultError("加密输出已经关闭。")
        tail = self._encryptor.finalize()
        if tail:
            self._handle.write(tail)
        self._handle.write(self._encryptor.tag)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._handle = None
        return FileEncryptionResult(
            nonce=self.nonce,
            plaintext_size=self._plaintext_size,
            ciphertext_size=self.destination.stat().st_size,
            plaintext_sha256=self._sha.digest(),
        )

    def abort(self) -> None:
        self._finalized = True
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
        try:
            self.destination.unlink(missing_ok=True)
        except OSError:
            pass


def encrypt_file(
    dek: bytes,
    item_id: int,
    source: BinaryIO,
    destination: Path,
    chunk_size: int,
) -> FileEncryptionResult:
    encryptor = FileEncryptor(dek, item_id, destination)
    try:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            encryptor.update(chunk)
        return encryptor.finalize()
    except Exception:
        encryptor.abort()
        raise


def _read_header_and_tag(handle: BinaryIO, path: Path) -> tuple[bytes, bytes, int]:
    size = path.stat().st_size
    if size < HEADER_SIZE + TAG_SIZE:
        raise ContentIntegrityError("密文文件过短或已损坏。")
    header = handle.read(HEADER_SIZE)
    if len(header) != HEADER_SIZE or header[:4] != MAGIC:
        raise ContentIntegrityError("密文文件格式无效。")
    version = header[4]
    if version != FORMAT_VERSION:
        raise ContentIntegrityError("密文文件版本不受支持。")
    nonce = header[5:]
    handle.seek(size - TAG_SIZE)
    tag = handle.read(TAG_SIZE)
    if len(tag) != TAG_SIZE:
        raise ContentIntegrityError("密文文件认证标签缺失。")
    handle.seek(HEADER_SIZE)
    return nonce, tag, size - HEADER_SIZE - TAG_SIZE


class FileDecryptor:
    """Incremental decryptor. Call ``verify`` before sending anything."""

    def __init__(self, path: Path, dek: bytes, item_id: int):
        self.path = Path(path)
        if not self.path.is_file():
            raise ContentIntegrityError("密文文件不存在。")
        self._handle = self.path.open("rb")
        self._nonce, tag, self._ciphertext_size = _read_header_and_tag(
            self._handle, self.path
        )
        self._decryptor = Cipher(
            algorithms.AES(dek), modes.GCM(self._nonce, tag)
        ).decryptor()
        self._decryptor.authenticate_additional_data(_aad("file", item_id))
        self._remaining = self._ciphertext_size
        self._sha = hashlib.sha256()
        self._plaintext_size = 0
        self._done = False

    def chunks(self, chunk_size: int) -> Iterator[bytes]:
        if self._done:
            return
        while self._remaining > 0:
            chunk = self._handle.read(min(chunk_size, self._remaining))
            if not chunk:
                self._handle.close()
                raise ContentIntegrityError("密文文件被截断。")
            self._remaining -= len(chunk)
            plaintext = self._decryptor.update(chunk)
            if plaintext:
                self._sha.update(plaintext)
                self._plaintext_size += len(plaintext)
                yield plaintext
        try:
            tail = self._decryptor.finalize()
        except InvalidTag as exc:
            self._handle.close()
            raise ContentIntegrityError("文件内容完整性校验失败。") from exc
        if tail:
            self._sha.update(tail)
            self._plaintext_size += len(tail)
            yield tail
        self._done = True
        self._handle.close()

    def verify(self, chunk_size: int, expected_sha256: bytes) -> int:
        for _ in self.chunks(chunk_size):
            pass
        if self._sha.digest() != bytes(expected_sha256):
            raise ContentIntegrityError("文件内容校验值不一致。")
        return self._plaintext_size

    def close(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass


def read_file_plaintext(
    path: Path,
    dek: bytes,
    item_id: int,
    expected_sha256: bytes,
    chunk_size: int,
) -> bytes:
    decryptor = FileDecryptor(path, dek, item_id)
    data = b"".join(decryptor.chunks(chunk_size))
    if hashlib.sha256(data).digest() != bytes(expected_sha256):
        raise ContentIntegrityError("文件内容校验值不一致。")
    return data
