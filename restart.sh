#!/bin/bash
# ============================================================
#  Chain Gambler - Full System Restart
#  Restarts backend + frontend with all new features
# ============================================================

set -e

# ── Project root ──
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
echo -e "${CYAN} Chain Gambler - SYSTEM RESTART${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo "  UI Updates Applied:"
echo "  - Reversal Detection Panel"
echo "  - Speed Simulator Panel"
echo "  - System Health Monitoring"
echo "  - Backup Manager Interface"
echo "  - Kelly Criterion Display"
echo "  - Signal Quality Filters"
echo "  - Decision Reasoning Traces"
echo ""

# ── Kill existing processes ──
echo -e "${YELLOW}Stopping existing processes...${NC}"
pkill -f "Server_AGI" 2>/dev/null || true
pkill -f "vite.*4180" 2>/dev/null || true
pkill -f "vite.*5173" 2>/dev/null || true
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
check_port 5173

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
    echo -e "${RED}ERROR: Python not found.${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python: $PYTHON${NC}"

# ── Environment variables (Optimized for production) ──
export AGI_LIVE_ENABLED=true
export AGI_REQUIRE_EXPLICIT_LIVE_ARM=false
export AGI_CONTROL_TOKEN="${AGI_CONTROL_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))' 2>/dev/null || echo 'CHANGE-THIS-STRONG-TOKEN')}"
export AGI_HOST=0.0.0.0
export AGI_PORT=9090

# Deadzone and thresholds
export AGI_DEADZONE_CONFIDENCE=0.99
export AGI_ACTION_THRESHOLD=0.0001
export AGI_LOW_VOL_MIN_ACTION=0.0001
export AGI_MED_VOL_MIN_ACTION=0.0001
export AGI_HIGH_VOL_MIN_ACTION=0.0001

# Bias correction
export AGI_BIAS_WINDOW=50
export AGI_BIAS_STRENGTH=0.3

# Risk management
export AGI_MIN_LOTS=0.01
export AGI_RISK_PERCENT=1.0
export AGI_MAX_POS_PER_SYMBOL=3
export AGI_TRADE_INTERVAL_SEC=60
export AGI_TRAIL_INTERVAL_SEC=30
export AGI_EQUITY_POLL_SEC=15

# Training optimization
export AGI_USE_SUBPROC_VECENV=0  # Set to 1 for parallel training

# Backup configuration
export AGI_BACKUP_DIR="$SCRIPT_DIR/backups"
export AGI_BACKUP_INTERVAL_HOURS=24
export AGI_MAX_BACKUPS=7

# ── Start Backend ──
echo -e "${GREEN}Starting Backend Server...${NC}"
$PYTHON -m Python.Server_AGI &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# ── Wait for backend ──
echo -e "${YELLOW}Waiting for backend to initialize (20s)...${NC}"
sleep 20

# ── Health check ──
HEALTH_URL="http://localhost:5000/api/health"
if curl -s $HEALTH_URL > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is ONLINE${NC}"
    echo "  Health endpoint: $HEALTH_URL"
else
    echo -e "${YELLOW}⚠ Backend not responding yet (may need more time)${NC}"
fi

# ── Start Frontend ──
echo -e "${GREEN}Starting Frontend UI...${NC}"
if [ -d "$SCRIPT_DIR/ui_lab_app" ]; then
    cd "$SCRIPT_DIR/ui_lab_app"
    if [ -d "node_modules" ]; then
        # Check if vite is available
        if npx vite --version > /dev/null 2>&1; then
            npx vite --host 0.0.0.0 --port 4180 &
            FRONTEND_PID=$!
            echo "  Frontend PID: $FRONTEND_PID"
            echo "  URL: http://localhost:4180"
        else
            echo -e "${YELLOW}Vite not found, skipping frontend${NC}"
        fi
    else
        echo -e "${YELLOW}No node_modules, skipping frontend (run npm install first)${NC}"
    fi
    cd "$SCRIPT_DIR"
else
    echo -e "${YELLOW}No ui_lab_app directory found${NC}"
fi

sleep 3

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} SYSTEM RESTARTED SUCCESSFULLY${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Backend API : http://localhost:5000/api/health"
echo "  Status      : http://localhost:5000/api/status"
echo "  Frontend    : http://localhost:4180"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# ── Graceful shutdown ──
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    pkill -f "Server_AGI" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Keep script alive ──
wait
