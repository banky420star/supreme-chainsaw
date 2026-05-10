#!/usr/bin/env bash
# =============================================================================
# Chain Gambler — Production Stack Startup
# Usage: bash scripts/start_prod.sh [--no-build]
#
# Steps:
#   1. Validate .env exists and has required keys
#   2. Build the frontend (unless --no-build is passed)
#   3. Bring up the full production stack via docker compose
#   4. Wait for health check to pass
# =============================================================================

set -euo pipefail

# ── Resolve project root regardless of where the script is called from ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── Colors ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

NO_BUILD=false
for arg in "$@"; do
    [[ "$arg" == "--no-build" ]] && NO_BUILD=true
done

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Chain Gambler — Production Startup${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ── Step 1: Validate .env ──
echo -e "${YELLOW}[1/4] Validating environment...${NC}"

if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env not found.${NC}"
    echo "       Copy .env.example → .env and fill in credentials before deploying."
    echo "       cp .env.example .env && \$EDITOR .env"
    exit 1
fi

# Check required keys are non-empty
REQUIRED_KEYS=(
    "AGI_CONTROL_TOKEN"
    "AGI_IS_LIVE"
)

MISSING=()
for key in "${REQUIRED_KEYS[@]}"; do
    # Extract value: skip comment lines, match KEY=value
    val=$(grep -E "^${key}=" .env | head -1 | cut -d'=' -f2- | xargs)
    if [ -z "$val" ]; then
        MISSING+=("$key")
    fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
    echo -e "${RED}ERROR: Required variables are empty in .env:${NC}"
    for k in "${MISSING[@]}"; do
        echo "       - $k"
    done
    exit 1
fi

# Warn if control token looks like a default/weak value
TOKEN_VAL=$(grep -E "^AGI_CONTROL_TOKEN=" .env | head -1 | cut -d'=' -f2- | xargs)
if [[ "$TOKEN_VAL" == "chain_gambler_2026" ]] || [ ${#TOKEN_VAL} -lt 16 ]; then
    echo -e "${YELLOW}WARNING: AGI_CONTROL_TOKEN appears weak or is the dev default.${NC}"
    echo "         Generate a strong token: openssl rand -hex 32"
fi

echo -e "${GREEN}  .env validated${NC}"

# ── Step 2: Build frontend ──
if [ "$NO_BUILD" = false ]; then
    echo ""
    echo -e "${YELLOW}[2/4] Building frontend...${NC}"
    if [ ! -d frontend/node_modules ]; then
        echo "  Installing frontend dependencies (npm ci)..."
        (cd frontend && npm ci)
    fi
    (cd frontend && npm run build)
    echo -e "${GREEN}  Frontend built → frontend/dist/${NC}"
else
    echo ""
    echo -e "${YELLOW}[2/4] Skipping frontend build (--no-build)${NC}"
fi

# ── Step 3: Start production stack ──
echo ""
echo -e "${YELLOW}[3/4] Starting production stack...${NC}"
docker compose -f docker-compose.prod.yml pull --quiet 2>/dev/null || true
docker compose -f docker-compose.prod.yml up -d --build

echo -e "${GREEN}  Stack started${NC}"
docker compose -f docker-compose.prod.yml ps

# ── Step 4: Health check ──
echo ""
echo -e "${YELLOW}[4/4] Waiting for backend health check (up to 90s)...${NC}"

MAX_WAIT=90
INTERVAL=5
ELAPSED=0
HEALTHY=false

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost/api/health 2>/dev/null || echo "000")
    if [[ "$STATUS" == "200" ]]; then
        HEALTHY=true
        break
    fi
    printf "  Waiting... (%ds elapsed, last HTTP status: %s)\r" "$ELAPSED" "$STATUS"
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}  Health check passed (HTTP 200)${NC}"
else
    echo -e "${YELLOW}  WARNING: Health check did not pass within ${MAX_WAIT}s${NC}"
    echo "           The stack may still be starting. Check logs with:"
    echo "           docker compose -f docker-compose.prod.yml logs -f backend"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Stack is UP${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  API Health : http://localhost/api/health"
echo "  API Status : http://localhost/api/status"
echo "  Frontend   : http://localhost/"
echo "  n8n        : http://localhost:5678/ (admin / \$N8N_PASSWORD)"
echo "  Backend    : http://localhost:9090/api/health (direct)"
echo ""
echo "  View logs  : docker compose -f docker-compose.prod.yml logs -f"
echo "  Stop stack : docker compose -f docker-compose.prod.yml down"
echo "  Emergency  : curl -X POST http://localhost/api/control \\"
echo "                 -H 'Content-Type: application/json' \\"
echo "                 -H \"X-Control-Token: \$AGI_CONTROL_TOKEN\" \\"
echo "                 -d '{\"action\":\"emergency_stop\"}'"
echo ""
