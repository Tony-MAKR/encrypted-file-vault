# Run the automated checks.
# Add -IncludeE2E to also run Playwright browser tests (requires Edge and built frontend).
param(
    [switch]$IncludeE2E
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"

function Assert-Success([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path $Python)) {
    throw "Backend environment not found. Run scripts/setup-dev.ps1 first."
}

Write-Host "== Backend tests =="
Push-Location (Join-Path $Root "backend")
try {
    & $Python -m pytest
    Assert-Success "Backend tests"
    & $Python -m ruff check .
    Assert-Success "Ruff"
}
finally {
    Pop-Location
}

Write-Host "== Frontend checks =="
Push-Location (Join-Path $Root "frontend")
try {
    npm run build
    Assert-Success "Frontend build"
    npm run lint
    Assert-Success "Oxlint"
}
finally {
    Pop-Location
}

Write-Host "== Desktop checks =="
$Desktop = Join-Path $Root "desktop"
if (Test-Path (Join-Path $Desktop "node_modules")) {
    Push-Location $Desktop
    try {
        npm test
        Assert-Success "Desktop tests"
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Desktop dependencies are not installed; run scripts/build-desktop.ps1 to install and package."
}

if ($IncludeE2E) {
    Write-Host "== Browser end-to-end checks =="
    $E2E = Join-Path $Root "e2e"
    if (-not (Test-Path (Join-Path $E2E "node_modules"))) {
        throw "E2E dependencies are not installed. Run npm install in e2e first."
    }
    Push-Location $E2E
    try {
        npm test
        Assert-Success "Browser tests"
    }
    finally {
        Pop-Location
    }
}

Write-Host "All checks completed."
