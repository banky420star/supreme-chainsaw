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
    Write-Host "Expected: C:\supreme-chainsaw\.venv312\Scripts\python.exe" -ForegroundColor Yellow
    Write-Host "Run: python -m venv .venv312 ; .\.venv312\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "Launching Mini Pipeline TUI (rich interactive console)..." -ForegroundColor Green
Write-Host "If it crashes or looks broken, the rich TUI sometimes needs a modern terminal (Windows Terminal recommended)." -ForegroundColor DarkGray
Write-Host ""

try {
    & $py $miniTui
} catch {
    Write-Host ""
    Write-Host "[ERROR] Mini TUI crashed: $_" -ForegroundColor Red
    Write-Host "Common fixes:" -ForegroundColor Yellow
    Write-Host "  1. pip install -U rich" -ForegroundColor Yellow
    Write-Host "  2. Run manually: .\.venv312\Scripts\python.exe scripts\mini_pipeline_tui.py --once" -ForegroundColor Yellow
    Write-Host "  3. Use the full monitor: .\.venv312\Scripts\python.exe scripts\monitor_tui.py --mini" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Mini TUI session ended." -ForegroundColor DarkGray
pause