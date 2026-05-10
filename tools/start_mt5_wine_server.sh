#!/bin/bash
# Start the MT5 Wine RPyC bridge with the correct WINEPREFIX.
export WINEPREFIX="/Users/bank/Library/Application Support/net.metaquotes.wine.metatrader5"
export WINEDEBUG=-all
export MT5_WINE_HOST=127.0.0.1
export MT5_WINE_PORT=18812

WINE_BIN="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"
WINPY="C:\\winpython\\python.exe"
SCRIPT="/Volumes/AI_DRIVE/trading bot/chain_gambler-main/tools/mt5_wine_server.py"

exec "$WINE_BIN" "$WINPY" "$SCRIPT"
