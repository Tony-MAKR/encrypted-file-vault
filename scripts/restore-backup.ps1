# Restore an encrypted .efbak backup. Stop the server first.
#   powershell -ExecutionPolicy Bypass -File scripts/restore-backup.ps1 -File "data\backups\vault-backup-....efbak"
# The backup passphrase is asked interactively and is never stored.
param(
    [Parameter(Mandatory = $true)]
    [string]$File,
    [switch]$Yes,
    [switch]$AllowVersionMismatch,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$Backend = Join-Path $Root "backend"

if (-not (Test-Path $Python)) {
    throw "Backend environment not found. Run scripts/setup-dev.ps1 first."
}

$BackupPath = $File
if (-not [System.IO.Path]::IsPathRooted($BackupPath)) {
    $BackupPath = Join-Path $Root $BackupPath
}
if (-not (Test-Path $BackupPath)) {
    throw "Backup file not found: $BackupPath"
}

$Arguments = @("manage.py", "restore_backup", $BackupPath, "--port", "$Port")
if ($Yes) {
    $Arguments += "--yes"
}
if ($AllowVersionMismatch) {
    $Arguments += "--allow-version-mismatch"
}

Write-Host "Restoring from: $BackupPath"
Write-Host "Make sure the server window is closed."
Write-Host ""

Push-Location $Backend
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Restore failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
