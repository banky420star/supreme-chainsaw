# Supreme Chainsaw - Full Stack Launcher
# Starts everything you need for complete autonomous trading observation:
# - Backend API Server (port 5050)
# - React Production UI (port 5173)
# - Main Rich TUI (full parity features + swarm status)
# - Optional supervisor integration

$ErrorActionPreference = "Continue"
Set-Location "C:\supreme-chainsaw"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Supreme Chainsaw - FULL STACK LAUNCHER                    " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Backend (5050) + React UI (5173) + Rich TUI + Swarm Status" -ForegroundColor Cyan
Write-Host "This is the complete production monitoring environment." -ForegroundColor DarkGray
Write-Host ""

$launchFull = ".\launch_full_project.ps1"

if (Test-Path $launchFull) {
    Write-Host "Delegating to launch_full_project.ps1 (full production stack)..." -ForegroundColor Yellow
    Write-Host "This starts: api_server (5050) + React UI (5173) + supervisor + TUI" -ForegroundColor DarkGray
    Write-Host ""
    try {
        & $launchFull
    } catch {
        Write-Host "[ERROR] launch_full_project.ps1 failed: $_" -ForegroundColor Red
        Write-Host "Try running it manually for detailed logs." -ForegroundColor Yellow
    }
} else {
    Write-Host "launch_full_project.ps1 not found. Using simple fallback..." -ForegroundColor Red
    
    $py = ".\.venv312\Scripts\python.exe"
    
    if (-not (Test-Path $py)) {
        Write-Host "[FATAL] venv python missing at $py" -ForegroundColor Red
        pause
        exit 1
    }

    Write-Host "Starting api_server (5050) minimized..." -ForegroundColor Cyan
    Start-Process -FilePath $py -ArgumentList "Python\api_server.py" -WindowStyle Minimized

    Start-Sleep -Seconds 4

    Write-Host "Starting React UI in new window..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "cd 'C:\supreme-chainsaw\frontend'; npm run dev" -WindowStyle Normal

    Start-Sleep -Seconds 3

    Write-Host "Starting rich monitor TUI..." -ForegroundColor Cyan
    & $py "scripts\monitor_tui.py" --mini
}

Write-Host ""
Write-Host "Full Stack session ended." -ForegroundColor DarkGray
pause