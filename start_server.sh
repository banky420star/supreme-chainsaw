#!/bin/bash

# Network Config
# Source .env if present so secrets aren't hardcoded
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

export AGI_HOST="${AGI_HOST:-0.0.0.0}"
export AGI_PORT="${AGI_PORT:-9090}"
export AGI_TOKEN="${AGI_TOKEN:-${AGI_CONTROL_TOKEN:-change-me-to-strong-random-token}}"

# Autonomy & Polling
export AGI_AUTONOMY_AUTO_CANARY="true"
export AGI_PNL_POLL="true"

# Risk & Cooldowns
export AGI_COOLDOWN_SEC="45"
export AGI_MIN_HOLD_SEC="120"
export CANARY_LOT_MULT="0.25"

# Deadzones (Spread / Noise Filters)
export AGI_DZ_EURUSD="0.18"
export AGI_DZ_GBPUSD="0.20"
export AGI_DZ_XAUUSD="0.22"

# Default to paper mode; live requires explicit opt-in
export CHAIN_GAMBLER_EXECUTION_MODE="paper"
export CHAIN_GAMBLER_ALLOW_LIVE="0"

echo "🚀 Starting Grok AGI Server on Port $AGI_PORT with Token '$AGI_TOKEN' in PAPER mode..."

# If you prefer to use your python venv, uncomment the next line:
# source venv/bin/activate

python -m Python.Server_AGI
