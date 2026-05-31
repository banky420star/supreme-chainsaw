<#
.SYNOPSIS
    Production launcher for Exness MT5 terminal with Chain Gambler.

.DESCRIPTION
    Launches the MT5 terminal pre-configured for the Exness Trial account
    and optimized for automated trading with the Chain Gambler system.

    Credentials are provided via environment variables at runtime:
    - MT5_LOGIN    - MT5 account login
    - MT5_PASSWORD - MT5 account password
    - MT5_SERVER   - MT5 server address

.USAGE
    # Set credentials via environment (recommended)
    $env:MT5_LOGIN = "435656990"
    $env:MT5_PASSWORD = "your_password"
    $env:MT5_SERVER = "Exness-MT5Trial9"

    .\scripts\launch_mt5_exness.ps1

    Or pass parameters directly (less secure for logging):
    .\scripts\launch_mt5_exness.ps1 -Login 435656990 -Password "your_password" -Server "Exness-MT5Trial9"

.NOTES
    Run as the user who will run the trading bot.
    Use /portable so settings stay with the installation folder.
#>

param(
    [string]$Login = $env:MT5_LOGIN,
    [string]$Password = $env:MT5_PASSWORD,
    [string]$Server = $env:MT5_SERVER,
    [string]$Mt5Path = "C:\Program Files\MetaTrader 5\terminal64.exe"
)

if (-not $Login -or -not $Password -or -not $Server) {
    Write-Error "MT5 credentials not provided. Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER environment variables or pass as parameters."
    exit 1
}

# Try to find the terminal if default path doesn't exist
if (-not (Test-Path $Mt5Path)) {
    Write-Host "Default path not found, searching for terminal64.exe..." -ForegroundColor Yellow
    $found = Get-ChildItem -Path "C:\Program Files*" -Filter "terminal64.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $Mt5Path = $found.FullName
        Write-Host "Found MT5 at: $Mt5Path" -ForegroundColor Green
    } else {
        Write-Error "Could not locate terminal64.exe. Please install MT5 first."
        exit 1
    }
}

$mt5Dir = Split-Path $Mt5Path

Write-Host "=== Launching Exness MT5 for Chain Gambler ===" -ForegroundColor Cyan
Write-Host "Login : $Login"
Write-Host "Server: $Server"
Write-Host "Path  : $Mt5Path"

# Build arguments for reliable automated login
$arguments = @(
    "/login:$Login",
    "/password:$Password",
    "/server:$Server",
    "/portable",
    "/skipnews"
)

Write-Host "Starting terminal with auto-login..." -ForegroundColor Yellow

$process = Start-Process -FilePath $Mt5Path -ArgumentList $arguments -WorkingDirectory $mt5Dir -PassThru

Write-Host "MT5 launched. Process ID: $($process.Id)" -ForegroundColor Green
Write-Host "The terminal should now be logged in and ready for the Python MetaTrader5 package." -ForegroundColor Green

# Optional: Wait a few seconds and verify
Start-Sleep -Seconds 8

Write-Host "`nTo test connectivity from Python, run:" -ForegroundColor Cyan
Write-Host "python -c \"import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.account_info()); mt5.shutdown()\"" -ForegroundColor White
