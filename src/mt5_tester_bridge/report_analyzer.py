"""MT5 Strategy Tester Report Analyzer.

Compares MT5 Strategy Tester results against Python simulation results.
Identifies discrepancies in fills, spread impact, slippage, and timing.
Produces actionable tuning suggestions for simulation accuracy.
"""
import os
from typing import Optional

from loguru import logger


def compare_results(tester_results: dict, simulation_results: dict) -> dict:
    """Compare Strategy Tester results against Python simulation.

    Identifies systematic discrepancies between simulated and actual
    test results. These discrepancies inform simulation parameter tuning.

    Args:
        tester_results: Parsed results from MT5 Strategy Tester
        simulation_results: Results from Python simulation engine

    Returns:
        dict with comparison metrics and tuning suggestions
    """
    comparison = {
        "trade_count_match": False,
        "pnl_delta": 0.0,
        "pnl_delta_pct": 0.0,
        "profit_factor_delta": 0.0,
        "max_drawdown_delta": 0.0,
        "win_rate_delta": 0.0,
        "avg_slippage_estimated": 0.0,
        "spread_impact_estimated": 0.0,
        "fill_discrepancies": [],
        "suggestions": [],
    }

    t_trades = tester_results.get("total_trades", 0)
    s_trades = simulation_results.get("total_trades", 0)
    comparison["trade_count_match"] = abs(t_trades - s_trades) <= max(1, int(s_trades * 0.05))

    # PnL comparison
    t_pnl = tester_results.get("total_pnl", 0.0)
    s_pnl = simulation_results.get("total_pnl", 0.0)
    comparison["pnl_delta"] = t_pnl - s_pnl
    comparison["pnl_delta_pct"] = (t_pnl - s_pnl) / abs(s_pnl) if s_pnl != 0 else 0.0

    # Profit factor comparison
    t_pf = tester_results.get("profit_factor", 0.0)
    s_pf = simulation_results.get("profit_factor", 0.0)
    comparison["profit_factor_delta"] = t_pf - s_pf

    # Max drawdown comparison
    t_dd = tester_results.get("max_drawdown", 0.0)
    s_dd = simulation_results.get("max_drawdown", 0.0)
    comparison["max_drawdown_delta"] = t_dd - s_dd

    # Win rate comparison
    t_wins = tester_results.get("winning_trades", 0)
    s_wins = simulation_results.get("winning_trades", 0)
    t_wr = t_wins / t_trades if t_trades > 0 else 0.0
    s_wr = s_wins / s_trades if s_trades > 0 else 0.0
    comparison["win_rate_delta"] = t_wr - s_wr

    # Estimate slippage impact
    # If tester PnL is consistently worse, slippage is likely underestimated
    if t_trades > 0 and comparison["pnl_delta"] < 0:
        per_trade_impact = comparison["pnl_delta"] / t_trades
        comparison["avg_slippage_estimated"] = abs(per_trade_impact)
        comparison["suggestions"].append(
            f"Tester PnL is ${comparison['pnl_delta']:.2f} worse than simulation. "
            f"Estimated per-trade slippage impact: ${per_trade_impact:.2f}. "
            f"Consider increasing slippage_model.base_slippage_pips."
        )

    # Spread impact estimation
    if t_trades > 0:
        # Compare close prices if available
        t_trades_list = tester_results.get("trades", [])
        s_trades_list = simulation_results.get("trades", [])

        if t_trades_list and s_trades_list:
            spread_impact = _estimate_spread_impact(t_trades_list, s_trades_list)
            comparison["spread_impact_estimated"] = spread_impact
            if spread_impact > 0:
                comparison["suggestions"].append(
                    f"Estimated spread impact: ${spread_impact:.2f} per trade. "
                    f"Consider adjusting spread_model.base_spread_pips."
                )

    # Drawdown analysis
    if t_dd > s_dd * 1.5 and s_dd > 0:
        comparison["suggestions"].append(
            f"Tester max drawdown (${t_dd:.2f}) is significantly higher than "
            f"simulated (${s_dd:.2f}). Consider tightening stop-loss ATR multiplier "
            f"or adding spread buffers to SL calculations."
        )

    # Fill discrepancies
    comparison["fill_discrepancies"] = _find_fill_discrepancies(
        tester_results.get("trades", []),
        simulation_results.get("trades", [])
    )

    if comparison["fill_discrepancies"]:
        comparison["suggestions"].append(
            f"Found {len(comparison['fill_discrepancies'])} fill discrepancies. "
            f"Review execution timing and market conditions."
        )

    logger.info(
        f"Comparison: PnL delta=${comparison['pnl_delta']:.2f} "
        f"({comparison['pnl_delta_pct']:.1%}), "
        f"PF delta={comparison['profit_factor_delta']:.2f}, "
        f"DD delta=${comparison['max_drawdown_delta']:.2f}"
    )

    return comparison


