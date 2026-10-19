# Start the local server and serve the built web application.
# Use this for normal browser use and for the desktop client.
#   powershell -ExecutionPolicy Bypass -File scripts/start.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -SkipBuild
param(
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"
$Frontend = Join-Path $Root "frontend"
$Dist = Join-Path $Frontend "dist"

if (-not (Test-Path $Python)) {
    throw "Backend environment not found. Run scripts/setup-dev.ps1 first."
}
if (-not (Test-Path $EnvFile)) {
    throw "Missing .env. Run scripts/setup-dev.ps1 first."
}

if (-not $SkipBuild -or -not (Test-Path (Join-Path $Dist "index.html"))) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js LTS and try again."
    }
    Write-Host "Building the web application..."
    Push-Location $Frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

$env:DJANGO_DEBUG = "false"

Write-Host ""
Write-Host "Server is starting on http://127.0.0.1:8000"
Write-Host "Browser and desktop client both use this address."
Write-Host "Press Ctrl+C or close this window to stop the server."
Write-Host ""

Set-Location (Join-Path $Root "backend")
& $Python manage.py runserver 127.0.0.1:8000 --noreload
