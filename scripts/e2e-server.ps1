# Start an isolated server for Playwright tests.
# The data directory must be empty and under the system temp directory.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    # CI installs Python into the runner's PATH instead of a project venv.
    $Python = "python"
}
$DataDir = $env:VAULT_E2E_DATA_DIR
$Port = 8020
if (-not $DataDir) {
    throw "VAULT_E2E_DATA_DIR is not set."
}

$Resolved = [System.IO.Path]::GetFullPath($DataDir)
$TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $Resolved.StartsWith($TempRoot)) {
    throw "E2E data directory must be under the system temp directory."
}

$FrontendIndex = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $FrontendIndex)) {
    throw "Frontend build not found. Run npm run build in frontend first."
}

if (Test-Path $Resolved) {
    Remove-Item -Path $Resolved -Recurse -Force
}
New-Item -ItemType Directory -Path $Resolved -Force | Out-Null
$env:DATA_DIR = $Resolved
$env:DJANGO_DEBUG = "false"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
$env:FRONTEND_DIST_DIR = Join-Path $Root "frontend\dist"

Push-Location (Join-Path $Root "backend")
try {
    & $Python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }
    & $Python manage.py runserver "127.0.0.1:$Port" --noreload
}
finally {
    Pop-Location
}
