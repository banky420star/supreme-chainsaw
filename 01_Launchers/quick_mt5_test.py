import MetaTrader5 as mt5
import os
import sys

# Prefer env (run scripts\set_exness_trial_env.ps1 first). Hardcoded = Exness trial fallback.
LOGIN = int(os.environ.get("MT5_LOGIN", "435656990"))
PASSWORD = os.environ.get("MT5_PASSWORD", "Fuckyou2/")
SERVER = os.environ.get("MT5_SERVER", "Exness-MT5Trial9")

print("Testing MT5 connection with provided Exness Trial credentials...")

if not mt5.initialize():
    print("FAILED: mt5.initialize()")
    print(mt5.last_error())
    sys.exit(1)

print("Package initialized.")

if not mt5.login(LOGIN, PASSWORD, SERVER):
    print("FAILED: Login")
    print(mt5.last_error())
    mt5.shutdown()
    sys.exit(1)

print("Login successful!")

acc = mt5.account_info()
if acc:
    print(f"Account: {acc.login} on {acc.server}")
    print(f"Balance: {acc.balance} {acc.currency}")
    print(f"Equity:  {acc.equity}")

print("\nSUCCESS - MT5 is ready for Chain Gambler.")
mt5.shutdown()
