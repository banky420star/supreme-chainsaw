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
    Write-Host "Delegating to launch_full_project.ps1 (recommended full stack)..." -ForegroundColor Yellow
    & $launchFull
} else {
    Write-Host "launch_full_project.ps1 not found. Falling back to manual start..." -ForegroundColor Red
    
    # Fallback: start backend + TUI
    $py = ".\.venv312\Scripts\python.exe"
    
    Write-Host "Starting api_server on 5050..." -ForegroundColor Cyan
    Start-Process -FilePath $py -ArgumentList "Python\api_server.py" -WindowStyle Minimized
    
    Start-Sleep -Seconds 3
    
    Write-Host "Starting React UI..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev" -WindowStyle Normal
    
    Start-Sleep -Seconds 2
    
    Write-Host "Starting full TUI..." -ForegroundColor Cyan
    & $py "scripts\monitor_tui.py"
}

Write-Host ""
Write-Host "Full Stack session ended." -ForegroundColor DarkGray
pause