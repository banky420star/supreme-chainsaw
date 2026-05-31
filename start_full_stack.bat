@echo off
echo ============================================
echo  SUPREME CHAINSAW - FULL STACK LAUNCHER
echo ============================================
echo.

REM Set environment variables for demo trading
set CHAIN_GAMBLER_EXECUTION_MODE=demo
set AGI_LIVE_ENABLED=true
set MT5_LOGIN=435656990
set MT5_PASSWORD=Fuckyou2/
set MT5_SERVER=Exness-MT5Trial9
set AGI_API_PORT=5051
set TELEGRAM_TOKEN=dummy_token
set TELEGRAM_CHAT_ID=0
set AGI_CONTROL_TOKEN=control_token_12345

echo Environment configured for demo account:
echo   Login: %MT5_LOGIN%
echo   Server: %MT5_SERVER%
echo.

cd /d "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean"

REM Kill any stale Python processes
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo Starting API Server...
start "API Server" "02_Core_Python\.venv312\Scripts\python.exe" -m Python.Server_AGI

timeout /t 5 /nobreak >nul

echo Starting React UI...
start "React UI" "C:\Users\Administrator\Downloads\node-v24.16.0-win-x64\node-v24.16.0-win-x64\node.exe" "C:\supreme-chainsaw\ui_lab_app\node_modules\vite\bin\vite.js" dev --port 4180 --host 0.0.0.0

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo  ALL SERVICES STARTED!
echo ============================================
echo.
echo Dashboard: http://localhost:4180/
echo API Status: http://localhost:5051/api/status
echo.
pause
