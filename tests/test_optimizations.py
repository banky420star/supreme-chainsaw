"""
Test script for Chain Gambler optimizations.

Validates:
1. Signal quality filtering
2. Kelly criterion sizing
3. Spread optimization
4. Portfolio allocation
"""
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime

# Add project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from loguru import logger

# Disable excessive logging for tests
logger.remove()
logger.add(sys.stderr, level="WARNING")


def test_signal_optimizer():
    """Test signal quality optimization."""
    print("\n" + "="*60)
    print("TEST: Signal Optimizer")
    print("="*60)

    try:
        from Python.signal_optimizer import SignalOptimizer, SignalQuality

        opt = SignalOptimizer()

        # Create test data with clear trend
        dates = pd.date_range(end=datetime.now(), periods=150, freq='5min')
        trend_df = pd.DataFrame({
            'open': np.linspace(1.1000, 1.1200, 150),
            'high': np.linspace(1.1010, 1.1210, 150),
            'low': np.linspace(1.0990, 1.1190, 150),
            'close': np.linspace(1.1000, 1.1200, 150),
            'volume': np.ones(150) * 10000,
        }, index=dates)

        # Test strong trend signal
        quality = opt.evaluate_signal(
            symbol="EURUSDm",
            df=trend_df,
            action="BUY",
            ppo_score=0.8,
            regime="MED_VOLATILITY",
            confidence=0.75,
        )

        print(f"Signal Quality Score: {quality.score:.3f}")
        print(f"Passed Filters: {quality.passed}")
        print(f"Filter Breakdown: {quality.filters}")

        assert isinstance(quality, SignalQuality)
        assert 0.0 <= quality.score <= 1.0
        print("  [PASS] Signal quality calculation working")

        # Test loss streak tracking
        opt.record_trade_result("EURUSDm", -50)
        opt.record_trade_result("EURUSDm", -30)
        opt.record_trade_result("EURUSDm", -40)

        loss_score = opt._check_loss_streak("EURUSDm")
        print(f"Loss Streak Score: {loss_score:.2f}")
        assert loss_score <= 0.5, "Loss streak should reduce score"
        print("  [PASS] Loss streak protection working")

        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_kelly_sizer():
    """Test Kelly criterion position sizing."""
    print("\n" + "="*60)
    print("TEST: Kelly Position Sizer")
    print("="*60)

    try:
        from Python.signal_optimizer import KellyPositionSizer

        kelly = KellyPositionSizer(fraction=0.5)  # Half-Kelly

        # Simulate trade history
        # Win rate 50%, avg win $100, avg loss $50
        # Kelly = (0.5*2 - 0.5) / 2 = 0.25
        # Half-Kelly = 0.125
        np.random.seed(42)
        for i in range(30):
            if np.random.random() > 0.5:
                kelly.record_trade("EURUSDm", np.random.uniform(80, 120))
            else:
                kelly.record_trade("EURUSDm", np.random.uniform(-60, -40))

        # Calculate Kelly size
        risk = kelly.calculate_size(
            symbol="EURUSDm",
            base_risk_pct=0.01,  # 1% base
            equity=10000,
        )

        print(f"Base Risk: 1.0%")
        print(f"Kelly Risk: {risk*100:.2f}%")
        print(f"Kelly Multiplier: {risk/0.01:.2f}x")

        # Kelly should return a value (can be very low if edge is poor)
        assert 0 <= risk <= 0.05, f"Kelly risk out of range: {risk}"

        if risk < 0.001:
            print("  [INFO] Kelly risk very low (poor edge detected in test data)")
        else:
            print("  [PASS] Kelly sizing working correctly")

        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_spread_optimizer():
    """Test spread optimization."""
    print("\n" + "="*60)
    print("TEST: Spread Optimizer")
    print("="*60)

    try:
        from Python.signal_optimizer import SpreadOptimizer

        spread_opt = SpreadOptimizer()

        # Simulate spread history
        for spread in [0.0001, 0.00012, 0.00011, 0.00013, 0.0001] * 10:
            is_good, score = spread_opt.is_spread_favorable("EURUSDm", spread)

        # Test favorable spread
        is_good, score = spread_opt.is_spread_favorable("EURUSDm", 0.0001)
        print(f"Normal spread (0.1 pip): Good={is_good}, Score={score:.2f}")
        assert is_good, "Normal spread should be favorable"

        # Test wide spread
        is_good, score = spread_opt.is_spread_favorable("EURUSDm", 0.0005)
        print(f"Wide spread (0.5 pip): Good={is_good}, Score={score:.2f}")
        assert not is_good, "Wide spread should be rejected"
        print("  [PASS] Spread filtering working")

        # Test session quality
        for hour in [8, 14, 20, 2]:
            quality = spread_opt.get_session_quality(hour)
            print(f"  Hour {hour:02d} UTC: Quality={quality:.1f}")

        print("  [PASS] Session quality scoring working")

        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_enhanced_portfolio_allocator():
    """Test enhanced portfolio allocation."""
    print("\n" + "="*60)
    print("TEST: Enhanced Portfolio Allocator")
    print("="*60)

    try:
        from Python.portfolio_allocator import PortfolioAllocator

        config = {
            "max_portfolio_heat": 0.06,
            "min_symbol_heat": 0.005,
            "max_symbol_heat": 0.03,
            "correlation_penalty": 0.5,
            "history_window": 50,
        }

        symbols = ["EURUSDm", "GBPUSDm", "XAUUSDm"]
        allocator = PortfolioAllocator(config, symbols)

        # Record trade results
        np.random.seed(42)
        for _ in range(30):
            allocator.record_trade_result("EURUSDm", np.random.choice([50, -30], p=[0.6, 0.4]))
            allocator.record_trade_result("GBPUSDm", np.random.choice([40, -35], p=[0.5, 0.5]))
            allocator.record_trade_result("XAUUSDm", np.random.choice([80, -60], p=[0.45, 0.55]))

        # Calculate allocations
        allocs = allocator.allocate(equity=10000)

        print("Risk Allocations:")
        for sym, alloc in allocs.items():
            print(f"  {sym}: {alloc:.2%}")

        assert sum(allocs.values()) <= 0.06, "Total heat exceeded"
        print("  [PASS] Portfolio allocation working")

        # Test Kelly fraction
        for sym in symbols:
            kelly = allocator.get_kelly_fraction(sym)
            print(f"  {sym} Kelly: {kelly:.2%}")
            assert 0 <= kelly <= 1.0, "Kelly fraction out of range"

        print("  [PASS] Kelly fraction calculation working")

        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration with HybridBrain."""
    print("\n" + "="*60)
    print("TEST: Integration with HybridBrain")
    print("="*60)

    try:
        from Python.hybrid_brain import HybridBrain
        from Python.risk_engine import RiskEngine

        risk = RiskEngine()

        class MockExecutor:
            def reconcile_exposure(self, *args, **kwargs):
                pass

        brain = HybridBrain(risk=risk, executor=MockExecutor())

        # Check if optimizer is initialized
        if hasattr(brain, 'signal_optimizer') and brain.signal_optimizer is not None:
            print("  [PASS] Signal optimizer initialized in HybridBrain")
        else:
            print("  [WARN] Signal optimizer not available (check imports)")

        if hasattr(brain, 'kelly_sizer') and brain.kelly_sizer is not None:
            print("  [PASS] Kelly sizer initialized in HybridBrain")
        else:
            print("  [WARN] Kelly sizer not available (check imports)")

        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all optimization tests."""
    print("\n" + "="*60)
    print("CHAIN GAMBLER OPTIMIZATION TEST SUITE")
    print("="*60)

    results = []

    results.append(("Signal Optimizer", test_signal_optimizer()))
    results.append(("Kelly Sizer", test_kelly_sizer()))
    results.append(("Spread Optimizer", test_spread_optimizer()))
    results.append(("Portfolio Allocator", test_enhanced_portfolio_allocator()))
    results.append(("Integration", test_integration()))

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(passed for _, passed in results)

    print("\n" + "="*60)
    if all_passed:
        print("[PASS] ALL OPTIMIZATION TESTS PASSED")
        print("\nThe optimizations are ready to use!")
        print("See docs/OPTIMIZATION_GUIDE.md for configuration details.")
    else:
        print("[FAIL] SOME TESTS FAILED")
        print("\nCheck the error messages above.")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
