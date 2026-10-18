# Start the backend and frontend in two PowerShell windows.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $Python)) {
    throw "Backend environment not found. Run scripts/setup-dev.ps1 first."
}
if (-not (Test-Path $EnvFile)) {
    throw "Missing .env. Run scripts/setup-dev.ps1 first."
}

$BackendCommand = "Set-Location '$Root\backend'; & '$Python' manage.py runserver 127.0.0.1:8000"
$FrontendCommand = "Set-Location '$Root\frontend'; npm run dev"

Write-Host "Starting backend on  http://127.0.0.1:8000"
Write-Host "Starting frontend on http://127.0.0.1:5173"
Write-Host "Close the two opened windows to stop the servers."

Start-Process powershell -ArgumentList @("-NoLogo", "-NoExit", "-Command", $BackendCommand)
Start-Process powershell -ArgumentList @("-NoLogo", "-NoExit", "-Command", $FrontendCommand)
