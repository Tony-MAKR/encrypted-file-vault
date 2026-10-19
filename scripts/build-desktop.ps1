# Build the Windows desktop installer and portable archive.
#   powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Desktop = Join-Path $Root "desktop"
$Release = Join-Path $Desktop "release"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found. Install Node.js LTS and try again."
}
if (-not (Test-Path (Join-Path $Desktop "package.json"))) {
    throw "Desktop project not found."
}

Write-Host "== Build the web application =="
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

$buildStarted = Get-Date
Push-Location $Desktop
try {
    if (-not (Test-Path (Join-Path $Desktop "node_modules"))) {
        Write-Host "== Install desktop dependencies =="
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "Desktop dependency installation failed with exit code $LASTEXITCODE."
        }
    }

    Write-Host "== Desktop unit tests =="
    npm test
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop tests failed with exit code $LASTEXITCODE."
    }

    Write-Host "== Package Windows installer and portable archive =="
    # No code-signing certificate is configured for this stage.
    $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
    npm run dist
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop packaging failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

# Ignore stale artifacts from earlier builds: only files written by this run
# are published with fresh checksums.
$artifacts = @(Get-ChildItem $Release -File |
    Where-Object {
        $_.Extension -in @(".exe", ".zip") -and
        $_.LastWriteTime -ge $buildStarted
    } |
    Sort-Object Name)
if ($artifacts.Count -eq 0) {
    throw "No release files were produced."
}

$checksums = foreach ($file in $artifacts) {
    $hash = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLower()
    "$hash  $($file.Name)"
}
$checksumFile = Join-Path $Release "SHA256SUMS.txt"
$checksums | Set-Content -Path $checksumFile -Encoding ascii

$installNotesSource = Join-Path $Root "docs\desktop-install.txt"
$installNotesTarget = Join-Path $Release "INSTALL.txt"
Copy-Item $installNotesSource $installNotesTarget -Force

Write-Host ""
Write-Host "Build complete. Release files:"
$artifacts | ForEach-Object { Write-Host ("  " + $_.FullName) }
Write-Host ("  " + $checksumFile)
Write-Host ("  " + $installNotesTarget)
