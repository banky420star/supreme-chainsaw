"""
Enable Micro Account Trading

Configures the system to trade with $50-100 equity.
WARNING: This is high-risk trading with minimal capital.
"""
import os
import sys
import json
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def reset_risk_tracking():
    """Reset risk tracking to start fresh with current equity."""
    try:
        # Call API to reset peak equity
        response = requests.post(
            "http://localhost:5050/api/control",
            json={"action": "reset_peak_equity"},
            timeout=5
        )
        if response.ok:
            print("[OK] Risk tracking reset")
            return True
        else:
            print(f"[WARN] Could not reset via API: {response.status_code}")
            return False
    except Exception as e:
        print(f"[WARN] API not available: {e}")
        return False

def check_account():
    """Check current account status."""
    try:
        response = requests.get("http://localhost:5050/api/status", timeout=5)
        if response.ok:
            data = response.json()
            equity = data.get("account", {}).get("equity", 0)
            balance = data.get("account", {}).get("balance", 0)
            print(f"[INFO] Account Equity: ${equity:.2f}")
            print(f"[INFO] Account Balance: ${balance:.2f}")
            return equity
    except Exception as e:
        print(f"[WARN] Could not check account: {e}")
        return 0

def enable_trading():
    """Enable trading via API."""
    try:
        response = requests.post(
            "http://localhost:5050/api/control",
            json={"action": "unblock"},
            timeout=5
        )
        if response.ok:
            print("[OK] Trading unblocked")
            return True
        else:
            print(f"[FAIL] Could not unblock: {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] API error: {e}")
        return False

def main():
    print("=" * 60)
    print("MICRO ACCOUNT TRADING ENABLE")
    print("=" * 60)
    print()
    print("WARNING: Trading with < $100 is EXTREMELY HIGH RISK")
    print("You can lose your entire account in 1-2 trades.")
    print()

    # Check account
    equity = check_account()
    if equity < 50:
        print(f"[ERROR] Equity too low (${equity:.2f}). Need at least $50.")
        return 1

    print(f"[OK] Equity sufficient: ${equity:.2f}")
    print()

    # Calculate position size
    risk_per_trade = equity * 0.05  # 5% risk
    print(f"Risk per trade: ${risk_per_trade:.2f} (5% of equity)")

    # For EURUSD, 0.01 lot = $0.10 per pip
    # With 10 pip SL = $1 risk
    # With $54 and 5% risk = $2.70 per trade
    # Can trade 0.01 lots with 20-25 pip stops
    print(f"Recommended: 0.01 lots with 20-25 pip stops")
    print()

    # Reset risk tracking
    print("Resetting risk tracking...")
    reset_risk_tracking()
    print()

    # Enable trading
    print("Enabling trading...")
    if enable_trading():
        print()
        print("=" * 60)
        print("MICRO TRADING ENABLED")
        print("=" * 60)
        print()
        print("Configuration:")
        print(f"  - Equity: ${equity:.2f}")
        print(f"  - Risk per trade: 5% (${risk_per_trade:.2f})")
        print(f"  - Position size: 0.01 lots (fixed)")
        print(f"  - Max positions: 1")
        print(f"  - Symbol: EURUSDm only")
        print()
        print("Commands to run:")
        print("  1. python start_live.py --config config_micro_account.yaml --live")
        print("  2. Monitor at: http://localhost:4182")
        print()
        print("EMERGENCY STOP:")
        print("  curl -X POST http://localhost:5050/api/control \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"action\": \"emergency_stop\"}'")
        print()
        return 0
    else:
        print("[FAIL] Could not enable trading")
        return 1

if __name__ == "__main__":
    sys.exit(main())
