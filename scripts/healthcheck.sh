#!/usr/bin/env bash
# =============================================================================
# Chain Gambler — Comprehensive Health Check
# Usage: bash scripts/healthcheck.sh [BASE_URL]
# Default BASE_URL: http://localhost:9090
#
# Checks:
#   1. API reachable (/api/health)
#   2. Status endpoint returns valid JSON (/api/status)
#   3. Bot is not in HALTED / emergency_stop state
#   4. Redis is reachable and responding to PING
#   5. nginx reverse proxy is forwarding correctly (if port 80 is up)
#   6. n8n UI responds (if port 5678 is up)
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
# =============================================================================

set -uo pipefail

BASE="${1:-http://localhost:9090}"
NGINX_BASE="http://localhost"
N8N_BASE="http://localhost:5678"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# ── Colors ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL + 1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; WARN=$((WARN + 1)); }
info() { echo -e "        $1"; }

echo ""
echo -e "${CYAN}==================================================${NC}"
echo -e "${CYAN} Chain Gambler — Health Check${NC}"
echo -e "${CYAN} Target: ${BASE}${NC}"
echo -e "${CYAN}==================================================${NC}"
echo ""

# ── Check 1: /api/health reachable ──
echo -e "${CYAN}[1] API Reachability${NC}"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE}/api/health" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    pass "/api/health returned HTTP 200"
else
    fail "/api/health returned HTTP ${HTTP_CODE} (expected 200)"
    info "Is the backend container running? Check: docker compose -f docker-compose.prod.yml ps"
fi

# ── Check 2: /api/status returns valid JSON ──
echo ""
echo -e "${CYAN}[2] Status Endpoint${NC}"
STATUS_BODY=$(curl -sf "${BASE}/api/status" 2>/dev/null || echo "")
if echo "$STATUS_BODY" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    pass "/api/status returned valid JSON"
else
    fail "/api/status did not return valid JSON"
    info "Raw response: ${STATUS_BODY:0:200}"
fi

# ── Check 3: Bot not in halted / emergency-stopped state ──
echo ""
echo -e "${CYAN}[3] Bot State${NC}"
if [ -n "$STATUS_BODY" ]; then
    # Extract known halt-indicator fields from the JSON
    HALTED=$(echo "$STATUS_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# Check multiple possible locations for halt state
halted = (
    d.get('halted', False)
    or d.get('emergency_stop', False)
    or str(d.get('status', '')).lower() in ('halted', 'stopped', 'emergency')
    or str(d.get('trading_state', '')).lower() in ('halted', 'stopped')
)
print('true' if halted else 'false')
" 2>/dev/null || echo "unknown")

    LIVE=$(echo "$STATUS_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
live = d.get('live', d.get('is_live', d.get('live_enabled', None)))
print(str(live).lower() if live is not None else 'unknown')
" 2>/dev/null || echo "unknown")

    if [[ "$HALTED" == "true" ]]; then
        fail "Bot is in HALTED / emergency_stop state — trading is suspended"
    elif [[ "$HALTED" == "false" ]]; then
        pass "Bot is NOT halted"
    else
        warn "Could not determine halt state from status JSON"
    fi

    if [[ "$LIVE" == "true" ]]; then
        pass "Live trading is ENABLED"
    elif [[ "$LIVE" == "false" ]]; then
        warn "Live trading is DISABLED (dry-run / simulation mode)"
    else
        warn "Could not determine live trading state"
    fi
else
    warn "Skipping state checks — no status body available"
fi

# ── Check 4: Redis ping ──
echo ""
echo -e "${CYAN}[4] Redis${NC}"
if command -v redis-cli &>/dev/null; then
    REDIS_REPLY=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING 2>/dev/null || echo "")
    if [[ "$REDIS_REPLY" == "PONG" ]]; then
        pass "Redis responded PONG at ${REDIS_HOST}:${REDIS_PORT}"
    else
        fail "Redis did not respond PONG (got: '${REDIS_REPLY}')"
        info "Is the redis container running? Check: docker compose -f docker-compose.prod.yml ps redis"
    fi
elif docker compose -f "$(dirname "$0")/../docker-compose.prod.yml" exec -T redis redis-cli PING 2>/dev/null | grep -q PONG; then
    pass "Redis responded PONG (via docker compose exec)"
else
    warn "redis-cli not found locally and docker compose exec failed — skipping Redis check"
    info "Install redis-tools or ensure the redis container is running"
fi

# ── Check 5: nginx reverse proxy ──
echo ""
echo -e "${CYAN}[5] nginx Reverse Proxy${NC}"
NGINX_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${NGINX_BASE}/api/health" 2>/dev/null || echo "000")
if [[ "$NGINX_CODE" == "200" ]]; then
    pass "nginx is proxying /api/health → backend (HTTP 200)"
elif [[ "$NGINX_CODE" == "000" ]]; then
    warn "nginx not reachable on port 80 — may not be in the stack"
else
    fail "nginx returned HTTP ${NGINX_CODE} for /api/health (expected 200)"
fi

FRONTEND_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${NGINX_BASE}/" 2>/dev/null || echo "000")
if [[ "$FRONTEND_CODE" == "200" ]]; then
    pass "nginx is serving frontend at /"
elif [[ "$FRONTEND_CODE" == "000" ]]; then
    warn "Frontend not reachable on port 80 (nginx may not be up)"
else
    warn "nginx returned HTTP ${FRONTEND_CODE} for / (expected 200)"
fi

# ── Check 6: n8n ──
echo ""
echo -e "${CYAN}[6] n8n Automation${NC}"
N8N_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${N8N_BASE}/" 2>/dev/null || echo "000")
if [[ "$N8N_CODE" == "200" ]] || [[ "$N8N_CODE" == "401" ]]; then
    # 401 means n8n is up but requires auth — that's expected with basic auth enabled
    pass "n8n is reachable at ${N8N_BASE} (HTTP ${N8N_CODE})"
elif [[ "$N8N_CODE" == "000" ]]; then
    warn "n8n not reachable on port 5678 — may not be in the stack"
else
    warn "n8n returned HTTP ${N8N_CODE}"
fi

# ── Summary ──
echo ""
echo -e "${CYAN}==================================================${NC}"
TOTAL=$((PASS + FAIL + WARN))
echo -e " Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}  (${TOTAL} total checks)"
echo -e "${CYAN}==================================================${NC}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Health check FAILED — review failures above.${NC}"
    echo "  Logs: docker compose -f docker-compose.prod.yml logs -f"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo -e "${YELLOW}Health check passed with warnings — review warnings above.${NC}"
    exit 0
else
    echo -e "${GREEN}All checks passed.${NC}"
    exit 0
fi
