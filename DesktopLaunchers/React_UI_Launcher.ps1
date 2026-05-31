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
    exit 1
}

Push-Location $frontendDir

# Try to find npm
$npmCmd = "npm"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    $npmCmd = "C:\Program Files\nodejs\npm.cmd"
    if (-not (Test-Path $npmCmd)) {
        Write-Host "[FATAL] npm not found. Please install Node.js" -ForegroundColor Red
        Pop-Location
        exit 1
    }
}

Write-Host "Starting Vite React dev server..." -ForegroundColor Green
& $npmCmd run dev

Pop-Location

Write-Host ""
Write-Host "React UI stopped." -ForegroundColor DarkGray
pause