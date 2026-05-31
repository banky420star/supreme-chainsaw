# Supreme Chainsaw - One-click TUI Launcher (PowerShell)
# Run from project root:  .\launch_tui.ps1
#
# Quick status only (no live refresh):  .\launch_tui.ps1 -Once
#
# Auto-launch TUI on candidate staging / training complete (self-sustaining watcher):
#   .\launch_tui.ps1 -Watcher -Persistent
# This integrates with vps_agi_supervisor for zero-touch observation when new post-fix 50k candidates appear.

param(
    [switch]$Once,
    [switch]$Watcher,      # Launch the robust pipeline observer instead of direct TUI
    [switch]$Persistent    # For watcher: keep running across multiple completion events
)

$ErrorActionPreference = "Stop"
Set-Location "C:\supreme-chainsaw"

$py = ".\.venv312\Scripts\python.exe"
$tui = "scripts\monitor_tui.py"
$observer = "tools\launch_pipeline_observer_on_completion.py"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Supreme Chainsaw - Autonomous Pipeline TUI    " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Live observer for the full 7-stage pipeline (Training is the critical path)." -ForegroundColor Green
Write-Host "New: Swarm Status panel (Grok 30+ subagents + project agents) + unified audit / loop-closure." -ForegroundColor Magenta
Write-Host "     Grok swarm auto-bridged on launch via scripts/swarm_status.py --sync-grok" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $py)) {
    Write-Host "[FATAL] Venv python not found at $py" -ForegroundColor Red
    Write-Host "Fix: cd C:\supreme-chainsaw ; dir .venv312\Scripts\python.exe" -ForegroundColor Yellow
    exit 1
}

if ($Watcher) {
    Write-Host "WATCHER MODE: Robust auto-TUI on 'Candidate staged' or training completion signals." -ForegroundColor Yellow
    Write-Host "Watching recent training logs (postfix 50k, timestamped, enhanced etc.)." -ForegroundColor DarkGray
    $obsArgs = @($observer)
    if ($Persistent) { $obsArgs += "--persistent" }
    Write-Host "Launching observer (logs will show detections)..."
    & $py @obsArgs
    exit $LASTEXITCODE
}

$args = @($tui)
if ($Once) { $args += "--once" }

# Swarm Coordination: ensure full visibility of Grok sub-swarm + any project agents before TUI starts
Write-Host "Syncing full agent swarm status (Grok subagents + project) for TUI..." -ForegroundColor DarkGray
& $py -c "from scripts.swarm_status import sync_grok_swarm; print('Synced', sync_grok_swarm(36), 'Grok agents for unified visibility')" 2>$null

# Use the call operator to avoid PS current-dir execution policy gotchas
& $py @args

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[WARN] TUI exited with code $LASTEXITCODE" -ForegroundColor Yellow
    Write-Host "If rich is missing:  .\.venv312\Scripts\python.exe -m pip install rich" -ForegroundColor Yellow
}

Write-Host ""
if ($Once) {
    Write-Host "Snapshot complete." -ForegroundColor DarkGray
} else {
    Write-Host "TUI closed. Press any key..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