def _estimate_spread_impact(tester_trades: list, sim_trades: list) -> float:
    """Estimate the per-trade spread cost impact.

    Compares entry/exit prices between tester and simulation to
    estimate how much spread costs affected real fills.
    """
    if not tester_trades or not sim_trades:
        return 0.0

    total_impact = 0.0
    matched = 0

    # Match trades by time proximity
    for t_trade in tester_trades:
        t_time = t_trade.get("time", "")
        t_symbol = t_trade.get("symbol", "")
        t_type = t_trade.get("type", "").upper()

        best_match = None
        best_dt = float("inf")

        for s_trade in sim_trades:
            if s_trade.get("symbol", "") != t_symbol:
                continue
            if s_trade.get("type", "").upper() != t_type:
                continue

            s_time = s_trade.get("time", "")
            dt = abs(len(s_time) - len(t_time))  # rough proximity
            if dt < best_dt:
                best_dt = dt
                best_match = s_trade

        if best_match:
            t_price = t_trade.get("price", 0)
            s_price = best_match.get("price", 0)
            if t_price > 0 and s_price > 0:
                # Price difference includes spread + slippage
                total_impact += abs(t_price - s_price)
                matched += 1

    return total_impact / matched if matched > 0 else 0.0


def _find_fill_discrepancies(tester_trades: list, sim_trades: list) -> list:
    """Identify individual trades with significant fill differences."""
    discrepancies = []

    if not tester_trades or not sim_trades:
        return discrepancies

    for t_trade in tester_trades:
        t_time = t_trade.get("time", "")
        t_symbol = t_trade.get("symbol", "")
        t_profit = t_trade.get("profit", 0)

        # Find closest matching sim trade
        best_match = None
        for s_trade in sim_trades:
            if s_trade.get("symbol", "") != t_symbol:
                continue
            if s_trade.get("type", "").upper() != t_trade.get("type", "").upper():
                continue
            s_profit = s_trade.get("profit", 0)
            if abs(t_profit - s_profit) > abs(t_profit) * 0.2:
                best_match = s_trade
                break

        if best_match:
            s_profit = best_match.get("profit", 0)
            profit_delta = t_profit - s_profit
            if abs(profit_delta) > 5.0:  # $5 threshold
                discrepancies.append({
                    "time": t_time,
                    "symbol": t_symbol,
                    "type": t_trade.get("type", ""),
                    "tester_profit": t_profit,
                    "sim_profit": s_profit,
                    "delta": profit_delta,
                })

    return discrepancies


def generate_tuning_report(comparison: dict, output_path: str = None) -> str:
    """Generate a human-readable tuning report from comparison results.

    Args:
        comparison: Output from compare_results()
        output_path: Optional path to write report file

    Returns:
        Report string
    """
    lines = [
        "=" * 60,
        "MT5 Strategy Tester vs Python Simulation — Comparison Report",
        "=" * 60,
        "",
        f"Trade count match: {comparison.get('trade_count_match', 'N/A')}",
        f"PnL delta: ${comparison.get('pnl_delta', 0):.2f} "
        f"({comparison.get('pnl_delta_pct', 0):.1%})",
        f"Profit factor delta: {comparison.get('profit_factor_delta', 0):.2f}",
        f"Max drawdown delta: ${comparison.get('max_drawdown_delta', 0):.2f}",
        f"Win rate delta: {comparison.get('win_rate_delta', 0):.1%}",
        f"Estimated slippage: ${comparison.get('avg_slippage_estimated', 0):.2f}/trade",
        f"Estimated spread impact: ${comparison.get('spread_impact_estimated', 0):.2f}/trade",
        "",
    ]

    fill_disc = comparison.get("fill_discrepancies", [])
    if fill_disc:
        lines.append(f"Fill discrepancies: {len(fill_disc)}")
        for disc in fill_disc[:5]:
            lines.append(
                f"  {disc['time']} {disc['symbol']} {disc['type']}: "
                f"tester=${disc['tester_profit']:.2f} sim=${disc['sim_profit']:.2f} "
                f"delta=${disc['delta']:.2f}"
            )
        if len(fill_disc) > 5:
            lines.append(f"  ... and {len(fill_disc) - 5} more")
        lines.append("")

    suggestions = comparison.get("suggestions", [])
    if suggestions:
        lines.append("Tuning Suggestions:")
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s}")
    else:
        lines.append("No tuning suggestions — simulation matches tester well.")

    lines.append("")
    lines.append("=" * 60)

    report = "\n".join(lines)

    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"Tuning report written to {output_path}")

    return report