# Handoff Watcher Launcher (PowerShell) - Resilient detached background for the Python watcher.
# Launches scripts/handoff_watcher.py as hidden independent process.
# Includes simple outer restart loop (if python exits unexpectedly).
# Use: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\handoff_watcher_launcher.ps1
# This survives the launching session / agent and keeps watcher polling 24/7.
# NEW STANDARD: passes MTF envs so arming always uses 1m+5m+15m+1h + best feats + Decision+Execution context.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = "C:\supreme-chainsaw" }
Set-Location $RepoRoot

$Logs = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$WLog = Join-Path $Logs "handoff_watcher_launcher.log"

function Write-LauncherLog {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss.fffZ")
    $line = "[$ts] [$Level] $Msg"
    Add-Content -Path $WLog -Value $line -Encoding UTF8 -Force
    Write-Host $line -ForegroundColor $(if ($Level -eq "ERROR") { "Red" } elseif ($Level -eq "WARN") { "Yellow" } else { "Cyan" })
}

Write-LauncherLog "=== HANDOFF WATCHER LAUNCHER START (resilient detached) ==="

$pyCandidates = @(
    (Join-Path $RepoRoot ".venv312\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    "python.exe"
)
$pythonExe = $null
foreach ($c in $pyCandidates) { if (Test-Path $c) { $pythonExe = $c; break } }
if (-not $pythonExe) { $pythonExe = "python.exe" }

$WatcherPy = Join-Path $RepoRoot "scripts\handoff_watcher.py"
if (-not (Test-Path $WatcherPy)) {
    Write-LauncherLog "FATAL: $WatcherPy not found. Aborting." "ERROR"
    exit 1
}

$env:PYTHONUNBUFFERED = "1"  # immediate log output

# NEW STANDARD: ensure watcher deploys multi-TF Decision+Execution context on arm
$env:AGI_USE_LEGACY_SINGLE_TF = "0"
$env:AGI_MULTI_TF_STANDARD = "1"
$env:AGI_FEATURE_VERSION = "multitimeframe_best"
$env:AGI_MTF_TIMEFRAMES = "1m,5m,15m,1h"
Write-LauncherLog "NEW MTF STANDARD envs set for handoff watcher (Decision+Execution multi-TF arming default)"

$maxRestarts = 50
$restartCount = 0

while ($restartCount -lt $maxRestarts) {
    Write-LauncherLog "Launching watcher (attempt $($restartCount+1)) : $pythonExe $WatcherPy (hidden, detached)"
    
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pythonExe
    $psi.Arguments = "`"$WatcherPy`""
    $psi.WorkingDirectory = $RepoRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1"

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $pid = $proc.Id
        Write-LauncherLog "Watcher Python started (PID=$pid). Polling for new candidates > 20260527_082932 ..."
        
        # Monitor until exit (for outer restart)
        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        Write-LauncherLog "Watcher exited (PID=$pid, code=$exitCode). Will restart in 10s..." "WARN"
    } catch {
        Write-LauncherLog "Launch error: $($_.Exception.Message)" "ERROR"
    }

    $restartCount++
    Start-Sleep -Seconds 10
}

Write-LauncherLog "Max restarts reached. Manual intervention required." "ERROR"
exit 2
