#!/bin/bash
# ============================================================
#  Money Printer - Mac Launcher (Full Kelly Aggressive)
#  Double-click or run: bash start_mac.sh
# ============================================================

set -e

# ── Project root (directory of this script) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Source .env if present (MT5 credentials, tokens, etc.) ──
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# ── Colors ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Money Printer - DRY-RUN / SIMULATION ONLY (Mac)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo "  *** MACOS: SIMULATION / DRY-RUN ONLY ***"
echo "  Real MT5 live execution is NOT available on macOS without a working Wine+MT5 bridge."
echo "  Use this for model development, backtesting, paper trading, and UI testing."
echo "  For production live trading, deploy to Windows VPS with native MT5 (recommended)."
echo ""
echo "  Aggressive Kelly-style params for simulation testing only."
echo ""

# ── Kill existing processes ──
echo -e "${YELLOW}Cleaning up old processes...${NC}"
pkill -9 -f "Server_AGI" 2>/dev/null || true
pkill -9 -f "Python.api_server" 2>/dev/null || true
pkill -9 -f "api_server.py" 2>/dev/null || true
pkill -9 -f "vite.*4180" 2>/dev/null || true
sleep 3

# ── Remove stale lock files ──
rm -f "$SCRIPT_DIR/.tmp/server_agi.lock" "$SCRIPT_DIR/.tmp/champion_cycle.lock" 2>/dev/null || true

# ── Check ports ──
check_port() {
    local port=$1
    if lsof -i :$port -P -n 2>/dev/null | grep -q LISTEN; then
        echo -e "${YELLOW}WARNING: Port $port in use, killing...${NC}"
        lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
        sleep 3
    fi
}
check_port 5050
check_port 4180
sleep 2
PYTHON=""
for candidate in \
    "$SCRIPT_DIR/.venv312/bin/python" \
    "$SCRIPT_DIR/.venv/bin/python" \
    "$SCRIPT_DIR/../.venv312/bin/python" \
    "$(which python3)" \
    "$(which python)"; do
    if [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z ""$PYTHON"" ]; then
    echo -e "${RED}ERROR: Python not found. Install Python 3.12+ and create a venv.${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python: ${PYTHON}${NC}"
"$PYTHON" --version

# ── Install dependencies if needed ──
if [ ! -d "$SCRIPT_DIR/.venv312" ] && [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo -e "${YELLOW}No venv found. Creating one...${NC}"
    "$PYTHON" -m venv "$SCRIPT_DIR/.venv"
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# ── Environment variables ──
# IMPORTANT: On macOS this is ALWAYS dry-run / paper simulation only.
# Real MT5 order execution requires Windows (native MT5) or a fully working Wine bridge (fragile).
export AGI_LIVE_ENABLED=false
export AGI_REQUIRE_EXPLICIT_LIVE_ARM=false

# Control token: prefer .env or env var, never hardcode weak defaults in production
if [ -z "${AGI_CONTROL_TOKEN:-}" ]; then
    export AGI_CONTROL_TOKEN="${AGI_CONTROL_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))' 2>/dev/null || echo 'mac-dryrun-CHANGE-THIS-NOW')}"
    echo -e "${YELLOW}Using generated AGI_CONTROL_TOKEN (store it!): $AGI_CONTROL_TOKEN${NC}"
fi
export AGI_DEADZONE_CONFIDENCE=0.99
export AGI_ACTION_THRESHOLD=0.0001
export AGI_HIGH_VOL_MIN_ACTION=0.0001
export AGI_LOW_VOL_MIN_ACTION=0.0001
export AGI_MED_VOL_MIN_ACTION=0.0001
export AGI_MIN_LOTS=0.02
export AGI_RISK_PERCENT=1.0
export AGI_TRADE_INTERVAL_SEC=30
export AGI_NEG_TIMEOUT_MIN=60
export AGI_TRAIL_INTERVAL_SEC=15
export AGI_BIAS_WINDOW=50
export AGI_BIAS_STRENGTH=0.5
export AGI_EQUITY_POLL_SEC=15
export AGI_MAX_POS_PER_SYMBOL=3
export AGI_SL_COOLDOWN_MIN=3
export AGI_HEARTBEAT_SEC=1800
export CANARY_LOT_MULT=1.0
export CANARY_MAX_LOSS_PCT=10
export AGI_TRAIN_INTERVAL_HOURS=2

# ── Start Backend ──
echo -e "${GREEN}Starting Backend Server (DRY-RUN mode on Mac)...${NC}"
echo "  Note: Live MT5 trading requires Windows. Mac runs in simulation mode."
"$PYTHON" -m Python.Server_AGI &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# ── Start API Server ──
echo -e "${GREEN}Starting API Server (port 5050)...${NC}"
"$PYTHON" -m Python.api_server &
API_PID=$!
echo "  API PID: $API_PID"

# ── Wait for backend ──
echo -e "${YELLOW}Waiting for backend to load models (30s)...${NC}"
sleep 30

# ── Health check ──
if curl -s http://localhost:5050/api/status > /dev/null 2>&1; then
    echo -e "${GREEN}API Server is ONLINE${NC}"
else
    echo -e "${YELLOW}WARNING: API not responding yet, may need more time${NC}"
fi

# ── Start Frontend ──
echo -e "${GREEN}Starting UI Lab Frontend...${NC}"
if [ -d "$SCRIPT_DIR/ui_lab_app" ]; then
    cd "$SCRIPT_DIR/ui_lab_app"
    if [ -d "node_modules" ]; then
        npm run dev -- --host 0.0.0.0 --port 4180 &
        FRONTEND_PID=$!
        echo "  Frontend PID: $FRONTEND_PID"
    else
        echo -e "${YELLOW}Installing frontend dependencies...${NC}"
        npm install
        npm run dev -- --host 0.0.0.0 --port 4180 &
        FRONTEND_PID=$!
    fi
    cd "$SCRIPT_DIR"
else
    echo -e "${YELLOW}No ui_lab_app directory found, skipping frontend.${NC}"
fi

sleep 5

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} All systems launched! (DRY-RUN SIMULATION on Mac)${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Backend API : http://localhost:5050/api/status"
echo "  Frontend UI : http://localhost:4180/"
echo "  Emergency stop:"
echo "  curl -X POST http://localhost:5050/api/control -H 'Content-Type: application/json' -H "X-Control-Token: \$AGI_CONTROL_TOKEN" -d '{\"action\":\"emergency_stop\"}'"
echo ""
echo "  Press Ctrl+C to stop all services"

# ── Graceful shutdown ──
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $API_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    pkill -9 -f "Server_AGI" 2>/dev/null || true
    pkill -f "api_server" 2>/dev/null || true
    pkill -9 -f "vite.*4180"
pkill -9 -f "Python.api_server"
pkill -9 -f "api_server.py" 2>/dev/null || true
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Keep script alive ──
wait