"""Stage 7: encrypted backup creation, verification and restore helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import namedtuple
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit import backup as backup_service
from apps.audit.management.commands import restore_backup
from apps.audit.models import AuditEvent, BackupRecord

BACKUP_PASSWORD = "Stage7-Backup-Passphrase-2026!"


def _fake_vault(settings) -> tuple[Path, Path]:
    key_path = Path(settings.VAULT_KEY_FILE)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text('{"wrapped": "not-a-real-key"}', encoding="utf-8")

    objects = Path(settings.VAULT_OBJECTS_DIR)
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "aaaa.vault").write_bytes(b"EFV1-first-ciphertext")
    (objects / "bbbb.vault").write_bytes(b"EFV1-second-ciphertext")
    return key_path, objects


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.django_db
def test_backup_is_encrypted_and_complete(admin_user, settings):
    _fake_vault(settings)

    summary = backup_service.create_backup(
        BACKUP_PASSWORD, note="测试备份", user=admin_user
    )

    assert summary.path.is_file()
    raw = summary.path.read_bytes()
    assert raw.startswith(backup_service.MAGIC)
    assert b"manifest.json" not in raw
    assert b"master.key.json" not in raw
    assert b"SQLite format 3" not in raw

    backup_record = BackupRecord.objects.get(filename=summary.filename)
    assert backup_record.created_by == admin_user
    assert backup_record.size_bytes == summary.path.stat().st_size
    assert backup_record.sha256 == summary.sha256

    manifest = backup_service.verify_backup_file(summary.path, BACKUP_PASSWORD)
    assert manifest["format"] == backup_service.BACKUP_FORMAT_NAME
    assert manifest["master_key"] is not None
    assert len(manifest["objects"]) == 2
    assert manifest["counts"]["users"] >= 1


@pytest.mark.django_db
def test_backup_wrong_password_and_tampering_are_rejected(admin_user, settings):
    _fake_vault(settings)
    summary = backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)

    with pytest.raises(backup_service.BackupPasswordError):
        backup_service.verify_backup_file(summary.path, "Wrong-Passphrase-2026!")

    raw = bytearray(summary.path.read_bytes())
    raw[-20] ^= 0x01
    summary.path.write_bytes(raw)

    with pytest.raises(backup_service.BackupError):
        backup_service.verify_backup_file(summary.path, BACKUP_PASSWORD)


@pytest.mark.django_db
def test_backup_rejects_short_password(admin_user, settings):
    _fake_vault(settings)
    with pytest.raises(backup_service.BackupError):
        backup_service.create_backup("short", user=admin_user)


@pytest.mark.django_db
def test_backup_rejects_insufficient_space(admin_user, settings, monkeypatch):
    _fake_vault(settings)
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(
        backup_service.shutil,
        "disk_usage",
        lambda _path: Usage(total=10**12, used=10**12, free=1024),
    )

    with pytest.raises(backup_service.BackupSpaceError):
        backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)


@pytest.mark.django_db
def test_backup_rejects_concurrent_jobs(admin_user, settings):
    _fake_vault(settings)
    assert backup_service._backup_lock.acquire(blocking=False)
    try:
        with pytest.raises(backup_service.BackupBusy):
            backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)
    finally:
        backup_service._backup_lock.release()


@pytest.mark.django_db
def test_backup_api_create_list_and_verify(admin_client, settings):
    _fake_vault(settings)

    created = admin_client.post(
        "/api/v1/admin/backups/",
        {
            "passphrase": BACKUP_PASSWORD,
            "passphrase_confirm": BACKUP_PASSWORD,
            "note": "接口创建",
        },
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    payload = created.json()
    assert payload["sha256"]
    assert payload["backup"]["status"] == "created"

    listing = admin_client.get("/api/v1/admin/backups/")
    assert listing.status_code == 200
    data = listing.json()
    assert data["count"] == 1
    assert data["summary"]["last_backup_at"]
    assert data["summary"]["reminder_due"] is False

    verify = admin_client.post(
        f"/api/v1/admin/backups/{payload['backup']['id']}/verify/",
        {"passphrase": BACKUP_PASSWORD},
        content_type="application/json",
    )
    assert verify.status_code == 200, verify.content
    assert verify.json()["detail"] == "备份验证通过。"
    record = BackupRecord.objects.get(pk=payload["backup"]["id"])
    assert record.status == BackupRecord.Status.VERIFIED
    assert record.verified_at is not None
    audited = json.dumps(
        list(AuditEvent.objects.values("action", "detail", "target_label")),
        ensure_ascii=False,
    )
    assert "backup_created" in audited
    assert "backup_verified" in audited
    assert BACKUP_PASSWORD not in audited

    wrong = admin_client.post(
        f"/api/v1/admin/backups/{payload['backup']['id']}/verify/",
        {"passphrase": "Wrong-Passphrase-2026!"},
        content_type="application/json",
    )
    assert wrong.status_code == 400
    record.refresh_from_db()
    assert record.status == BackupRecord.Status.FAILED


@pytest.mark.django_db
def test_backup_api_requires_admin(user_client, settings):
    _fake_vault(settings)
    assert user_client.get("/api/v1/admin/backups/").status_code == 404
    assert (
        user_client.post(
            "/api/v1/admin/backups/",
            {
                "passphrase": BACKUP_PASSWORD,
                "passphrase_confirm": BACKUP_PASSWORD,
            },
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_backup_verify_missing_file_returns_404(admin_client, settings):
    _fake_vault(settings)
    created = admin_client.post(
        "/api/v1/admin/backups/",
        {
            "passphrase": BACKUP_PASSWORD,
            "passphrase_confirm": BACKUP_PASSWORD,
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    record = BackupRecord.objects.get(pk=created.json()["backup"]["id"])
    (Path(settings.BACKUP_DIR) / record.filename).unlink()

    response = admin_client.post(
        f"/api/v1/admin/backups/{record.pk}/verify/",
        {"passphrase": BACKUP_PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_prepare_restore_extracts_verified_files(admin_user, settings, tmp_path):
    _fake_vault(settings)
    summary = backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)

    work = Path(settings.VAULT_TMP_DIR) / "restore-test"
    extracted, manifest = backup_service.prepare_restore(
        summary.path, BACKUP_PASSWORD, work
    )

    assert (extracted / backup_service.DATABASE_ENTRY).is_file()
    assert (extracted / backup_service.KEY_ENTRY).is_file()
    assert len(list((extracted / "objects").glob("*.vault"))) == 2
    assert manifest["counts"]["users"] >= 1


@pytest.mark.django_db
def test_restore_command_applies_and_keeps_safety_copy(
    admin_user, settings, monkeypatch, tmp_path
):
    _fake_vault(settings)
    summary = backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)

    work = Path(settings.VAULT_TMP_DIR) / "restore-command-source"
    extracted, _manifest = backup_service.prepare_restore(
        summary.path, BACKUP_PASSWORD, work
    )
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_db = live_dir / "db.sqlite3"
    live_db.write_bytes((extracted / backup_service.DATABASE_ENTRY).read_bytes())
    marker = sqlite3.connect(live_db)
    try:
        marker.execute("CREATE TABLE before_marker (value TEXT)")
        marker.execute("INSERT INTO before_marker VALUES ('old-data')")
        marker.commit()
    finally:
        marker.close()
    before_hash = _file_hash(live_db)
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", str(live_db))
    monkeypatch.setenv("VAULT_BACKUP_PASSWORD", BACKUP_PASSWORD)

    call_command(
        "restore_backup",
        str(summary.path),
        "--yes",
        "--skip-port-check",
        verbosity=0,
    )

    assert live_db.is_file()
    connection = sqlite3.connect(f"file:{live_db.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM accounts_user").fetchone()[0] >= 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='before_marker'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()

    safety_dirs = list(Path(settings.BACKUP_DIR).glob("pre-restore-*"))
    assert len(safety_dirs) == 1
    assert (safety_dirs[0] / "db.sqlite3").is_file()
    assert _file_hash(safety_dirs[0] / "db.sqlite3") == before_hash
    safety_copy = sqlite3.connect(safety_dirs[0] / "db.sqlite3")
    try:
        assert safety_copy.execute(
            "SELECT COUNT(*) FROM before_marker"
        ).fetchone()[0] == 1
    finally:
        safety_copy.close()


@pytest.mark.django_db
def test_restore_rejects_app_version_mismatch(
    settings, monkeypatch, tmp_path
):
    backup_file = tmp_path / "fake.efbak"
    backup_file.write_bytes(b"not-needed")
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    manifest = {
        "app_version": "0.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "counts": {},
        "objects": [],
        "master_key": None,
    }
    monkeypatch.setattr(
        backup_service,
        "prepare_restore",
        lambda *_args, **_kwargs: (extracted, manifest),
    )
    monkeypatch.setenv("VAULT_BACKUP_PASSWORD", BACKUP_PASSWORD)

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "restore_backup",
            str(backup_file),
            "--yes",
            "--skip-port-check",
            verbosity=0,
        )

    assert "allow-version-mismatch" in str(exc_info.value)


@pytest.mark.django_db
def test_restore_rollback_restores_previous_data(
    admin_user, settings, monkeypatch, tmp_path
):
    _fake_vault(settings)
    summary = backup_service.create_backup(BACKUP_PASSWORD, user=admin_user)

    work = Path(settings.VAULT_TMP_DIR) / "restore-rollback"
    extracted, manifest = backup_service.prepare_restore(
        summary.path, BACKUP_PASSWORD, work
    )

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_db = live_dir / "db.sqlite3"
    live_db.write_bytes((extracted / backup_service.DATABASE_ENTRY).read_bytes())
    marker = sqlite3.connect(live_db)
    try:
        marker.execute("CREATE TABLE before_marker (value TEXT)")
        marker.execute("INSERT INTO before_marker VALUES ('old-data')")
        marker.commit()
    finally:
        marker.close()
    before_hash = _file_hash(live_db)
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", str(live_db))

    safety, key_existed = restore_backup._safety_copy("rollback-test")
    restore_backup._apply_restore(extracted, manifest)
    assert _file_hash(live_db) != before_hash

    restore_backup._rollback(safety, key_existed)
    assert _file_hash(live_db) == before_hash


def test_backup_file_names_and_passphrase_are_not_in_package(settings, tmp_path):
    # A pure format test: the header and encrypted chunks never contain the
    # ZIP entry names in plaintext.
    source = tmp_path / "source.zip"
    source.write_bytes(b"PK\x03\x04manifest.json-and-master.key.json")
    target = tmp_path / "output.efbak"
    backup_service.encrypt_zip(source, target, BACKUP_PASSWORD)

    raw = target.read_bytes()
    assert b"manifest.json" not in raw
    assert b"master.key.json" not in raw
    assert raw[:4] == backup_service.MAGIC
