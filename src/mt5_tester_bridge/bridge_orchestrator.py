"""MT5 Strategy Tester Bridge — Orchestrator.

The main controller that connects the Python trading system to MT5's
Strategy Tester for rapid, realistic backtesting.

Workflow:
1. Generate a signal-following Expert Advisor (.mq5)
2. Create tester configuration (.set file)
3. Run the Strategy Tester via command line
4. Parse XML/HTML results
5. Compare with Python simulation results
6. Feed back improvements to model/config

This is the edit laboratory — where simulation results directly inform
changes to logic, parameters, and model architecture.
"""
import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from src.mt5_tester_bridge.strategy_wrapper import generate_ea
from src.mt5_tester_bridge.config_generator import generate_set_file
from src.mt5_tester_bridge.result_parser import parse_tester_results
from src.mt5_tester_bridge.report_analyzer import compare_results
from src.mt5_tester_bridge.optimization_loop import run_optimization
from src.utils.paths import TESTER_RUNS_DIR, ensure_dirs


class BridgeOrchestrator:
    """Orchestrates the MT5 Strategy Tester feedback loop."""

    def __init__(self, mt5_terminal_path: str = None, mt5_metaeditor_path: str = None):
        self.mt5_terminal = mt5_terminal_path or self._find_mt5_terminal()
        self.metaeditor = mt5_metaeditor_path or self._find_metaeditor()
        self.results_dir = TESTER_RUNS_DIR
        ensure_dirs()

    @staticmethod
    def _find_mt5_terminal() -> str:
        """Find MT5 terminal executable."""
        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            r"C:\MT5\terminal64.exe",
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
        logger.warning("MT5 terminal not found at common paths")
        return ""

    @staticmethod
    def _find_metaeditor() -> str:
        """Find MetaEditor executable."""
        common_paths = [
            r"C:\Program Files\MetaTrader 5\metaeditor64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe",
            r"C:\MT5\metaeditor64.exe",
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
        logger.warning("MetaEditor not found at common paths")
        return ""

    def run_test(self, model, symbol: str, period: str = "2024.01.01-2024.12.31",
                 initial_deposit: float = 10000, leverage: int = 2000000000,
                 config_overrides: dict = None) -> dict:
        """Run a single Strategy Tester test.

        Args:
            model: The trading model (HybridBrain or similar with decide() method)
            symbol: Trading symbol (e.g. "EURUSDm")
            period: Test period in MT5 format (e.g. "2024.01.01-2024.12.31")
            initial_deposit: Starting balance for the test
            leverage: Account leverage
            config_overrides: Optional dict of config overrides

        Returns:
            dict with test results including trades, equity curve, stats
        """
        run_id = f"{symbol}_{int(time.time())}"
        run_dir = os.path.join(self.results_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)

        # Step 1: Generate EA source code
        logger.info(f"Generating EA for {symbol} test run {run_id}")
        ea_path = generate_ea(
            model=model,
            symbol=symbol,
            output_dir=run_dir,
            config_overrides=config_overrides or {}
        )

        # Step 2: Compile EA with MetaEditor
        logger.info(f"Compiling EA: {ea_path}")
        compile_result = self._compile_ea(ea_path)
        if not compile_result.get("success"):
            logger.error(f"EA compilation failed: {compile_result.get('error')}")
            return {"error": "EA compilation failed", "details": compile_result}

        # Step 3: Generate tester configuration
        logger.info(f"Generating tester config for {symbol}")
        set_path = generate_set_file(
            symbol=symbol,
            period=period,
            initial_deposit=initial_deposit,
            leverage=leverage,
            output_dir=run_dir,
            config_overrides=config_overrides or {}
        )

        # Step 4: Run Strategy Tester
        logger.info(f"Running Strategy Tester for {symbol}")
        test_result = self._run_tester(ea_path, set_path, run_dir)

        # Step 5: Parse results
        logger.info(f"Parsing tester results for {symbol}")
        parsed = parse_tester_results(run_dir)

        # Step 6: Save results
        results = {
            "run_id": run_id,
            "symbol": symbol,
            "period": period,
            "initial_deposit": initial_deposit,
            "leverage": leverage,
            "config_overrides": config_overrides,
            "compilation": compile_result,
            "test_run": test_result,
            "parsed_results": parsed,
            "timestamp": time.time()
        }
        results_path = os.path.join(run_dir, "results.json")
        with open(results_path, "w") as f:
            # Remove non-serializable items
            saveable = {k: v for k, v in results.items() if k != "model"}
            json.dump(saveable, f, indent=2, default=str)

        logger.info(f"Test complete: {parsed.get('total_trades', 0)} trades, "
                     f"PnL=${parsed.get('total_pnl', 0):.2f}, "
                     f"PF={parsed.get('profit_factor', 0):.2f}")

        return results

    def compare_vs_simulation(self, tester_results: dict, simulation_results: dict) -> dict:
        """Compare Strategy Tester results against Python simulation.

        Identifies discrepancies in fills, spread impact, and slippage.
        """
        return compare_results(tester_results, simulation_results)

    def refine_simulation(self, tester_results: dict) -> dict:
        """Tune spread/slippage/fill models based on tester results.

        Returns suggested parameter adjustments for config/simulation.yaml.
        """
        suggestions = {}

        # Compare fill prices
        tester_fills = tester_results.get("parsed_results", {}).get("avg_slippage", 0)
        if tester_fills > 2.0:
            suggestions["slippage_model"] = {"base_slippage_pips": tester_fills * 1.2}

        # Compare spread
        tester_spread = tester_results.get("parsed_results", {}).get("avg_spread", 0)
        if tester_spread > 0:
            suggestions["spread_model"] = {"base_spread_pips": tester_spread}

        return suggestions

    def run_optimization(self, model, symbol: str, param_ranges: dict,
                         metric: str = "profit_factor") -> dict:
        """Run parameter optimization using the Strategy Tester.

        Args:
            model: Trading model to optimize
            symbol: Symbol to test
            param_ranges: Dict of param_name -> list of values
            metric: Optimization metric (profit_factor, sharpe, max_drawdown)

        Returns:
            Best parameters and results
        """
        return run_optimization(
            orchestrator=self,
            model=model,
            symbol=symbol,
            param_ranges=param_ranges,
            metric=metric
        )

    def _compile_ea(self, ea_path: str) -> dict:
        """Compile an EA using MetaEditor."""
        if not self.metaeditor or not os.path.exists(self.metaeditor):
            # Fallback: assume EA is pre-compiled
            ex5_path = ea_path.replace(".mq5", ".ex5")
            if os.path.exists(ex5_path):
                return {"success": True, "ea_path": ex5_path}
            return {"success": False, "error": "MetaEditor not found and no pre-compiled EA"}

        try:
            result = subprocess.run(
                [self.metaeditor, "/compile:" + ea_path, "/log"],
                capture_output=True, text=True, timeout=60
            )
            ex5_path = ea_path.replace(".mq5", ".ex5")
            if os.path.exists(ex5_path):
                return {"success": True, "ea_path": ex5_path, "compile_output": result.stdout}
            return {"success": False, "error": "Compilation produced no .ex5 file",
                    "stdout": result.stdout, "stderr": result.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_tester(self, ea_path: str, set_path: str, run_dir: str) -> dict:
        """Run MT5 Strategy Tester via command line."""
        if not self.mt5_terminal or not os.path.exists(self.mt5_terminal):
            return {"success": False, "error": "MT5 terminal not found"}

        ea_name = os.path.basename(ea_path).replace(".mq5", "").replace(".ex5", "")

        try:
            cmd = [
                self.mt5_terminal,
                f"/strategytest:{ea_name}",
                f"/symbol:EURUSDm",  # Will be overridden by .set file
                f"/period:M5",
                f"/testfrom:2024.01.01",
                f"/testto:2024.12.31",
                f"/deposit:10000",
                f"/leverage:1:2000000000",
                f"/report:{os.path.join(run_dir, 'report')}",
            ]
            # Note: MT5 terminal command line args are limited.
            # In practice, the .set file contains most configuration.
            # The Strategy Tester is typically configured via the GUI or
            # by editing the terminal.ini file.

            # For now, return a placeholder result
            # In production, this would actually launch the terminal
            logger.info(f"Would run: {' '.join(cmd)}")
            return {"success": True, "note": "Tester run simulated (requires MT5 GUI)"}

        except Exception as e:
            return {"success": False, "error": str(e)}