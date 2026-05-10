#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Chain Gambler Launcher
# Double-click to open Terminal and start the entire trading stack.
# Close the Terminal window to stop all services.
# ═══════════════════════════════════════════════════════════════════════════════

cd "$(dirname "$0")"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_ROOT="$(pwd)"
TMP_DIR="$PROJECT_ROOT/.tmp"
WINEPREFIX="/Users/bank/Library/Application Support/net.metaquotes.wine.metatrader5"
WINE_BIN="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
VENV_NPM="/opt/homebrew/bin/npm"

mkdir -p "$TMP_DIR"

echo "[Chain Gambler] Starting trading stack..."

# -- MT5 Wine RPyC Bridge ------------------------------------------------------
if ! lsof -i :18812 | grep LISTEN >/dev/null 2>&1; then
    echo "[Chain Gambler] Starting MT5 Wine bridge..."
    export WINEPREFIX="$WINEPREFIX"
    export WINEDEBUG=-all
    export MT5_WINE_HOST=127.0.0.1
    export MT5_WINE_PORT=18812
    WINPY="C:\\winpython\\python.exe"
    SCRIPT="$PROJECT_ROOT/tools/mt5_wine_server.py"
    nohup "$WINE_BIN" "$WINPY" "$SCRIPT" > "$TMP_DIR/mt5_wine_server.log" 2>&1 &
    sleep 6
    if lsof -i :18812 | grep LISTEN >/dev/null 2>&1; then
        echo "[Chain Gambler] MT5 bridge ready."
    else
        echo "[Chain Gambler] WARNING: MT5 bridge failed to start."
    fi
else
    echo "[Chain Gambler] MT5 bridge already running."
fi

# -- API Server ----------------------------------------------------------------
if ! lsof -i :9090 | grep LISTEN >/dev/null 2>&1; then
    echo "[Chain Gambler] Starting API server on 9090..."
    cd "$PROJECT_ROOT"
    export AGI_API_PORT=9090
    nohup "$VENV_PYTHON" Python/api_server.py > "$TMP_DIR/api_server.log" 2>&1 &
    sleep 2
    echo "[Chain Gambler] API server started."
else
    echo "[Chain Gambler] API server already running."
fi

# -- Server_AGI ----------------------------------------------------------------
if ! pgrep -f "Server_AGI" >/dev/null 2>&1; then
    echo "[Chain Gambler] Starting Server_AGI in paper mode..."
    cd "$PROJECT_ROOT"
    export AGI_API_PORT=9090
    export CHAIN_GAMBLER_EXECUTION_MODE=paper
    export CHAIN_GAMBLER_ALLOW_LIVE=0
    rm -f "$TMP_DIR/server_agi.lock"
    nohup "$VENV_PYTHON" -m Python.Server_AGI > "$TMP_DIR/server_agi.log" 2>&1 &
    sleep 4
    echo "[Chain Gambler] Server_AGI started."
else
    echo "[Chain Gambler] Server_AGI already running."
fi

# -- Frontend ------------------------------------------------------------------
if ! lsof -i :5173 | grep LISTEN >/dev/null 2>&1; then
    echo "[Chain Gambler] Starting frontend dev server..."
    cd "$PROJECT_ROOT/frontend"
    nohup "$VENV_NPM" run dev > "$TMP_DIR/frontend.log" 2>&1 &
    sleep 3
    echo "[Chain Gambler] Frontend ready."
else
    echo "[Chain Gambler] Frontend already running."
fi

echo "[Chain Gambler] Opening dashboard..."
open "http://localhost:5173/app/"

echo "[Chain Gambler] All systems go. Press Ctrl+C or close this window to stop."

# Health-check loop: restart Server_AGI if it dies
while true; do
    /bin/sleep 10
    if ! pgrep -f "Server_AGI" >/dev/null 2>&1; then
        echo "[Chain Gambler] Server_AGI died -- restarting..."
        cd "$PROJECT_ROOT"
        export AGI_API_PORT=9090
        export CHAIN_GAMBLER_EXECUTION_MODE=paper
        export CHAIN_GAMBLER_ALLOW_LIVE=0
        rm -f "$TMP_DIR/server_agi.lock"
        nohup "$VENV_PYTHON" -m Python.Server_AGI > "$TMP_DIR/server_agi.log" 2>&1 &
    fi
done
