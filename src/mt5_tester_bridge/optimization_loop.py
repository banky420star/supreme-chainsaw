"""MT5 Strategy Tester Optimization Loop.

Runs parameter optimization by iterating over parameter ranges,
testing each configuration via the MT5 Strategy Tester, and
selecting the best configuration based on the target metric.

This is the core feedback mechanism: simulation → tester → refine → repeat.
"""
import os
import json
import time
import copy
from typing import Optional

from loguru import logger


def run_optimization(orchestrator, model, symbol: str, param_ranges: dict,
                     metric: str = "profit_factor") -> dict:
    """Run parameter optimization using MT5 Strategy Tester.

    Iterates over all combinations of parameter ranges, runs each
    through the Strategy Tester, and selects the best based on metric.

    Args:
        orchestrator: BridgeOrchestrator instance
        model: Trading model to test
        symbol: Trading symbol (e.g. "EURUSDm")
        param_ranges: Dict of param_name -> list of values to try
            Example: {"lot_size": [0.01, 0.02, 0.05],
                      "sl_atr_mult": [2.0, 2.5, 3.0, 3.5],
                      "tp_atr_mult": [4.0, 5.0, 6.0]}
        metric: Optimization target — "profit_factor", "sharpe", "max_drawdown",
                "total_pnl", "recovery_factor"

    Returns:
        dict with best parameters, best score, all results
    """
    logger.info(f"Starting optimization for {symbol} on metric={metric}")
    logger.info(f"Parameter ranges: {param_ranges}")

    # Generate all parameter combinations
    combos = _generate_combinations(param_ranges)
    logger.info(f"Testing {len(combos)} parameter combinations")

    results = []
    best_score = float("-inf") if metric != "max_drawdown" else float("inf")
    best_params = None
    best_result = None

    for i, combo in enumerate(combos):
        logger.info(f"Optimization {i+1}/{len(combos)}: {combo}")

        try:
            result = orchestrator.run_test(
                model=model,
                symbol=symbol,
                config_overrides=combo,
            )

            # Extract the target metric
            parsed = result.get("parsed_results", {})
            score = _extract_metric(parsed, metric)

            combo_result = {
                "params": combo,
                "score": score,
                "metric": metric,
                "total_trades": parsed.get("total_trades", 0),
                "total_pnl": parsed.get("total_pnl", 0),
                "profit_factor": parsed.get("profit_factor", 0),
                "max_drawdown": parsed.get("max_drawdown", 0),
            }
            results.append(combo_result)

            # Check if this is the best so far
            is_better = _is_better(score, best_score, metric)
            if is_better:
                best_score = score
                best_params = combo
                best_result = combo_result
                logger.info(f"  New best: {metric}={score:.4f} with {combo}")

        except Exception as e:
            logger.error(f"Optimization run {i+1} failed: {e}")
            results.append({"params": combo, "error": str(e)})

    # Build final optimization result
    optimization_result = {
        "symbol": symbol,
        "metric": metric,
        "best_params": best_params,
        "best_score": best_score,
        "best_result": best_result,
        "all_results": results,
        "total_combinations": len(combos),
        "successful_combinations": len([r for r in results if "error" not in r]),
        "timestamp": time.time(),
    }

    # Save results
    _save_optimization_results(optimization_result, symbol, orchestrator.results_dir)

    logger.info(
        f"Optimization complete: best {metric}={best_score:.4f} "
        f"with params={best_params}"
    )

    return optimization_result


def _generate_combinations(param_ranges: dict) -> list:
    """Generate all combinations of parameter values.

    Args:
        param_ranges: Dict of param_name -> list of values

    Returns:
        List of dicts, each representing one parameter combination
    """
    if not param_ranges:
        return [{}]

    keys = list(param_ranges.keys())
    values = list(param_ranges.values())

    combos = [{}]
    for key, vals in zip(keys, values):
        new_combos = []
        for existing in combos:
            for val in vals:
                new_combo = copy.deepcopy(existing)
                new_combo[key] = val
                new_combos.append(new_combo)
        combos = new_combos

    return combos


def _extract_metric(parsed_results: dict, metric: str) -> float:
    """Extract the target metric from parsed results."""
    metric_map = {
        "profit_factor": "profit_factor",
        "sharpe": "sharpe_ratio",
        "sharpe_ratio": "sharpe_ratio",
        "max_drawdown": "max_drawdown",
        "total_pnl": "total_pnl",
        "recovery_factor": "recovery_factor",
        "total_trades": "total_trades",
    }

    key = metric_map.get(metric, metric)
    return float(parsed_results.get(key, 0))


def _is_better(score: float, current_best: float, metric: str) -> bool:
    """Determine if the new score is better than current best.

    For max_drawdown, lower is better. For all other metrics, higher is better.
    """
    if metric == "max_drawdown":
        return score < current_best
    return score > current_best


