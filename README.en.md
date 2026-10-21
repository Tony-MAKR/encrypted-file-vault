# Encrypted File Vault

**In one line:** A self-hosted encrypted file and secrets manager for Windows with group- and user-level access control.

A self-hosted, local-first encrypted file and secrets manager for Windows. Admins can store files and text secrets (website or database passwords) encrypted at rest, then grant access to groups or individual users. Only authorized users can view or download decrypted content.

> **Status: v1.0.0 is published on GitHub: https://github.com/Tony-MAKR/encrypted-file-vault. The project currently targets Windows 10/11 and listens on `127.0.0.1` only. Do not expose it to a LAN or the public internet without HTTPS and an explicit deployment decision.**

[中文 README](README.md)

## Features

- First-run setup, login, logout, password change, lockout and session timeouts.
- Admin and standard-user roles; user creation, disable/enable, role changes and temporary password reset.
- User groups, group membership, group grants and per-user grants; revocation takes effect immediately.
- Encrypted text secrets and file entries.
- Master-password initialization, unlock and lock; the vault locks again after a server restart.
- File uploads are encrypted while being received; no plaintext temporary file is written.
- Categories, tags, search, filters, dashboard statistics and a password generator.
- Archive/restore, owner transfer, 30-day recycle bin and permanent deletion.
- Queryable audit log for authentication, accounts, groups, grants, items, content access and backups.
- Encrypted backup packages (database, ciphertext, wrapped master key and manifest) with an independent backup passphrase, plus verification.
- Command-line restore with validation, explicit confirmation, an automatic pre-restore copy and rollback on failure.
- Audit retention cleanup and a read-only deployment security check.
- Windows desktop client (Electron), NSIS installer, portable ZIP and SHA-256 checksums.
- Django serves the built web application; browser and desktop client use the same address.

## Requirements

- Windows 10/11 x64
- Python 3.12+ (developed on 3.14)
- Node.js LTS and npm (developed on Node 24)
- Git (optional)

## Quick start

```powershell
# Install Python and frontend dependencies, create .env, migrate the database
powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1

# Build the web app and start the server at http://127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Open `http://127.0.0.1:8000/`. On a fresh database, the first page creates the first administrator.

For development with Vite hot reload:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

The backend runs on `http://127.0.0.1:8000`; the Vite dev server runs on `http://127.0.0.1:5173`.

## Desktop client

Build the installer and portable archive:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

Output is written to `desktop/release/`:

- `EncryptedFileVault-Setup-<version>-x64.exe`
- `EncryptedFileVault-Portable-<version>-x64.zip`
- `SHA256SUMS.txt`
- `INSTALL.txt`

The installer is **not code-signed**. Windows SmartScreen may show an “Unknown publisher” warning. Verify the SHA-256 value before running it.

The desktop client is only a shell. It does not copy the database, encryption keys or ciphertext to client machines, and it does not store login passwords, master passwords or keys. Uninstalling the client does not delete server data.

## Security model and limitations

- Server-side envelope encryption: Argon2id derives a key-encryption key from the master password; a random master key is kept in memory only; every item has its own AES-256-GCM data key.
- The master password is never stored. If it is lost, encrypted content cannot be recovered.
- Metadata (titles, descriptions, categories, tags) is stored in plaintext for search and management. Do not put secrets in those fields.
- Authorized users can photograph, save or forward decrypted content. The system reduces risk through authorization, download control and auditing; it cannot prevent this absolutely.
- The first release is **server-side encryption**. A malicious administrator with full control of the server can theoretically decrypt content. End-to-end encryption is reserved for a future architecture.
- Backup passphrases are never stored. Losing a backup passphrase makes that backup unreadable; the master password is still required to decrypt restored content.
- HTTPS, LAN deployment and code signing are not configured in this release. Do not change the listening address to `0.0.0.0` or expose the server publicly.
- Encryption does not replace operating-system updates, antivirus, BitLocker or offline backups.

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Testing

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

This runs backend pytest and Ruff, the frontend build and Oxlint, and desktop unit tests.

Browser end-to-end tests (Windows, Microsoft Edge installed):

```powershell
cd e2e
npm ci
npm test
```

See [docs/testing.md](docs/testing.md) for the full test plan and manual acceptance checklist.

## Documentation

- [Project charter and requirements (Chinese)](docs/00-project-charter.md)
- [Feasibility study (Chinese)](docs/01-feasibility-study.md)
- [Requirements analysis (Chinese)](docs/02-requirements-analysis.md)
- [Testing guide (Chinese)](docs/testing.md)
- [Release process (Chinese)](docs/releasing.md)
- Stage specifications: [01](docs/specs/01-project-foundation.md) · [02](docs/specs/02-accounts-and-roles.md) · [03](docs/specs/03-groups-and-authorization.md) · [04](docs/specs/04-encryption-engine.md) · [05](docs/specs/05-web-features.md) · [06](docs/specs/06-desktop-client.md) · [07](docs/specs/07-audit-backup-hardening.md) · [08](docs/specs/08-testing-and-release.md)

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before opening a pull request.

Do not include real passwords, keys, customer data or production backups in issues, pull requests, tests or examples.

## License

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party component attribution.

Copyright 2026 Encrypted File Vault contributors.
