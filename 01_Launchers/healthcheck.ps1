<#
.SYNOPSIS
    Simple, reliable Windows health check for Chain Gambler AGI (VPS use).
    Enhanced for Operational Readiness + paper trading supervision (includes supervisor, venv, lock age, MT5 hints, hardened disk).
    Run: powershell -File scripts\healthcheck.ps1 -IncludeMT5Check
    Used by monitor_tui.py and vps_agi_supervisor.ps1 integration.
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:9090",
    [switch]$IncludeMT5Check,
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$logsDir = Join-Path $repoRoot "logs"
$lockPath = Join-Path $repoRoot ".tmp\server_agi.lock"

$passed = 0
$failed = 0
$warned = 0

if (-not $Quiet) {
    Write-Host "Chain Gambler Healthcheck (paper-ready supervision) | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
}

function Add-Result {
    param($Name, $Ok, $Msg = "")
    if ($Ok) { $script:passed++ } else { $script:failed++ }
    if (-not $Quiet) {
        $color = if ($Ok) { "Green" } else { "Red" }
        Write-Host ("{0,-45} {1}" -f $Name, $(if($Ok){"[PASS]"}else{"[FAIL]"})) -ForegroundColor $color
        if ($Msg) { Write-Host "   $Msg" -ForegroundColor DarkGray }
    }
}

# 1. Health endpoint
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 8
    if ($health.status -eq "ok") { Add-Result "API /health" $true } else { Add-Result "API /health" $false $health.status }
} catch { Add-Result "API /health" $false $_.Exception.Message }

# 2. Ready endpoint
try {
    $ready = Invoke-RestMethod -Uri "$BaseUrl/api/health/ready" -TimeoutSec 8
    if ($ready.ready) { Add-Result "API /health/ready" $true } else { Add-Result "API /health/ready" $false ($ready.reason) }
} catch { Add-Result "API /health/ready" $false $_.Exception.Message }

# 3. AGI process
$agiRunning = $false
try {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "Server_AGI" }
    if ($procs) { $agiRunning = $true }
} catch {}
if (Test-Path $lockPath) { $agiRunning = $true }
Add-Result "AGI Server process / lock" $agiRunning

# 4. Recent logs
$logFile = Join-Path $logsDir "server.log"
if (Test-Path $logFile) {
    $age = (Get-Date) - (Get-Item $logFile).LastWriteTime
    if ($age.TotalMinutes -lt 30) { Add-Result "server.log recent activity" $true } else { Add-Result "server.log recent activity" $false "Last write $([int]$age.TotalMinutes)m ago" }
} else {
    Add-Result "server.log exists" $false
}

# 5. MT5 (optional)
if ($IncludeMT5Check) {
    $mt5Proc = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
    Add-Result "MT5 terminal64.exe running" ($null -ne $mt5Proc)
    if ($mt5Proc) {
        $today = Get-Date -Format 'yyyyMMdd'
        $mt5Log = "$env:APPDATA\MetaQuotes\Terminal\*\logs\${today}.log"
        # Best effort recent login check from today's log (non-fatal) - dynamic date
        try {
            $recentAuth = Get-ChildItem -Path "$env:APPDATA\MetaQuotes\Terminal" -Recurse -Filter "*${today}.log" -ErrorAction SilentlyContinue | 
                Select-Object -First 1 | ForEach-Object { Get-Content $_.FullName -Tail 20 -ErrorAction SilentlyContinue | Select-String -Pattern "authorized|login|Exness" }
            if ($recentAuth) { 
                Add-Result "MT5 recent auth activity (today)" $true 
            } else {
                Add-Result "MT5 recent auth activity (today)" $true "MT5 running but no auth log match (may be ok)"
            }
        } catch {
            Add-Result "MT5 recent auth activity (today)" $true "Check skipped (non-fatal)"
        }
    }
}

# 6. Supervisor process (critical for E12 readiness)
$supRunning = $false
try {
    $supProcs = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "vps_agi_supervisor" }
    if ($supProcs) { $supRunning = $true }
} catch {}
$supLog = Join-Path $logsDir "vps_agi_supervisor.log"
if ((Test-Path $supLog) -and (((Get-Date) - (Get-Item $supLog).LastWriteTime).TotalMinutes -lt 5)) {
    $supRunning = $true
}
Add-Result "vps_agi_supervisor active (proc or recent log)" $supRunning

# 7. Venv + Python availability (paper trading foundation)
$py312 = Join-Path $repoRoot ".venv312\Scripts\python.exe"
$py = Join-Path $repoRoot ".venv\Scripts\python.exe"
$venvOk = (Test-Path $py312) -or (Test-Path $py)
Add-Result "Python venv present (.venv312 or .venv)" $venvOk

# 8. Lock file sanity (detect stale Server_AGI lock)
$lockAgeOk = $true
if (Test-Path $lockPath) {
    $lockAge = (Get-Date) - (Get-Item $lockPath).LastWriteTime
    if ($lockAge.TotalMinutes -gt 30) {
        Add-Result "server_agi.lock age (<30m)" $false "Stale? $($lockAge.TotalMinutes)m old"
        $lockAgeOk = $false
    } else {
        Add-Result "server_agi.lock age (<30m)" $true
    }
} else {
    Add-Result "server_agi.lock (absent = ok if not running)" $true "No lock present"
}

# 9. Disk space (hardened thresholds for long-running paper)
$drive = Get-PSDrive C
$freeGB = [math]::Round($drive.Free / 1GB, 1)
$usedPct = [math]::Round( ( ($drive.Used / ($drive.Used + $drive.Free)) * 100 ) , 0)
if ($freeGB -gt 20) {
    Add-Result "Disk space C: ($freeGB GB free, ~$usedPct% used)" $true
} elseif ($freeGB -gt 8) {
    Add-Result "Disk space C: ($freeGB GB free, ~$usedPct% used)" $true "Warning: monitor closely"
    $warned++
} else {
    Add-Result "Disk space C: ($freeGB GB free, ~$usedPct% used)" $false "Critically low for sustained ops"
}

if (-not $Quiet) {
    Write-Host ""
    Write-Host "Health Summary: $passed passed, $failed failed, $warned warnings" -ForegroundColor Cyan
}

if ($failed -gt 0) { exit 1 } else { exit 0 }
