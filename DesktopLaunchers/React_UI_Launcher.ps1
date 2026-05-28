# Supreme Chainsaw - React UI Launcher (Frontend Only)
# Starts the beautiful production React dashboard (Vite dev server on port 5173)
# Connects to the backend api_server on 5050 for all data.

$ErrorActionPreference = "Stop"
Set-Location "C:\supreme-chainsaw"

$frontendDir = "frontend"

Write-Host ""
Write-Host "================================================" -ForegroundColor Blue
Write-Host "  Supreme Chainsaw - REACT UI LAUNCHER          " -ForegroundColor Blue
Write-Host "================================================" -ForegroundColor Blue
Write-Host "Production React Dashboard (hot reload)" -ForegroundColor Cyan
Write-Host "Port 5173 → connects to api_server on 5050" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $frontendDir)) {
    Write-Host "[FATAL] frontend/ directory not found" -ForegroundColor Red
    Write-Host "Expected at: C:\supreme-chainsaw\frontend" -ForegroundColor Yellow
    pause
    exit 1
}

Push-Location $frontendDir

# Robust npm detection
$npmCmd = $null
if (Get-Command npm -ErrorAction SilentlyContinue) {
    $npmCmd = "npm"
} elseif (Test-Path "C:\Program Files\nodejs\npm.cmd") {
    $npmCmd = "C:\Program Files\nodejs\npm.cmd"
} elseif (Test-Path "$env:ProgramFiles\nodejs\npm.cmd") {
    $npmCmd = "$env:ProgramFiles\nodejs\npm.cmd"
}

if (-not $npmCmd) {
    Write-Host "[FATAL] npm not found in PATH or standard locations." -ForegroundColor Red
    Write-Host "Install Node.js from https://nodejs.org/ then re-run this launcher." -ForegroundColor Yellow
    Pop-Location
    pause
    exit 1
}

Write-Host "Using npm: $npmCmd" -ForegroundColor DarkGray
Write-Host "Starting Vite React dev server on port 5173..." -ForegroundColor Green
Write-Host "(This will stay open. Close this window to stop the UI.)" -ForegroundColor DarkGray
Write-Host ""

try {
    & $npmCmd run dev
} catch {
    Write-Host "[ERROR] Failed to start React UI: $_" -ForegroundColor Red
    Write-Host "Try: cd frontend; npm install; npm run dev" -ForegroundColor Yellow
}

Pop-Location
Write-Host ""
Write-Host "React UI stopped." -ForegroundColor DarkGray
pause