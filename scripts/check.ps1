# Run the Stage 1 automated checks.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Backend environment not found. Run scripts/setup-dev.ps1 first."
}

Write-Host "== Backend tests =="
Push-Location (Join-Path $Root "backend")
try {
    & $Python -m pytest
    & $Python -m ruff check .
}
finally {
    Pop-Location
}

Write-Host "== Frontend checks =="
Push-Location (Join-Path $Root "frontend")
try {
    npm run build
    npm run lint
}
finally {
    Pop-Location
}

Write-Host "All checks completed."
