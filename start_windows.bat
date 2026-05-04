@echo off
REM ============================================================
REM  Chain Gambler - Windows Live Launcher (Optimized)
REM ============================================================

cd /d %~dp0

REM ── Kill existing processes ──
echo Cleaning up old processes...
taskkill /F /FI "WINDOWTITLE eq Server_AGI*" 2>nul || true
timeout /t 2 /nobreak >nul

REM ── Environment Variables ──
set AGI_LIVE_ENABLED=true
set AGI_REQUIRE_EXPLICIT_LIVE_ARM=false
set AGI_CONTROL_TOKEN=chain_gambler_2026
set AGI_HOST=0.0.0.0
set AGI_PORT=9090
set AGI_TOKEN=fuckyou2/

REM ── Trading Speed & Frequency ──
set AGI_TRADE_INTERVAL_SEC=300
set AGI_TRAIL_INTERVAL_SEC=30
set AGI_EQUITY_POLL_SEC=15
set AGI_REVIEW_INTERVAL_SEC=120
set AGI_HEARTBEAT_SEC=1800

REM ── Risk & Position Management ──
set AGI_HEDGING_ENABLED=false
set AGI_MAX_POS_PER_SYMBOL=5
set AGI_RISK_PERCENT=1.0
set AGI_SL_COOLDOWN_MIN=5
set AGI_MIN_LOTS=0.01
set AGI_ACTION_THRESHOLD=0.0001

REM ── Bias Correction ──
set AGI_BIAS_WINDOW=50
set AGI_BIAS_STRENGTH=0.5

REM ── Deadzone ──
set AGI_DEADZONE_CONFIDENCE=0.99

REM ── Autonomy ──
set AGI_AUTONOMY_AUTO_CANARY=true
set AGI_PNL_POLL=true
set CANARY_LOT_MULT=0.25

echo ============================================================
echo  Chain Gambler - LIVE Mode (5min interval, no hedging)
echo  Symbols: EURUSDm, GBPUSDm, BTCUSDm
echo  Trade interval: 5min | Review: 2min | No hedging
echo ============================================================

python -m Python.Server_AGI --live