"""
Quick connectivity test for the provided Exness MT5 Trial account.

Usage:
    python scripts/test_mt5_connection.py

It will attempt to initialize with the hardcoded trial credentials
(Login: 435656990, Server: Exness-MT5Trial9).

Make sure the MT5 terminal is running and logged in first.
"""

import MetaTrader5 as mt5
import os
from datetime import datetime

# Credentials: prefer environment (set via scripts\set_exness_trial_env.ps1 or manually).
# Hardcoded fallbacks are for the Exness MT5 Trial account only.
LOGIN = int(os.environ.get("MT5_LOGIN", "435656990"))
PASSWORD = os.environ.get("MT5_PASSWORD", "Fuckyou2/")
SERVER = os.environ.get("MT5_SERVER", "Exness-MT5Trial9")

print("=== Exness MT5 Trial Connection Test ===")
print(f"Login : {LOGIN}")
print(f"Server: {SERVER}")
print()

# Attempt initialization
if not mt5.initialize():
    print("initialize() failed")
    print(mt5.last_error())
    mt5.shutdown()
    exit(1)

print("MetaTrader5 package initialized successfully.")

# Login explicitly (in case terminal is not already logged in)
authorized = mt5.login(LOGIN, password=PASSWORD, server=SERVER)
if not authorized:
    print("Login failed!")
    print(mt5.last_error())
    mt5.shutdown()
    exit(1)

print("Login successful.")

# Get account info
account_info = mt5.account_info()
if account_info is not None:
    print("\nAccount Info:")
    print(f"  Login:    {account_info.login}")
    print(f"  Server:   {account_info.server}")
    print(f"  Balance:  {account_info.balance}")
    print(f"  Equity:   {account_info.equity}")
    print(f"  Margin:   {account_info.margin}")
    print(f"  Currency: {account_info.currency}")
else:
    print("Failed to get account info")

# Test symbol data (important for training)
print("\nTesting symbol data fetch...")
symbols = ["BTCUSDm", "XAUUSDm", "EURUSDm"]
for sym in symbols:
    symbol_info = mt5.symbol_info(sym)
    if symbol_info is not None:
        print(f"  {sym}: visible={symbol_info.visible}, digits={symbol_info.digits}")
    else:
        print(f"  {sym}: Not found (may need to add in Market Watch)")

print("\n=== Connection Test Completed Successfully ===")
mt5.shutdown()
