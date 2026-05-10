#!/usr/bin/env python3
"""
Test MT5 bridge contract (native or Wine RPyC).

Run from the project root:
    python tools/test_mt5_bridge_contract.py

Exits with code 0 if all assertions pass, 1 otherwise.
"""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from Python.mt5_compat import mt5, MT5_AVAILABLE


def test_initialize() -> bool:
    ok = mt5.initialize()
    print(f"mt5.initialize() -> {ok}")
    return bool(ok)


def test_terminal_info() -> bool:
    ti = mt5.terminal_info()
    connected = getattr(ti, "connected", False)
    print(f"mt5.terminal_info().connected -> {connected}")
    return bool(connected)


def test_account_info() -> bool:
    info = mt5.account_info()
    print(f"mt5.account_info() -> {info}")
    if info is None:
        print("FAIL: account_info is None")
        return False

    login = getattr(info, "login", None)
    server = getattr(info, "server", None)
    balance = getattr(info, "balance", None)
    equity = getattr(info, "equity", None)

    if not login:
        print(f"FAIL: login missing ({login})")
        return False
    if not server:
        print(f"FAIL: server missing ({server})")
        return False
    if balance is None or balance <= 0:
        print(f"FAIL: balance <= 0 or missing ({balance})")
        return False
    if equity is None or equity <= 0:
        print(f"FAIL: equity <= 0 or missing ({equity})")
        return False

    print(f"PASS: login={login}, server={server}, balance={balance}, equity={equity}")
    return True


def test_symbol_ticks() -> bool:
    symbols = ["BTCUSDm", "XAUUSDm"]
    for sym in symbols:
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            print(f"FAIL: tick for {sym} is None")
            return False
        bid = getattr(tick, "bid", None)
        ask = getattr(tick, "ask", None)
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            print(f"FAIL: {sym} bid/ask invalid (bid={bid}, ask={ask})")
            return False
        print(f"PASS: {sym} bid={bid}, ask={ask}")
    return True


def test_positions_get() -> bool:
    positions = mt5.positions_get()
    if positions is None:
        positions = []
    print(f"mt5.positions_get() returned {len(positions)} positions")
    return isinstance(positions, list)


def main() -> int:
    if not MT5_AVAILABLE:
        print("FAIL: MT5 not available")
        return 1

    results = [
        ("initialize", test_initialize()),
        ("terminal_info", test_terminal_info()),
        ("account_info", test_account_info()),
        ("symbol_ticks", test_symbol_ticks()),
        ("positions_get", test_positions_get()),
    ]

    print("\n--- Summary ---")
    all_pass = True
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"{name}: {status}")
        if not ok:
            all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
