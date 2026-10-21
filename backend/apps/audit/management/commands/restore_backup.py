"""Restore an encrypted backup while the server is stopped.

Safety rules enforced here:

* the server must not be listening on the configured port;
* the passphrase is read from the environment or prompted, never logged;
* the package is fully decrypted and hash-verified before anything is replaced;
* the operator must type ``RESTORE`` unless ``--yes`` is used;
* current data is copied to ``data/backups/pre-restore-<time>/`` first;
* any failure during replacement rolls the previous data back.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import socket
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit import backup as backup_service

PASSWORD_ENV = "VAULT_BACKUP_PASSWORD"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except OSError:
        return False


def _copy_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".restoring")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def _safety_copy(stamp: str) -> tuple[Path, bool]:
    backup_dir = Path(settings.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    safety = backup_dir / f"pre-restore-{stamp}"
    counter = 1
    while safety.exists():
        safety = backup_dir / f"pre-restore-{stamp}-{counter}"
        counter += 1
    safety.mkdir(parents=True)

    database_path = Path(settings.DATABASES["default"]["NAME"])
    if database_path.is_file():
        shutil.copy2(database_path, safety / "db.sqlite3")

    key_path = Path(settings.VAULT_KEY_FILE)
    key_existed = key_path.is_file()
    if key_existed:
        shutil.copy2(key_path, safety / "master.key.json")

    objects_dir = Path(settings.VAULT_OBJECTS_DIR)
    objects_existed = objects_dir.is_dir()
    if objects_existed:
        shutil.copytree(objects_dir, safety / "objects")

    counts = {}
    if (safety / "db.sqlite3").is_file():
        try:
            counts = backup_service.database_counts(safety / "db.sqlite3")
        except backup_service.BackupError:
            counts = {}

    (safety / "meta.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(),
                "counts": counts,
                "key_existed": key_existed,
                "objects_existed": objects_existed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return safety, key_existed


def _apply_restore(extracted: Path, manifest: dict) -> None:
    restored_db = extracted / backup_service.DATABASE_ENTRY
    target_db = Path(settings.DATABASES["default"]["NAME"])
    _copy_database(restored_db, target_db)

    restored_key = extracted / backup_service.KEY_ENTRY
    target_key = Path(settings.VAULT_KEY_FILE)
    if manifest.get("master_key") is not None:
        if not restored_key.is_file():
            raise backup_service.BackupIntegrityError("备份中缺少主密钥文件。")
        target_key.parent.mkdir(parents=True, exist_ok=True)
        temporary_key = target_key.with_name(target_key.name + ".restoring")
        shutil.copy2(restored_key, temporary_key)
        os.replace(temporary_key, target_key)

    restored_objects = extracted / "objects"
    target_objects = Path(settings.VAULT_OBJECTS_DIR)
    new_objects = target_objects.with_name(target_objects.name + ".restoring")
    if new_objects.exists():
        shutil.rmtree(new_objects)
    if restored_objects.is_dir():
        shutil.copytree(restored_objects, new_objects)
    else:
        new_objects.mkdir(parents=True)
    if target_objects.exists():
        shutil.rmtree(target_objects)
    os.replace(new_objects, target_objects)


def _rollback(safety: Path, key_existed: bool) -> None:
    database = safety / "db.sqlite3"
    if database.is_file():
        _copy_database(database, Path(settings.DATABASES["default"]["NAME"]))

    key_path = Path(settings.VAULT_KEY_FILE)
    safety_key = safety / "master.key.json"
    if safety_key.is_file():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safety_key, key_path)
    elif not key_existed:
        key_path.unlink(missing_ok=True)

    objects_dir = Path(settings.VAULT_OBJECTS_DIR)
    safety_objects = safety / "objects"
    if objects_dir.exists():
        shutil.rmtree(objects_dir)
    if safety_objects.is_dir():
        shutil.copytree(safety_objects, objects_dir)
    else:
        objects_dir.mkdir(parents=True, exist_ok=True)


class Command(BaseCommand):
    help = "从加密备份包恢复数据（必须先停止服务器）。"

    def add_arguments(self, parser):
        parser.add_argument("backup", help=".efbak 备份文件路径")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="跳过输入 RESTORE 的确认（仅用于受控测试）。",
        )
        parser.add_argument(
            "--allow-version-mismatch",
            action="store_true",
            help="允许应用版本不同但格式版本一致的备份。",
        )
        parser.add_argument(
            "--skip-port-check",
            action="store_true",
            help="跳过服务器端口检查（仅用于测试）。",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="检查服务器是否仍在监听的端口，默认 8000。",
        )
        parser.add_argument(
            "--keep-work",
            action="store_true",
            help="保留解密后的临时目录，便于排查（默认删除）。",
        )

    def handle(self, *args, **options):
        backup_path = Path(options["backup"]).expanduser()
        if not backup_path.is_absolute():
            backup_path = (Path.cwd() / backup_path).resolve()
        if not backup_path.is_file():
            raise CommandError(f"找不到备份文件：{backup_path}")

        if not options["skip_port_check"] and _port_open(options["port"]):
            raise CommandError(
                "服务器仍在运行。请先关闭服务器窗口，确认端口 "
                f"{options['port']} 没有监听后再恢复。"
            )

        password = os.environ.get(PASSWORD_ENV)
        if not password:
            password = getpass.getpass("请输入备份口令（不会显示）：")
        if not password:
            raise CommandError("没有输入备份口令，已取消。")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        work = Path(settings.VAULT_TMP_DIR) / f"restore-{stamp}-{uuid.uuid4().hex}"

        try:
            try:
                extracted, manifest = backup_service.prepare_restore(
                    backup_path, password, work
                )
            except backup_service.BackupError as exc:
                raise CommandError(str(exc)) from exc

            if (
                str(manifest.get("app_version", "")) != settings.APP_VERSION
                and not options["allow_version_mismatch"]
            ):
                raise CommandError(
                    "备份的应用版本是 "
                    f"{manifest.get('app_version', '未知')}，当前是 "
                    f"{settings.APP_VERSION}。确认兼容后可加 "
                    "--allow-version-mismatch 再试。"
                )

            counts = manifest.get("counts", {})
            self.stdout.write("备份校验通过：")
            self.stdout.write(f"  创建时间：{manifest.get('created_at', '未知')}")
            self.stdout.write(f"  应用版本：{manifest.get('app_version', '未知')}")
            self.stdout.write(
                "  账号 / 用户组 / 条目 / 加密内容："
                f"{counts.get('users', 0)} / {counts.get('groups', 0)} / "
                f"{counts.get('items', 0)} / {counts.get('contents', 0)}"
            )
            self.stdout.write(
                f"  密文文件：{len(manifest.get('objects', []))} 个"
            )

            if not options["yes"]:
                answer = input(
                    "恢复会覆盖当前数据库、密文和主密钥文件。"
                    "当前数据会先保存到 pre-restore 目录。\n"
                    "确认请输入 RESTORE："
                ).strip()
                if answer != "RESTORE":
                    raise CommandError("输入不匹配，已取消恢复，当前数据没有变化。")

            safety, key_existed = _safety_copy(stamp)
            self.stdout.write(f"当前数据已保存到：{safety}")

            try:
                _apply_restore(extracted, manifest)
            except Exception as exc:  # noqa: BLE001 - rollback then re-raise
                self.stderr.write("恢复过程中出错，正在回滚……")
                _rollback(safety, key_existed)
                raise CommandError(
                    f"恢复失败，已回滚到恢复前的数据：{exc}"
                ) from exc

            self._write_restore_audit(backup_path, manifest, safety)
            self.stdout.write(
                self.style.SUCCESS(
                    "恢复完成。保险箱处于锁定状态；请启动服务器，"
                    "用备份中的账号登录并重新输入主密码。"
                )
            )
            self.stdout.write(
                "确认数据无误后，可自行清理 pre-restore 目录；系统不会自动删除。"
            )
        finally:
            if not options["keep_work"]:
                shutil.rmtree(work, ignore_errors=True)

    def _write_restore_audit(
        self, backup_path: Path, manifest: dict, safety: Path
    ) -> None:
        try:
            # Import after the database has been replaced so the event lands
            # in the restored database.
            from apps.audit.models import AuditEvent

            AuditEvent.objects.create(
                actor=None,
                actor_username="system",
                actor_role="",
                action="backup_restored",
                target_type="backup",
                target_label=backup_path.name[:200],
                result=AuditEvent.Result.SUCCESS,
                detail={
                    "backup_created_at": manifest.get("created_at"),
                    "backup_app_version": manifest.get("app_version"),
                    "counts": manifest.get("counts", {}),
                    "safety_copy": safety.name,
                },
            )
        except Exception as exc:  # noqa: BLE001 - restore already succeeded
            self.stderr.write(
                "提示：恢复成功，但写入审计记录失败："
                f"{exc.__class__.__name__}。请查看服务器日志。"
            )
