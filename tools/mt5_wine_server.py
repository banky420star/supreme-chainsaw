#!/usr/bin/env python3
"""
RPyC server that exposes MetaTrader5 from inside Wine.
Uses classic SlaveService so macOS can do conn.eval("mt5.account_info()").
Run this inside the Wine Python environment:

  WINEPREFIX="~/Library/Application Support/net.metaquotes.wine.metatrader5" \
    /Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64 \
    C:\\winpython\\python.exe tools/mt5_wine_server.py
"""
from __future__ import annotations

import os
import sys

import rpyc
from rpyc.utils.server import ThreadedServer
from rpyc.core import SlaveService

HOST = os.environ.get("MT5_WINE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MT5_WINE_PORT", "18812"))


class MT5WineService(SlaveService):
    """SlaveService that pre-imports MetaTrader5 and datetime into the exposed namespace."""

    def on_connect(self, conn):
        super().on_connect(conn)
        conn.execute("import MetaTrader5 as mt5")
        conn.execute("import datetime")


def main():
    print(f"[mt5-wine-server] Starting RPyC classic server on {HOST}:{PORT}")
    t = ThreadedServer(
        MT5WineService,
        hostname=HOST,
        port=PORT,
        reuse_addr=True,
    )
    print("[mt5-wine-server] Ready. Waiting for macOS connections...")
    try:
        t.start()
    except KeyboardInterrupt:
        print("[mt5-wine-server] Stopping.")
        t.close()


if __name__ == "__main__":
    main()
