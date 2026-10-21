# Local development setup for Windows.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root "backend\.venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Requirements = Join-Path $Root "backend\requirements-dev.txt"
$ManagePy = Join-Path $Root "backend\manage.py"
$InitEnv = Join-Path $Root "scripts\init_env.py"
$Frontend = Join-Path $Root "frontend"

Write-Host "== Encrypted File Vault - setup =="

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python 3.12+ and try again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found. Install Node.js LTS and try again."
}

Set-Location $Root

if (-not (Test-Path $Python)) {
    Write-Host "Creating backend virtual environment..."
    python -m venv $Venv
}

Write-Host "Installing backend dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r $Requirements

Write-Host "Creating local .env if needed..."
& python $InitEnv

Write-Host "Applying database migrations..."
& $Python $ManagePy migrate --noinput

Write-Host "Installing frontend dependencies..."
Push-Location $Frontend
try {
    npm install
}
finally {
    Pop-Location
}

$Desktop = Join-Path $Root "desktop"
if (Test-Path (Join-Path $Desktop "package.json")) {
    Write-Host "Installing desktop client dependencies..."
    Push-Location $Desktop
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

$E2E = Join-Path $Root "e2e"
if (Test-Path (Join-Path $E2E "package.json")) {
    Write-Host "Installing browser test dependencies..."
    Push-Location $E2E
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Development: powershell -ExecutionPolicy Bypass -File scripts/dev.ps1"
Write-Host "Normal use:  powershell -ExecutionPolicy Bypass -File scripts/start.ps1"
Write-Host "Desktop:     powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1"
Write-Host "Backend:  http://127.0.0.1:8000/api/v1/health/"
Write-Host "Frontend: http://127.0.0.1:5173 (development only)"
