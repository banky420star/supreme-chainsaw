"""
Comprehensive Testing Framework for Chain Gambler Trading System

This module provides:
1. MT5 historical data downloading for backtesting
2. Full trading cycle simulation with all fixed components
3. Safety validation tests for kill switches and risk management
4. Performance reporting and validation

Usage:
    python -m tests.test_chain_gambler_comprehensive --download-data --symbols EURUSDm GBPUSDm XAUUSDm
    python -m tests.test_chain_gambler_comprehensive --run-simulation --days 30
    python -m tests.test_chain_gambler_comprehensive --full-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

# Configure logging for tests
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(PROJECT_ROOT / "logs" / "test_framework.log", rotation="10 MB", level="DEBUG")

# Test configuration
TEST_CONFIG = {
    "symbols": ["EURUSDm", "GBPUSDm", "XAUUSDm", "BTCUSDm"],
    "timeframes": ["M5", "M15", "H1"],
    "test_days": 30,
    "data_dir": PROJECT_ROOT / "tests" / "data",
    "results_dir": PROJECT_ROOT / "tests" / "results",
}


@dataclass
class TestResult:
    """Result of a single test case."""
    name: str
    passed: bool
    duration_ms: float
    error_message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class MT5DataDownloader:
    """Download historical data from MT5 for testing."""

    def __init__(self):
        self._mt5 = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to MT5 terminal."""
        if self.connected:
            return True

        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5

            if not mt5.initialize():
                logger.error("MT5 initialize failed")
                return False

            self.connected = True
            logger.success("Connected to MT5")
            return True

        except ImportError:
            logger.warning("MetaTrader5 not installed, using synthetic data")
            return False
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from MT5."""
        if self._mt5 and self.connected:
            self._mt5.shutdown()
            self.connected = False

    def download_data(
        self,
        symbol: str,
        timeframe: str = "M5",
        days: int = 30,
        save: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Download historical data from MT5.

        Args:
            symbol: Trading symbol (e.g., "EURUSDm")
            timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1)
            days: Number of days to download
            save: Whether to save to file

        Returns:
            DataFrame with OHLCV data or None if failed
        """
        if not self.connect():
            logger.info(f"Generating synthetic data for {symbol}")
            return self._generate_synthetic_data(symbol, days)

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": self._mt5.TIMEFRAME_M1,
            "M5": self._mt5.TIMEFRAME_M5,
            "M15": self._mt5.TIMEFRAME_M15,
            "M30": self._mt5.TIMEFRAME_M30,
            "H1": self._mt5.TIMEFRAME_H1,
            "H4": self._mt5.TIMEFRAME_H4,
            "D1": self._mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, self._mt5.TIMEFRAME_M5)

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            rates = self._mt5.copy_rates_range(symbol, mt5_tf, start_date, end_date)
            if rates is None or len(rates) == 0:
                logger.warning(f"No data returned for {symbol}")
                return None

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)

            logger.success(f"Downloaded {len(df)} bars for {symbol} ({timeframe})")

            if save:
                self._save_data(df, symbol, timeframe)

            return df

        except Exception as e:
            logger.error(f"Error downloading {symbol}: {e}")
            return None

    def _generate_synthetic_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing."""
        np.random.seed(42)  # Reproducible

        # Generate timestamps (5-minute bars)
        periods = days * 24 * 12  # 5-min bars per day
        dates = pd.date_range(
            end=datetime.now(),
            periods=periods,
            freq='5min',
            tz='UTC'
        )

        # Base price depends on symbol
        base_price = {
            "EURUSD": 1.0850, "EURUSDm": 1.0850,
            "GBPUSD": 1.2650, "GBPUSDm": 1.2650,
            "USDJPY": 151.50, "USDJPYm": 151.50,
            "XAUUSD": 2350.00, "XAUUSDm": 2350.00,
            "BTCUSD": 65000.00, "BTCUSDm": 65000.00,
        }.get(symbol, 100.0)

        # Generate random walk
        returns = np.random.normal(0, 0.0002, periods)
        if "XAU" in symbol:
            returns = np.random.normal(0, 0.0008, periods)  # Gold more volatile
        elif "BTC" in symbol:
            returns = np.random.normal(0, 0.0020, periods)  # Bitcoin most volatile

        closes = base_price * np.exp(np.cumsum(returns))

        # Generate OHLC from close
        data = {
            'open': closes * (1 + np.random.normal(0, 0.0001, periods)),
            'high': closes * (1 + abs(np.random.normal(0, 0.0003, periods))),
            'low': closes * (1 - abs(np.random.normal(0, 0.0003, periods))),
            'close': closes,
            'volume': np.random.randint(1000, 100000, periods),
        }

        df = pd.DataFrame(data, index=dates)
        df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1))
        df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1))

        logger.info(f"Generated {len(df)} synthetic bars for {symbol}")
        return df

    def _save_data(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """Save data to CSV file."""
        TEST_CONFIG["data_dir"].mkdir(parents=True, exist_ok=True)

        filename = f"{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = TEST_CONFIG["data_dir"] / filename

        df.to_csv(filepath)
        logger.info(f"Saved data to {filepath}")


class TradingSimulator:
    """Simulate full trading cycles with all components."""

    def __init__(self, test_equity: float = 10000.0):
        self.equity = test_equity
        self.initial_equity = test_equity
        self.trades: List[Dict] = []
        self.risk_events: List[Dict] = []
        self.decisions: List[Dict] = []

        # Initialize components
        self._init_components()

    def _init_components(self):
        """Initialize all trading components."""
        try:
            from Python.risk_engine import RiskEngine
            from Python.risk_supervisor import RiskSupervisor
            from Python.hybrid_brain import HybridBrain
            from Python.order_manager import OrderManager

            self.risk_engine = RiskEngine()
            self.risk_supervisor = RiskSupervisor()
            self.order_manager = OrderManager(executor=None)  # Dry-run mode

            # Initialize brain with dry-run executor
            class DummyExecutor:
                def reconcile_exposure(self, *args, **kwargs):
                    pass

            self.brain = HybridBrain(
                risk=self.risk_engine,
                executor=DummyExecutor(),
            )

            logger.success("Trading components initialized")

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise

    def simulate_trading_day(
        self,
        symbol: str,
        df: pd.DataFrame,
        max_trades: int = 10
    ) -> Dict[str, Any]:
        """
        Simulate a full trading day.

        Args:
            symbol: Trading symbol
            df: OHLCV DataFrame
            max_trades: Maximum trades per day

        Returns:
            Simulation results
        """
        day_results = {
            "symbol": symbol,
            "bars_processed": len(df),
            "trades_taken": 0,
            "decisions_made": 0,
            "pnl": 0.0,
            "risk_events": [],
            "errors": [],
        }

        # Process each bar
        for i in range(100, len(df), 5):  # Step by 5 bars, start after 100 for feature window
            try:
                window = df.iloc[i-100:i]

                # Update equity
                self.risk_engine.update_equity(self.equity)

                # Get decision from brain
                decision = self.brain.decide(symbol, window)
                day_results["decisions_made"] += 1
                self.decisions.append(decision)

                # Simulate trade execution
                if decision["action"] != "HOLD" and day_results["trades_taken"] < max_trades:
                    if self.risk_engine.can_trade(symbol):
                        trade_result = self._simulate_trade(symbol, decision, window)
                        if trade_result:
                            day_results["trades_taken"] += 1
                            self.trades.append(trade_result)
                            self.equity += trade_result.get("pnl", 0)

                # Check risk events
                if self.risk_engine.halt:
                    day_results["risk_events"].append({
                        "time": window.index[-1],
                        "reason": self.risk_engine._halt_reason,
                        "equity": self.equity,
                    })

            except Exception as e:
                error_msg = f"Error at bar {i}: {e}"
                logger.error(error_msg)
                day_results["errors"].append(error_msg)

        day_results["pnl"] = self.equity - self.initial_equity
        return day_results

    def _simulate_trade(
        self,
        symbol: str,
        decision: Dict,
        df: pd.DataFrame
    ) -> Optional[Dict]:
        """Simulate a single trade execution."""
        current_price = df["close"].iloc[-1]
        action = decision["action"]
        exposure = decision.get("exposure", 0)

        # Calculate position size
        lot_size = abs(exposure) * 0.01  # Simplified sizing

        # Simulate SL/TP
        atr = df["high"].rolling(14).max().iloc[-1] - df["low"].rolling(14).min().iloc[-1]
        sl_distance = atr * 2
        tp_distance = atr * 3

        if action == "BUY":
            sl = current_price - sl_distance
            tp = current_price + tp_distance
        else:  # SELL
            sl = current_price + sl_distance
            tp = current_price - tp_distance

        # Simulate trade outcome (simplified random outcome)
        np.random.seed(int(time.time() * 1000) % 10000)
        outcome = np.random.choice(["win", "loss", "breakeven"], p=[0.35, 0.35, 0.30])

        if outcome == "win":
            pnl = lot_size * 100 * tp_distance
        elif outcome == "loss":
            pnl = -lot_size * 100 * sl_distance
        else:
            pnl = 0

        return {
            "symbol": symbol,
            "action": action,
            "entry_price": current_price,
            "lot_size": lot_size,
            "sl": sl,
            "tp": tp,
            "outcome": outcome,
            "pnl": pnl,
            "decision": decision,
        }


class SafetyValidator:
    """Validate safety mechanisms like kill switches."""

    @staticmethod
    def test_kill_switches() -> List[TestResult]:
        """Test all kill switch scenarios."""
        results = []

        # Test 1: Daily loss kill switch
        try:
            from Python.risk_engine import RiskEngine

            start = time.time()
            risk = RiskEngine()
            risk._current_equity = 10000
            risk.max_daily_loss_pct = 3.0

            # Simulate losses
            risk.record_pnl(-150)  # Should trigger kill switch at -$300
            risk.record_pnl(-150)
            risk.record_pnl(-100)  # Total -400, should trigger

            passed = risk.halt and risk._halt_reason == "daily_loss"
            duration = (time.time() - start) * 1000

            results.append(TestResult(
                name="Daily Loss Kill Switch",
                passed=passed,
                duration_ms=duration,
                details={"halt": risk.halt, "reason": risk._halt_reason}
            ))
        except Exception as e:
            results.append(TestResult(
                name="Daily Loss Kill Switch",
                passed=False,
                duration_ms=0,
                error_message=str(e)
            ))

        # Test 2: Daily reset only clears daily_loss
        try:
            from Python.risk_engine import RiskEngine

            start = time.time()
            risk = RiskEngine()
            risk._current_equity = 10000

            # Trigger consecutive errors halt
            risk.error_count = 3
            risk.record_error(critical=True)  # Should set halt
            assert risk.halt and risk._halt_reason == "consecutive_errors"

            # Reset daily - should NOT clear consecutive_errors
            risk.reset_daily()

            passed = risk.halt and risk._halt_reason == "consecutive_errors"
            duration = (time.time() - start) * 1000

            results.append(TestResult(
                name="Reset Daily Preserves Non-Daily Halts",
                passed=passed,
                duration_ms=duration,
                details={"halt": risk.halt, "reason": risk._halt_reason}
            ))
        except Exception as e:
            results.append(TestResult(
                name="Reset Daily Preserves Non-Daily Halts",
                passed=False,
                duration_ms=0,
                error_message=str(e)
            ))

        # Test 3: Equity validation
        try:
            from Python.risk_engine import RiskEngine

            start = time.time()
            risk = RiskEngine()
            risk._current_equity = 0

            can_trade = risk.can_trade("EURUSDm")

            passed = not can_trade  # Should NOT be able to trade with $0
            duration = (time.time() - start) * 1000

            results.append(TestResult(
                name="Zero Equity Blocks Trading",
                passed=passed,
                duration_ms=duration,
                details={"equity": risk._current_equity, "can_trade": can_trade}
            ))
        except Exception as e:
            results.append(TestResult(
                name="Zero Equity Blocks Trading",
                passed=False,
                duration_ms=0,
                error_message=str(e)
            ))

        return results

    @staticmethod
    def test_symbol_validation() -> List[TestResult]:
        """Test symbol validation for path traversal."""
        results = []

        try:
            from Python.order_manager import _validate_symbol

            # Test valid symbols
            start = time.time()
            try:
                _validate_symbol("EURUSDm")
                _validate_symbol("XAUUSD")
                passed = True
            except ValueError:
                passed = False

            results.append(TestResult(
                name="Valid Symbol Acceptance",
                passed=passed,
                duration_ms=(time.time() - start) * 1000
            ))

            # Test path traversal rejection
            start = time.time()
            try:
                _validate_symbol("../../../etc/passwd")
                passed = False  # Should have raised
            except ValueError:
                passed = True

            results.append(TestResult(
                name="Path Traversal Rejection",
                passed=passed,
                duration_ms=(time.time() - start) * 1000
            ))

        except Exception as e:
            results.append(TestResult(
                name="Symbol Validation",
                passed=False,
                duration_ms=0,
                error_message=str(e)
            ))

        return results

    @staticmethod
    def test_trend_flip_logic() -> List[TestResult]:
        """Test symmetric trend-flip logic."""
        results = []

        try:
            from Python.hybrid_brain import HybridBrain
            from Python.risk_engine import RiskEngine

            # Create a mock setup
            risk = RiskEngine()

            class MockExecutor:
                def reconcile_exposure(self, *args, **kwargs):
                    pass

            brain = HybridBrain(risk=risk, executor=MockExecutor())

            # Create test data with clear bearish trend
            dates = pd.date_range(end=datetime.now(), periods=150, freq='5min')
            bearish_df = pd.DataFrame({
                'open': np.linspace(1.1000, 1.0900, 150),  # Falling prices
                'high': np.linspace(1.1010, 1.0910, 150),
                'low': np.linspace(1.0990, 1.0890, 150),
                'close': np.linspace(1.1000, 1.0900, 150),
                'volume': np.ones(150) * 10000,
            }, index=dates)

            # Create test data with clear bullish trend
            bullish_df = pd.DataFrame({
                'open': np.linspace(1.0900, 1.1000, 150),  # Rising prices
                'high': np.linspace(1.0910, 1.1010, 150),
                'low': np.linspace(1.0890, 1.0990, 150),
                'close': np.linspace(1.0900, 1.1000, 150),
                'volume': np.ones(150) * 10000,
            }, index=dates)

            # Mock PPO to return positive signal
            brain.ppo_model = None  # Disable PPO to test LSTM + mock only

            # Test bearish trend flip
            start = time.time()
            decision = brain.decide("EURUSDm", bearish_df)
            trend_flip = decision.get("trend_flip", "")

            # In bearish trend, should have some flip indication
            passed = "bearish" in trend_flip
            results.append(TestResult(
                name="Trend Flip Detection (Bearish)",
                passed=passed,
                duration_ms=(time.time() - start) * 1000,
                details={"trend_flip": trend_flip}
            ))

            # Test bullish trend
            start = time.time()
            decision = brain.decide("EURUSDm", bullish_df)
            trend_flip = decision.get("trend_flip", "")

            passed = "bullish" in trend_flip
            results.append(TestResult(
                name="Trend Flip Detection (Bullish)",
                passed=passed,
                duration_ms=(time.time() - start) * 1000,
                details={"trend_flip": trend_flip}
            ))

        except Exception as e:
            results.append(TestResult(
                name="Trend Flip Logic",
                passed=False,
                duration_ms=0,
                error_message=str(e) + "\n" + traceback.format_exc()
            ))

        return results


class TestReporter:
    """Generate test reports."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.simulation_results: List[Dict] = []

    def add_results(self, results: List[TestResult]):
        self.results.extend(results)

    def add_simulation(self, result: Dict):
        self.simulation_results.append(result)

    def generate_report(self) -> str:
        """Generate comprehensive test report."""
        lines = [
            "=" * 80,
            "CHAIN GAMBLER COMPREHENSIVE TEST REPORT",
            "=" * 80,
            f"Generated: {datetime.now().isoformat()}",
            f"Total Tests: {len(self.results)}",
            f"Passed: {sum(1 for r in self.results if r.passed)}",
            f"Failed: {sum(1 for r in self.results if not r.passed)}",
            "",
            "-" * 80,
            "SAFETY VALIDATION TESTS",
            "-" * 80,
        ]

        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            lines.append(f"{status}: {result.name} ({result.duration_ms:.1f}ms)")
            if result.error_message:
                lines.append(f"    Error: {result.error_message}")
            if result.details:
                lines.append(f"    Details: {json.dumps(result.details, default=str)}")

        if self.simulation_results:
            lines.extend([
                "",
                "-" * 80,
                "TRADING SIMULATION RESULTS",
                "-" * 80,
            ])

            for sim in self.simulation_results:
                lines.append(f"Symbol: {sim.get('symbol')}")
                lines.append(f"  Bars Processed: {sim.get('bars_processed')}")
                lines.append(f"  Trades Taken: {sim.get('trades_taken')}")
                lines.append(f"  Decisions Made: {sim.get('decisions_made')}")
                lines.append(f"  PnL: ${sim.get('pnl', 0):.2f}")
                lines.append(f"  Risk Events: {len(sim.get('risk_events', []))}")
                lines.append(f"  Errors: {len(sim.get('errors', []))}")

        lines.extend([
            "",
            "=" * 80,
            f"OVERALL: {'✅ ALL TESTS PASSED' if all(r.passed for r in self.results) else '❌ SOME TESTS FAILED'}",
            "=" * 80,
        ])

        return "\n".join(lines)

    def save_report(self, filename: Optional[str] = None):
        """Save report to file."""
        TEST_CONFIG["results_dir"].mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        filepath = TEST_CONFIG["results_dir"] / filename
        report = self.generate_report()

        with open(filepath, 'w') as f:
            f.write(report)

        logger.success(f"Test report saved to {filepath}")
        return filepath


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Chain Gambler Comprehensive Test Framework")
    parser.add_argument("--download-data", action="store_true", help="Download MT5 data")
    parser.add_argument("--symbols", nargs="+", default=TEST_CONFIG["symbols"], help="Symbols to test")
    parser.add_argument("--run-simulation", action="store_true", help="Run trading simulation")
    parser.add_argument("--days", type=int, default=7, help="Days of data to download/test")
    parser.add_argument("--run-safety-tests", action="store_true", help="Run safety validation tests")
    parser.add_argument("--full-test", action="store_true", help="Run full test suite")
    parser.add_argument("--report", action="store_true", help="Generate test report")

    args = parser.parse_args()

    reporter = TestReporter()

    # Download data if requested
    if args.download_data or args.full_test:
        logger.info("Downloading historical data...")
        downloader = MT5DataDownloader()

        for symbol in args.symbols:
            df = downloader.download_data(symbol, days=args.days)
            if df is not None:
                logger.success(f"Data ready for {symbol}: {len(df)} bars")

        downloader.disconnect()

    # Run safety tests
    if args.run_safety_tests or args.full_test:
        logger.info("Running safety validation tests...")

        kill_switch_results = SafetyValidator.test_kill_switches()
        reporter.add_results(kill_switch_results)

        symbol_validation_results = SafetyValidator.test_symbol_validation()
        reporter.add_results(symbol_validation_results)

        trend_flip_results = SafetyValidator.test_trend_flip_logic()
        reporter.add_results(trend_flip_results)

    # Run simulation
    if args.run_simulation or args.full_test:
        logger.info("Running trading simulation...")

        simulator = TradingSimulator(test_equity=10000.0)

        for symbol in args.symbols[:2]:  # Limit to first 2 symbols for speed
            # Load data
            data_files = list(TEST_CONFIG["data_dir"].glob(f"{symbol}_*.csv"))
            if data_files:
                df = pd.read_csv(data_files[0], index_col='time', parse_dates=True)
                logger.info(f"Loaded {len(df)} bars for {symbol}")

                result = simulator.simulate_trading_day(symbol, df, max_trades=5)
                reporter.add_simulation(result)

                logger.success(f"Simulation complete for {symbol}: {result['trades_taken']} trades")

    # Generate report
    if args.report or args.full_test:
        report_path = reporter.save_report()
        print(f"\nTest report saved to: {report_path}")

        # Also print to console
        print("\n" + reporter.generate_report())

    return 0 if all(r.passed for r in reporter.results) else 1


if __name__ == "__main__":
    sys.exit(main())