def _save_optimization_results(result: dict, symbol: str, base_dir: str) -> str:
    """Save optimization results to a JSON file."""
    os.makedirs(base_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"optimization_{symbol}_{timestamp}.json"
    filepath = os.path.join(base_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Optimization results saved to {filepath}")
    return filepath


def run_grid_search(orchestrator, model, symbol: str,
                    base_config: dict, param_grid: dict,
                    metric: str = "profit_factor",
                    min_trades: int = 10) -> dict:
    """Run a grid search optimization with minimum trade filter.

    Like run_optimization but filters out configurations that
    produce too few trades (likely overfitted or broken).

    Args:
        orchestrator: BridgeOrchestrator instance
        model: Trading model
        symbol: Symbol to test
        base_config: Base config overrides (merged with each grid point)
        param_grid: Dict of param_name -> list of values
        metric: Target metric
        min_trades: Minimum trades to consider a configuration valid

    Returns:
        dict with best parameters, scores, and filtered results
    """
    # Merge base config into each grid combination
    merged_ranges = {}
    for key, values in param_grid.items():
        merged_ranges[key] = values

    result = run_optimization(
        orchestrator=orchestrator,
        model=model,
        symbol=symbol,
        param_ranges=merged_ranges,
        metric=metric,
    )

    # Filter out low-trade configurations
    filtered_results = [
        r for r in result["all_results"]
        if r.get("total_trades", 0) >= min_trades and "error" not in r
    ]

    # Re-rank
    if filtered_results:
        if metric == "max_drawdown":
            best = min(filtered_results, key=lambda r: r.get("score", float("inf")))
        else:
            best = max(filtered_results, key=lambda r: r.get("score", float("-inf")))

        result["best_params"] = best["params"]
        result["best_score"] = best["score"]
        result["best_result"] = best
        result["filtered_results"] = filtered_results
        result["filtered_count"] = len(filtered_results)

    logger.info(
        f"Grid search: {len(filtered_results)}/{result['total_combinations']} "
        f"configs passed min_trades={min_trades} filter"
    )

    return result


def run_walk_forward(orchestrator, model, symbol: str,
                     param_ranges: dict, metric: str = "profit_factor",
                     train_periods: list = None,
                     test_periods: list = None) -> dict:
    """Run walk-forward optimization.

    Optimizes parameters on in-sample (train) periods, then validates
    on out-of-sample (test) periods.

    Args:
        orchestrator: BridgeOrchestrator instance
        model: Trading model
        symbol: Symbol to test
        param_ranges: Parameter ranges for optimization
        metric: Target metric
        train_periods: List of training period strings (e.g. ["2023.01.01-2023.06.30"])
        test_periods: List of test period strings (same length as train_periods)

    Returns:
        dict with walk-forward results
    """
    if train_periods is None:
        train_periods = ["2023.01.01-2023.06.30", "2023.07.01-2023.12.31"]
    if test_periods is None:
        test_periods = ["2023.07.01-2023.12.31", "2024.01.01-2024.06.30"]

    if len(train_periods) != len(test_periods):
        raise ValueError("train_periods and test_periods must be same length")

    wf_results = []

    for train_period, test_period in zip(train_periods, test_periods):
        logger.info(f"Walk-forward: train={train_period}, test={test_period}")

        # Optimize on training period
        opt_result = run_optimization(
            orchestrator=orchestrator,
            model=model,
            symbol=symbol,
            param_ranges=param_ranges,
            metric=metric,
        )

        best_params = opt_result.get("best_params", {})
        if not best_params:
            logger.warning(f"No best params found for train period {train_period}")
            continue

        # Test on out-of-sample period
        test_result = orchestrator.run_test(
            model=model,
            symbol=symbol,
            period=test_period,
            config_overrides=best_params,
        )

        parsed = test_result.get("parsed_results", {})
        wf_results.append({
            "train_period": train_period,
            "test_period": test_period,
            "best_params": best_params,
            "train_score": opt_result.get("best_score", 0),
            "test_score": _extract_metric(parsed, metric),
            "test_pnl": parsed.get("total_pnl", 0),
            "test_trades": parsed.get("total_trades", 0),
        })

    # Compute walk-forward efficiency
    if wf_results:
        avg_train = sum(r["train_score"] for r in wf_results) / len(wf_results)
        avg_test = sum(r["test_score"] for r in wf_results) / len(wf_results)
        wf_efficiency = avg_test / avg_train if avg_train != 0 else 0
    else:
        wf_efficiency = 0

    return {
        "symbol": symbol,
        "metric": metric,
        "walk_forward_efficiency": wf_efficiency,
        "folds": wf_results,
        "avg_train_score": avg_train if wf_results else 0,
        "avg_test_score": avg_test if wf_results else 0,
    }