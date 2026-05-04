#!/bin/bash
# ============================================================
#  Money Printer - Mac Launcher (Full Kelly Aggressive)
#  Double-click or run: bash start_mac.sh
# ============================================================

set -e

# ── Project root (directory of this script) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Money Printer - FULL KELLY AGGRESSIVE (Mac)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo "  Full Kelly criterion (no half-sizing)"
echo "  Low regime thresholds (0.001 min action)"
echo "  Canary models at full lot size (1.0x)"
echo "  Deadzone effectively disabled (0.99)"
echo "  60s trade interval, 3min SL cooldown"
echo "  3% risk per trade, max 3 positions/symbol"
echo "  \$5 breakeven then tight trailing starts"
echo "  Scale-out 1/3 at \$5, 1/3 at \$10, runner trails to max"
echo "  Compound Kelly: 0.5x at \$50, 1.0x at \$200+"
echo "  Moderate PPO bias correction (0.5)"
echo "  10% canary max loss (equity-scaled)"
echo "  Full buys and sells enabled"
echo ""

# ── Kill existing processes ──
echo -e "${YELLOW}Cleaning up old processes...${NC}"
pkill -f "Server_AGI" 2>/dev/null || true
pkill -f "vite.*4180" 2>/dev/null || true
sleep 3

# ── Check ports ──
check_port() {
    local port=$1
    if lsof -i :$port -P -n 2>/dev/null | grep -q LISTEN; then
        echo -e "${YELLOW}WARNING: Port $port in use, killing...${NC}"
        lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

check_port 5000
check_port 4180

# ── Find Python ──
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

if [ -z "$PYTHON" ]; then
    echo -e "${RED}ERROR: Python not found. Install Python 3.12+ and create a venv.${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python: $PYTHON${NC}"
$PYTHON --version

# ── Install dependencies if needed ──
if [ ! -d "$SCRIPT_DIR/.venv312" ] && [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo -e "${YELLOW}No venv found. Creating one...${NC}"
    $PYTHON -m venv "$SCRIPT_DIR/.venv"
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
    $PYTHON -m pip install --upgrade pip
    $PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# ── Environment variables ──
export AGI_LIVE_ENABLED=true
export AGI_REQUIRE_EXPLICIT_LIVE_ARM=false
export AGI_CONTROL_TOKEN=chain_gambler_2026
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
$PYTHON -m Python.Server_AGI &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# ── Wait for backend ──
echo -e "${YELLOW}Waiting for backend to load models (30s)...${NC}"
sleep 30

# ── Health check ──
if curl -s http://localhost:5000/api/status > /dev/null 2>&1; then
    echo -e "${GREEN}Backend is ONLINE${NC}"
else
    echo -e "${YELLOW}WARNING: Backend not responding yet, may need more time${NC}"
fi

# ── Start Frontend ──
echo -e "${GREEN}Starting UI Lab Frontend...${NC}"
if [ -d "$SCRIPT_DIR/ui_lab_app" ]; then
    cd "$SCRIPT_DIR/ui_lab_app"
    if [ -d "node_modules" ]; then
        npx vite --host 0.0.0.0 --port 4180 &
        FRONTEND_PID=$!
        echo "  Frontend PID: $FRONTEND_PID"
    else
        echo -e "${YELLOW}Installing frontend dependencies...${NC}"
        npm install
        npx vite --host 0.0.0.0 --port 4180 &
        FRONTEND_PID=$!
    fi
    cd "$SCRIPT_DIR"
else
    echo -e "${YELLOW}No ui_lab_app directory found, skipping frontend.${NC}"
fi

sleep 5

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} All systems launched! FULL KELLY ACTIVE${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Backend API : http://localhost:5000/api/status"
echo "  Frontend UI : http://localhost:4180/"
echo "  Emergency stop:"
echo "  curl -X POST http://localhost:5000/api/control -H 'Content-Type: application/json' -H 'X-Control-Token: chain_gambler_2026' -d '{\"action\":\"emergency_stop\"}'"
echo ""
echo "  Press Ctrl+C to stop all services"

# ── Graceful shutdown ──
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    pkill -f "Server_AGI" 2>/dev/null || true
    pkill -f "vite.*4180" 2>/dev/null || true
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Keep script alive ──
wait