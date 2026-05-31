# launch_demo_mt5.ps1
# Demo launcher for Exness MT5 demo account with Chain Gambler
#
# This script:
# - Sets execution mode to demo
# - Sets MT5 server to Exness-MT5Trial9
# - Starts the api_server on port 5051
# - Starts the ui_lab_app Vite dev server on port 4180
#
# Credentials (login/password) should be provided via environment variables
# at runtime, or via session.json. Actual values are NOT hardcoded here.
#
# Usage:
#   $env:MT5_LOGIN = "435656990"
#   $env:MT5_PASSWORD = "your_password_here"
#   .\launch_demo_mt5.ps1

param(
    [string]$ApiServerPath = "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean\02_Core_Python\Python\api_server.py",
    [string]$UiLabPath = "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean\ui_lab_app",
    [int]$ApiPort = 5051,
    [int]$UiPort = 4180
)

$ErrorActionPreference = "Continue"

# Set demo execution mode and MT5 server via environment variables
$env:CHAIN_GAMBLER_EXECUTION_MODE = "demo"
$env:MT5_SERVER = "Exness-MT5Trial9"
$env:AGI_API_PORT = "5051"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Chain Gambler - DEMO MT5 LAUNCHER             " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Mode    : demo (real orders to demo account)" -ForegroundColor Yellow
Write-Host "Server  : $env:MT5_SERVER" -ForegroundColor Yellow
Write-Host "ApiPort : $ApiPort" -ForegroundColor Cyan
Write-Host "UiPort  : $UiPort" -ForegroundColor Cyan
Write-Host ""

# Verify Python venv exists
$pythonExe = "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean\.venv312\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "Python venv not found at: $pythonExe"
    exit 1
}

# Start api_server
Write-Host "Starting api_server on port $ApiPort..." -ForegroundColor Green
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList $ApiServerPath -WindowStyle Minimized -PassThru

# Wait for api_server to initialize
Start-Sleep -Seconds 3

# Check if ui_lab_app exists and start it
if (Test-Path $UiLabPath) {
    Write-Host "Starting ui_lab_app Vite dev server on port $UiPort..." -ForegroundColor Green
    Push-Location $UiLabPath

    $npmCmd = "npm"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        $npmCmd = "C:\Program Files\nodejs\npm.cmd"
    }

    Start-Process -FilePath $npmCmd -ArgumentList "run dev" -WindowStyle Normal

    Pop-Location
} else {
    Write-Host "ui_lab_app not found at: $UiLabPath - skipping UI start" -ForegroundColor Yellow
    Write-Host "You may need to use the frontend directory instead." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Demo MT5 Trading Environment Started          " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ensure MT5 is running with demo credentials:" -ForegroundColor Yellow
Write-Host "  Login    : from session.json or env:MT5_LOGIN" -ForegroundColor White
Write-Host "  Password : from env:MT5_PASSWORD" -ForegroundColor White
Write-Host "  Server   : $env:MT5_SERVER" -ForegroundColor White
Write-Host ""
Write-Host "To test MT5 connectivity, run:" -ForegroundColor Cyan
Write-Host 'python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.account_info()); mt5.shutdown()"' -ForegroundColor White
Write-Host ""

# Return process info
Write-Host "Started processes:" -ForegroundColor Green
Write-Host "  api_server PID: $($apiProcess.Id)" -ForegroundColor White