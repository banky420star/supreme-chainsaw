<#
.SYNOPSIS
    One-time MT5 VPS Post-Install Configuration Script for Chain Gambler production.

.DESCRIPTION
    Run this AFTER you have:
    1. RDP'd into the VPS
    2. Manually run C:\Temp\mt5setup.exe (or your broker's MT5 installer)
    3. Logged into your broker account for the first time
    4. Enabled "Allow automated trading" + "Allow DLL imports" in Tools → Options → Expert Advisors

    This script will:
    - Create a clean dedicated MT5 folder (recommended)
    - Set up optimal shortcuts for production
    - Configure auto-start behavior
    - Create a dedicated "MT5 - Chain Gambler" desktop + Start Menu shortcut
    - Prepare Task Scheduler friendly launch options
    - Output the exact path you need for Python connectivity tests

.NOTES
    Run as Administrator.
    Requires MT5 already installed and logged in at least once.
#>

param(
    [string]$BrokerName = "Generic",
    [string]$InstallSource = "C:\Program Files\MetaTrader 5",
    [switch]$CreateDedicatedFolder = $true
)

Write-Host "=== Chain Gambler MT5 VPS Post-Install Setup ===" -ForegroundColor Cyan
Write-Host "Broker: $BrokerName" -ForegroundColor Gray

$ErrorActionPreference = "Stop"

# 1. Find existing MT5 installation
$mt5Exe = $null
$searchPaths = @(
    "$InstallSource\terminal64.exe",
    "C:\Program Files\MetaTrader 5\terminal64.exe",
    "C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    "$env:APPDATA\MetaQuotes\Terminal\*\terminal64.exe"
)

foreach ($path in $searchPaths) {
    $found = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $mt5Exe = $found.FullName
        Write-Host "Found MT5 at: $mt5Exe" -ForegroundColor Green
        break
    }
}

if (-not $mt5Exe) {
    Write-Error "Could not find terminal64.exe. Make sure you ran the MT5 installer and logged in at least once via RDP."
    exit 1
}

$mt5Dir = Split-Path $mt5Exe -Parent

# 2. Create dedicated production folder (recommended for multiple instances / clean separation)
$prodMt5Root = "C:\MT5_ChainGambler"
if ($CreateDedicatedFolder) {
    Write-Host "Creating dedicated production folder: $prodMt5Root" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $prodMt5Root | Out-Null

    # Copy the installed files (this is a common pattern for clean VPS setups)
    Write-Host "Copying MT5 files to dedicated folder (this can take 1-2 minutes)..." -ForegroundColor Yellow
    robocopy $mt5Dir $prodMt5Root /E /MT:8 /NFL /NDL /NJH /NJS /nc /ns | Out-Null
    $mt5Exe = Join-Path $prodMt5Root "terminal64.exe"
    Write-Host "Dedicated copy ready at: $mt5Exe" -ForegroundColor Green
}

# 3. Create production launch shortcuts
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Chain Gambler"

New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

# Production launch shortcut (no news, optimized for bot)
$shortcutPath = Join-Path $desktop "MT5 - Chain Gambler (Production).lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $mt5Exe
$Shortcut.Arguments = "/skipnews /portable"
$Shortcut.WorkingDirectory = (Split-Path $mt5Exe)
$Shortcut.Description = "Chain Gambler Production MT5 Terminal"
$Shortcut.Save()
Write-Host "Created desktop shortcut: $shortcutPath" -ForegroundColor Green

# Start Menu version
$startShortcut = Join-Path $startMenu "MT5 - Chain Gambler (Production).lnk"
Copy-Item $shortcutPath $startShortcut -Force

# 4. Create a simple batch launcher for Task Scheduler / auto-start
$launcherBat = "C:\MT5_ChainGambler\Launch_MT5_Production.bat"
@"
@echo off
echo Starting MT5 for Chain Gambler production...
start "" "$mt5Exe" /skipnews /portable
"@ | Out-File -FilePath $launcherBat -Encoding ASCII -Force
Write-Host "Created Task Scheduler friendly launcher: $launcherBat" -ForegroundColor Green

# 5. Output the exact path for Python
Write-Host "`n=== NEXT STEP FOR PYTHON CONNECTIVITY ===" -ForegroundColor Cyan
Write-Host "Use this exact path when testing MetaTrader5 package:" -ForegroundColor Yellow
Write-Host $mt5Exe -ForegroundColor White

Write-Host "`nAfter you close this RDP session, the terminal can run headlessly." -ForegroundColor Gray
Write-Host "We will then run the Python connectivity test from the agent." -ForegroundColor Gray

Write-Host "`n=== MT5 VPS Setup Complete ===" -ForegroundColor Green
Write-Host "You may now close the MT5 terminal and disconnect RDP." -ForegroundColor Cyan
Write-Host "The bot will control the terminal via Python going forward." -ForegroundColor Cyan
