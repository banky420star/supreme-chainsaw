@echo off
title SupremeChainsaw — Full Stack Launcher
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════════════════════════
:: SupremeChainsaw Full Stack Launcher
:: Starts the API server, React UI, and monitors both processes
:: with auto-restart capability.
:: ═══════════════════════════════════════════════════════════════

:: Detect script directory
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%"

:: Clean up trailing backslash
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║           SUPREMECHAINSAW — FULL STACK LAUNCHER          ║
echo  ║         Autonomous Trading Stack - Chain Gambler         ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo  [*] Project Root: %ROOT_DIR%
echo.

:: ─── Step 1: Verify Python virtual environment ────────────────
set "VENV_DIR=%ROOT_DIR%\.venv312"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo  [!] Virtual environment not found at %VENV_DIR%
    echo  [!] Attempting to create it...
    
    :: Check if python is available
    where python >nul 2>nul
    if errorlevel 1 (
        echo  [X] Python not found in PATH! Please install Python 3.12+.
        echo      Download from: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [X] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [✓] Virtual environment created.
    
    :: Install dependencies
    echo  [*] Installing Python dependencies (this may take a while)...
    "%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
    "%PYTHON_EXE%" -m pip install -r "%ROOT_DIR%\requirements.txt"
    if errorlevel 1 (
        echo  [!] Some dependencies may have failed to install.
        echo      Check the output above for details.
    ) else (
        echo  [✓] Python dependencies installed.
    )
) else (
    echo  [✓] Python virtual environment found.
)

:: ─── Step 2: Verify Node.js frontend dependencies ─────────────
set "UI_DIR=%ROOT_DIR%\03_UI_Monitoring\frontend"

if not exist "%UI_DIR%\node_modules" (
    echo  [*] Installing Node.js frontend dependencies...
    cd /d "%UI_DIR%"
    call npm install
    if errorlevel 1 (
        echo  [X] npm install failed. Check the output above.
        pause
        exit /b 1
    )
    echo  [✓] Frontend dependencies installed.
) else (
    echo  [✓] Frontend dependencies found.
)

:: ─── Step 3: Launch the PowerShell launcher ───────────────────
echo.
echo  [*] Launching the full stack with process monitoring...
echo  [*] API Server:  http://localhost:5051/api/status
echo  [*] UI Dashboard: http://localhost:4180
echo  [*] Press Ctrl+C to stop all services.
echo.

:: Launch the PowerShell monitor script
set "LAUNCHER_SCRIPT=%ROOT_DIR%\supreme_launcher.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER_SCRIPT%" -RootDir "%ROOT_DIR%"

:: If PowerShell script exits, we land here
echo.
echo  [*] SupremeChainsaw has shut down.
pause
