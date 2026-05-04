@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Chain Gambler - Money Printer Desktop Launcher v2.0
REM  Includes: Ollama AI, Training Analysis, Symbol Simulations
REM ============================================================

title Chain Gambler - Money Printer Edition
color 0A
cls

echo.
echo  ============================================================
echo   Chain Gambler - Money Printer Desktop Launcher v2.0
echo  ============================================================
echo.
echo   Features:
echo   [✓] Ollama AI for training descriptions
echo   [✓] Per-symbol metrics tracking
echo   [✓] Multi-timeframe optimization
echo   [✓] Symbol simulations for $54 micro account
echo   [✓] Training-Trading connection analysis
echo   [✓] Real-time learning process visualization
echo.
echo  ============================================================
echo.

REM ── Set project directory ──
cd /d "C:\Users\Administrator\chain_gambler"
set PROJECT_ROOT=%CD%

REM ── Kill existing processes ──
echo [*] Cleaning up old processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
taskkill /F /IM ollama.exe 2>nul
timeout /t 3 /nobreak >nul

REM ── Environment Variables ──
echo [*] Setting environment variables...

:: Ollama Configuration
set OLLAMA_URL=http://localhost:11434
set OLLAMA_MODEL=qwen3:4b
set OLLAMA_ORIGINS=*

:: API Server Configuration
set AGI_LIVE_ENABLED=true
set AGI_CONTROL_TOKEN=chain_gambler_2026
set AGI_HOST=0.0.0.0
set AGI_PORT=9090
set AGI_TOKEN=fuckyou2/

:: Trading Configuration for Micro Account ($54)
set AGI_TRADE_INTERVAL_SEC=300
set AGI_TRAIL_INTERVAL_SEC=30
set AGI_EQUITY_POLL_SEC=15
set AGI_RISK_PERCENT=5.0
set AGI_MAX_POS_PER_SYMBOL=1
set AGI_MIN_LOTS=0.01
set AGI_ACTION_THRESHOLD=0.001

:: Micro Account Settings
set MICRO_ACCOUNT_MODE=true
set MICRO_EQUITY=54

:: Training Configuration
set TRAINING_AI_ENABLED=true
set TRAINING_TIMEFRAMES=1m,5m,15m,30m,1h
set SYMBOL_SIMULATION_ENABLED=true

REM ── Start Ollama Server ──
echo [*] Starting Ollama AI Server (port 11434)...
start "Ollama-Server" /min cmd /k "cd /d %PROJECT_ROOT% && ollama serve"
timeout /t 5 /nobreak >nul

REM ── Verify Ollama is running ──
curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama is running
) else (
    echo [WARN] Ollama may still be loading...
)

REM ── Start API Server with Training Endpoints ──
echo [*] Starting API Server (port 5000)...
start "API-Server" /min cmd /k "cd /d %PROJECT_ROOT% && python Python/api_server.py"
timeout /t 5 /nobreak >nul

REM ── Verify API Server ──
curl -s http://localhost:5000/api/status >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] API Server is running
) else (
    echo [WARN] API Server may still be loading...
)

REM ── Run Symbol Simulations for $54 Account ──
echo [*] Running symbol simulations for micro account...
start "Symbol-Simulations" /min cmd /k "cd /d %PROJECT_ROOT% && python scripts/run_symbol_simulations.py > logs\symbol_sims_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log 2>&1"

REM ── Start UI Lab App with Training Features ──
echo [*] Starting Money Printer UI (port 4180+)...
start "Money-Printer-UI" /min cmd /k "cd /d %PROJECT_ROOT%\ui_lab_app && npm run dev"
timeout /t 10 /nobreak >nul

REM ── Find the actual port used by Vite ──
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "127.0.0.1:418"') do (
    for /f "tokens=2" %%b in ('tasklist ^| findstr " %%a "') do (
        set VITE_PID=%%a
    )
)

REM ── Display Status ──
cls
echo.
echo  ============================================================
echo   Chain Gambler - Money Printer Edition - RUNNING
echo  ============================================================
echo.
echo   Services Status:
echo   ────────────────
echo   [✓] Ollama AI Server    : http://localhost:11434
echo   [✓] API Server          : http://localhost:5000/api/status
echo   [✓] Training Endpoints  : /api/training/analysis
echo                            : /api/training/metrics
echo   [✓] Money Printer UI    : http://localhost:4183/ (or 4180-4182)
echo.
echo   Micro Account Settings ($54):
echo   ────────────────────────────
echo   • Position Size    : 0.01 lots (fixed)
echo   • Risk per Trade   : 5%% ($2.70)
echo   • Max Positions    : 1
necho   • Symbol Simulations: Running (check logs/symbol_sims_*.log)
echo.
echo   Quick Commands:
echo   ───────────────
echo   • View Training: curl http://localhost:5000/api/training/analysis
echo   • View Metrics : curl http://localhost:5000/api/training/metrics
echo   • Emergency    : curl -X POST http://localhost:5000/api/control -d {"action":"emergency_stop"}
echo.
echo  ============================================================
echo.
echo   Opening dashboard in 5 seconds...
echo.

timeout /t 5 /nobreak >nul

REM ── Open Browser ──
start "" "http://localhost:4183/"

REM ── Keep console open for logs ──
echo.
echo   Press any key to view real-time logs or close this window...
echo.
pause >nul

echo.
echo   Tailing latest API logs (Press Ctrl+C to stop)...
echo.
tail -f logs\api_server.log 2>nul || type logs\api_server.log 2>nul | tail -50
