"""Custom Django upload handler that encrypts file data while it arrives.

Django's default temporary-file handler would write plaintext uploads to disk.
This handler receives each multipart chunk, encrypts it immediately and writes
only ciphertext to a temporary blob. The view then moves that blob into the
object store after the database record is ready.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler

from . import crypto


@dataclass
class EncryptedUpload:
    """Small value object returned by the upload handler to the view."""

    name: str
    content_type: str
    temp_path: Path
    plaintext_size: int
    ciphertext_size: int
    plaintext_sha256: bytes
    nonce: bytes
    field_name: str = ""
    charset: str | None = None
    content_type_extra: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        return self.plaintext_size


class VaultEncryptingUploadHandler(FileUploadHandler):
    def __init__(
        self,
        request=None,
        *,
        item_id: int,
        dek: bytes,
        max_size: int,
    ):
        super().__init__(request)
        self.item_id = item_id
        self.dek = dek
        self.max_size = max(0, int(max_size))
        self._encryptor: crypto.FileEncryptor | None = None
        self._upload: EncryptedUpload | None = None
        self._plaintext_size = 0

    def new_file(
        self,
        field_name,
        file_name,
        content_type,
        content_length,
        charset=None,
        content_type_extra=None,
    ):
        super().new_file(
            field_name,
            file_name,
            content_type,
            content_length,
            charset,
            content_type_extra,
        )
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except (TypeError, ValueError):
                declared_size = 0
            if declared_size > self.max_size:
                raise RequestDataTooBig("上传文件超过大小上限。")

        temp_dir = Path(settings.VAULT_TMP_DIR)
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"upload-{secrets.token_hex(16)}.vault"
        self._encryptor = crypto.FileEncryptor(self.dek, self.item_id, temp_path)
        self._plaintext_size = 0

    def receive_data_chunk(self, raw_data, start):
        if self._encryptor is None:
            raise RequestDataTooBig("没有可用的加密上传流。")
        if self._plaintext_size + len(raw_data) > self.max_size:
            self.cleanup()
            raise RequestDataTooBig("上传文件超过大小上限。")
        self._encryptor.update(raw_data)
        self._plaintext_size += len(raw_data)
        return None

    def file_complete(self, file_size):
        if self._encryptor is None:
            return None
        if int(file_size) > self.max_size:
            self.cleanup()
            raise RequestDataTooBig("上传文件超过大小上限。")
        try:
            result = self._encryptor.finalize()
        except Exception:
            self.cleanup()
            raise
        self._upload = EncryptedUpload(
            name=self.file_name or "download",
            content_type=self.content_type or "application/octet-stream",
            temp_path=self._encryptor.destination,
            plaintext_size=result.plaintext_size,
            ciphertext_size=result.ciphertext_size,
            plaintext_sha256=result.plaintext_sha256,
            nonce=result.nonce,
            field_name=self.field_name or "",
            charset=self.charset,
            content_type_extra=self.content_type_extra or {},
        )
        self._encryptor = None
        return self._upload

    def cleanup(self) -> None:
        if self._encryptor is not None:
            self._encryptor.abort()
            self._encryptor = None
        if self._upload is not None:
            try:
                self._upload.temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._upload = None
