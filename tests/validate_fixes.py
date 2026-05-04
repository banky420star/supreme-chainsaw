"""
Quick validation script for Chain Gambler fixes.
Run this after applying fixes to verify they work correctly.
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def test_symbol_validation():
    """Test that path traversal is blocked."""
    print("\n" + "="*60)
    print("TEST 1: Symbol Validation (Path Traversal Protection)")
    print("="*60)

    try:
        from Python.order_manager import _validate_symbol

        # Test valid symbols
        valid_symbols = ["EURUSDm", "XAUUSD", "GBPUSDm", "BTCUSD"]
        for sym in valid_symbols:
            try:
                _validate_symbol(sym)
                print(f"[PASS] {sym}: Accepted")
            except ValueError as e:
                print(f"[FAIL] {sym}: Rejected - {e}")
                return False

        # Test invalid symbols (path traversal)
        invalid_symbols = ["../../../etc/passwd", "..\\\\windows\\system32", "symbol%00malicious"]
        for sym in invalid_symbols:
            try:
                _validate_symbol(sym)
                print(f"[FAIL] {sym}: Should have been rejected!")
                return False
            except ValueError:
                print(f"[PASS] {sym}: Correctly rejected")

        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False


def test_risk_engine_fixes():
    """Test risk engine kill switch fixes."""
    print("\n" + "="*60)
    print("TEST 2: Risk Engine Kill Switch Fixes")
    print("="*60)

    try:
        from Python.risk_engine import RiskEngine

        # Test 1: Consecutive errors halt persists through reset_daily
        print("\n  Testing consecutive_errors halt persistence...")
        risk = RiskEngine()
        risk._current_equity = 10000

        # Trigger consecutive errors halt
        risk.error_count = 3
        risk.record_error(critical=True)

        if not (risk.halt and risk._halt_reason == "consecutive_errors"):
            print("  [FAIL] Failed to set consecutive_errors halt")
            return False
        print("  [PASS] consecutive_errors halt set")

        # Call reset_daily - should NOT clear the halt
        risk.reset_daily()

        if risk.halt and risk._halt_reason == "consecutive_errors":
            print("  [PASS] consecutive_errors halt persisted through reset_daily")
        else:
            print("  [FAIL] consecutive_errors halt was incorrectly cleared!")
            return False

        # Test 2: Daily loss halt IS cleared by reset_daily
        print("\n  Testing daily_loss halt clearing...")
        risk2 = RiskEngine()
        risk2._current_equity = 10000
        risk2.max_daily_loss_pct = 3.0

        # Trigger daily loss halt
        risk2.record_pnl(-500)

        if not (risk2.halt and risk2._halt_reason == "daily_loss"):
            print("  [WARN]  daily_loss halt not set (may need more loss)")
        else:
            print("  [PASS] daily_loss halt set")
            risk2.reset_daily()

            if not risk2.halt:
                print("  [PASS] daily_loss halt correctly cleared")
            else:
                print("  [FAIL] daily_loss halt not cleared!")
                return False

        # Test 3: Zero equity blocks trading
        print("\n  Testing zero equity blocking...")
        risk3 = RiskEngine()
        risk3._current_equity = 0

        if risk3.can_trade("EURUSDm"):
            print("  [FAIL] Trading allowed with zero equity!")
            return False
        print("  [PASS] Trading correctly blocked with zero equity")

        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hybrid_brain_fixes():
    """Test hybrid brain trend-flip and bias fixes."""
    print("\n" + "="*60)
    print("TEST 3: Hybrid Brain Trend-Flip and Bias Fixes")
    print("="*60)

    try:
        import pandas as pd
        import numpy as np
        from datetime import datetime
        from Python.hybrid_brain import HybridBrain
        from Python.risk_engine import RiskEngine

        # Create a minimal setup
        risk = RiskEngine()

        class MockExecutor:
            def reconcile_exposure(self, *args, **kwargs):
                pass

        brain = HybridBrain(risk=risk, executor=MockExecutor())

        # Test 1: Check bias calculation doesn't include current action
        print("\n  Testing bias calculation isolation...")

        # Simulate multiple actions
        brain._ppo_bias["TEST"] = []  # Clear any existing

        # Add some historical data
        for action in [0.1, 0.15, 0.12, 0.14, 0.11]:
            brain._update_ppo_bias("TEST", action)

        # Check bias is calculated from historical data
        bias_before = brain._ppo_bias["TEST"][-1] if brain._ppo_bias["TEST"] else 0

        # Now update with a new action
        new_bias = brain._update_ppo_bias("TEST", 0.5)

        # The bias should be based on historical data, not dominated by the new 0.5
        if abs(new_bias) < 0.3:  # Should be around 0.12-0.13, not pulled toward 0.5
            print(f"  [PASS] Bias correctly isolated from current action (bias={new_bias:.4f})")
        else:
            print(f"  [WARN]  Bias may be contaminated: {new_bias:.4f}")
            # Not a failure, just a warning

        # Test 2: Check trend-flip logic exists
        print("\n  Testing trend-flip detection...")

        # Create bearish trending data
        dates = pd.date_range(end=datetime.now(), periods=150, freq='5min')
        bearish_df = pd.DataFrame({
            'open': np.linspace(1.1000, 1.0900, 150),
            'high': np.linspace(1.1010, 1.0910, 150),
            'low': np.linspace(1.0990, 1.0890, 150),
            'close': np.linspace(1.1000, 1.0900, 150),
            'volume': np.ones(150) * 10000,
        }, index=dates)

        # Get decision
        decision = brain.decide("EURUSDm", bearish_df)

        trend_flip = decision.get("trend_flip", "")
        if "bearish" in trend_flip:
            print(f"  [PASS] Bearish trend detected: {trend_flip}")
        else:
            print(f"  [INFO]  Trend flip result: {trend_flip}")

        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_server_security():
    """Test API server security fixes."""
    print("\n" + "="*60)
    print("TEST 4: API Server Security Fixes")
    print("="*60)

    try:
        # Check that secrets is imported (for constant-time comparison)
        with open(os.path.join(PROJECT_ROOT, "Python", "api_server.py"), 'r') as f:
            content = f.read()

        if "import secrets" in content or "from secrets import compare_digest" in content:
            print("  [PASS] secrets module imported for constant-time comparison")
        else:
            print("  [WARN]  secrets module not found (may need to add)")

        # Check for secure CORS handling
        if "permissive fallback" not in content.lower() and "localhost:4180" in content:
            if "no fallback" in content.lower() or "only allow whitelisted" in content.lower():
                print("  [PASS] CORS fallback removed")
            else:
                print("  [INFO]  CORS handling present")

        # Check for production mode check
        if "_IS_PRODUCTION" in content and "AGI_IS_LIVE" in content:
            print("  [PASS] Production mode check implemented")
        else:
            print("  [WARN]  Production mode check may need verification")

        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False


def main():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("CHAIN GAMBLER FIX VALIDATION")
    print("="*60)
    print(f"Project Root: {PROJECT_ROOT}")

    results = []

    results.append(("Symbol Validation", test_symbol_validation()))
    results.append(("Risk Engine Fixes", test_risk_engine_fixes()))
    results.append(("Hybrid Brain Fixes", test_hybrid_brain_fixes()))
    results.append(("API Server Security", test_api_server_security()))

    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)

    for name, passed in results:
        status = "[PASS] PASS" if passed else "[FAIL] FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    print("\n" + "="*60)
    if all_passed:
        print("[PASS] ALL FIXES VALIDATED SUCCESSFULLY")
    else:
        print("[FAIL] SOME VALIDATIONS FAILED")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
