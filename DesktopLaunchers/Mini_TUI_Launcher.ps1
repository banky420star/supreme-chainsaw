# Supreme Chainsaw - Mini Pipeline TUI Launcher
# Clean, compact, always-on view of the full autonomous pipeline
# (Ingestion → Decision PPO + Patterns + Timing → Rich Execution)

$ErrorActionPreference = "Stop"
Set-Location "C:\supreme-chainsaw"

$py = ".\.venv312\Scripts\python.exe"
$miniTui = "scripts\mini_pipeline_tui.py"

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "  Supreme Chainsaw - MINI PIPELINE WATCHER      " -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "Compact live view of the entire ingestion → champion execution pipeline" -ForegroundColor Cyan
Write-Host "Includes: Decision PPO (rich 18-dim + patterns + timing), ExecutionAgent, Swarm status" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $py)) {
    Write-Host "[FATAL] Python venv not found at $py" -ForegroundColor Red
    exit 1
}

& $py $miniTui

Write-Host ""
Write-Host "Mini TUI closed." -ForegroundColor DarkGray
pause