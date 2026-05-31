@echo off
chcp 65001 >nul
echo ==========================================
echo  SUPREME CHAINSAW - DEMO TRADING BOT
echo ==========================================
echo.
echo Starting Full Stack...
echo  - API Server (Port 5051)
echo  - Trading Bot (Server_AGI)
echo  - React Dashboard (Port 4180)
echo.
echo Account: 435656990 (Exness Demo)
echo Mode: DEMO (Paper Trading)
echo.
echo ==========================================
echo.

:: Set environment variables
set "CHAIN_GAMBLER_EXECUTION_MODE=demo"
set "AGI_LIVE_ENABLED=true"
set "MT5_LOGIN=435656990"
set "MT5_PASSWORD=Fuckyou2/"
set "MT5_SERVER=Exness-MT5Trial9"
set "AGI_API_PORT=5051"
set "AGI_TRADING_MODE=live"
set "TELEGRAM_TOKEN=dummy"
set "TELEGRAM_CHAT_ID=0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "AGI_CONTROL_TOKEN=demo-token-12345"

cd /d "%~dp0"

:: Start API Server
start "API Server" cmd /k "cd 02_Core_Python ^&^& ..\.venv312\Scripts\python.exe -m Python.api_server"

timeout /t 3 /nobreak >nul

:: Start Trading Bot
start "Trading Bot" cmd /k "cd 02_Core_Python ^&^& ..\.venv312\Scripts\python.exe -m Python.Server_AGI"

timeout /t 3 /nobreak >nul

:: Start React UI
cd "03_UI_Monitoring" 2>nul || cd "../03_UI_Monitoring" 2>nul
if exist "node_modules" (
    start "React Dashboard" cmd /k "npm run dev -- --port 4180"
) else (
    echo React UI not built. Run 'npm install' in 03_UI_Monitoring first.
)

echo.
echo ==========================================
echo  All services started!
echo ==========================================
echo.
echo API Status: http://localhost:5051/api/status
echo Dashboard: http://localhost:4180
echo.
echo Press any key to exit this window...
pause >nul
