"""
Trade Review — Post-trade analysis, annotation, and feedback loop.

Compiles executed trades with their decision context, analyzes outcomes,
creates human-readable annotations, and feeds results back into training.

Pipeline:
  1. Gather trade executions from MT5 + decision logs
  2. Match trades with their decision rationale (from decisions.jsonl)
  3. Analyze outcomes: P/L, SL/TP effectiveness, signal quality
  4. Annotate each trade with reason tags
  5. Store enriched trade records for retraining feedback
  6. Report summary metrics
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from loguru import logger

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_BASE, "logs")
REVIEW_DIR = os.path.join(_BASE, "logs", "trade_reviews")
os.makedirs(REVIEW_DIR, exist_ok=True)


# ── Reason Tags ──────────────────────────────────────────────────────
# Tags that explain WHY a trade won or lost
TAG_SL_TOO_TIGHT = "sl_too_tight"
TAG_TP_HIT = "tp_hit"
TAG_SIGNAL_CORRECT = "signal_correct"
TAG_SIGNAL_WRONG = "signal_wrong"
TAG_LOW_CONFIDENCE = "low_confidence"
TAG_HIGH_VOLATILITY = "high_volatility_regime"
TAG_BUY_BIAS = "buy_bias"
TAG_REVERSAL = "market_reversal"
TAG_SPREAD_WIDENED = "spread_widened"
TAG_NEWS_EVENT = "news_event_impact"
TAG_UNKNOWN = "unknown"

REASON_MAP = {
    4: "sl_hit",
    5: "tp_hit",
    6: "margin_call",
    7: "closed_by_dealer",
    8: "partial_close",
}


def _ts_to_utc(ts) -> datetime:
    """Convert MT5 timestamp (int or datetime) to UTC datetime."""
    if isinstance(ts, datetime):
        return ts
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def gather_closed_trades(days_back: int = 7) -> list[dict]:
    """Fetch closed trade deals from MT5 with full context."""
    if mt5 is None:
        logger.warning("MT5 not available — cannot gather trades")
        return []

    if not mt5.initialize():
        logger.error("MT5 init failed")
        return []

    try:
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        deals = mt5.history_deals_get(since, datetime.now(timezone.utc))
        if not deals:
            return []

        trades = []
        for d in deals:
            if d.entry != 1:  # Only closing deals
                continue
            if d.type == 2:  # Skip balance operations
                continue

            close_reason = REASON_MAP.get(d.reason, f"reason_{d.reason}")
            is_sl = d.reason == 4
            is_tp = d.reason == 5

            trades.append({
                "ticket": d.ticket,
                "order": d.order,
                "symbol": d.symbol,
                "side": "BUY" if d.type == 0 else "SELL",
                "volume": d.volume,
                "price": d.price,
                "profit": round(d.profit, 2),
                "commission": round(d.commission, 2),
                "swap": round(d.swap, 6),
                "close_time": _ts_to_utc(d.time).isoformat(),
                "close_reason": close_reason,
                "is_sl": is_sl,
                "is_tp": is_tp,
                "comment": d.comment or "",
            })
        return trades
    finally:
        mt5.shutdown()


def load_decision_log(hours_back: int = 168) -> list[dict]:
    """Load recent decisions from the JSONL log.

    Default 168 hours (7 days) to match the trade review window.
    """
    path = os.path.join(LOG_DIR, "decisions.jsonl")
    if not os.path.exists(path):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    decisions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line.strip())
                ts = d.get("timestamp", "")
                if ts:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt >= cutoff:
                        decisions.append(d)
            except (json.JSONDecodeError, ValueError):
                continue
    return decisions


def match_trade_to_decision(trade: dict, decisions: list[dict]) -> dict | None:
    """Find the decision that led to a trade by matching symbol and time proximity.

    The decision was made BEFORE the trade was opened, so we look for
    decisions for this symbol close to the trade's open time (not close time).
    We search up to 24 hours before close to cover longer-held positions.
    """
    symbol = trade["symbol"]
    close_time_str = trade["close_time"]
    try:
        close_dt = datetime.fromisoformat(close_time_str)
    except (ValueError, TypeError):
        return None

    best = None
    best_dt_diff = float("inf")

    for d in decisions:
        if d.get("symbol") != symbol:
            continue
        ts = d.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            # Decision must be BEFORE the trade closed, and within 24 hours
            # (covers trades held from minutes to hours)
            diff = (close_dt - dt).total_seconds()
            if 0 < diff < 86400 and diff < best_dt_diff:  # Within 24h before close
                best = d
                best_dt_diff = diff
        except (ValueError, TypeError):
            continue

    return best


def annotate_trade(trade: dict, decision: dict | None) -> list[str]:
    """Generate reason tags for a trade based on outcome and context."""
    tags = []

    if trade["is_sl"]:
        # Differentiate SL at loss vs SL in profit
        profit = trade.get("profit", 0)
        commission = trade.get("commission", 0)
        swap = trade.get("swap", 0)
        gross = profit - commission - swap
        if profit > 0:
            # SL hit but trade was in profit — trailing stop would have helped
            tags.append("sl_in_profit")
        elif abs(gross) < 0.5 and profit < 0:
            # Gross profit near zero, net negative — spread killed it
            tags.append(TAG_SPREAD_WIDENED)
        else:
            tags.append(TAG_SL_TOO_TIGHT)
    elif trade["is_tp"]:
        tags.append(TAG_TP_HIT)
        tags.append(TAG_SIGNAL_CORRECT)

    if decision:
        confidence = decision.get("confidence", 0)
        regime = decision.get("lstm_regime", "UNKNOWN")
        action = decision.get("action", "HOLD")
        ppo_action = decision.get("ppo_primary_action", 0)
        ppo_bias = decision.get("ppo_bias", 0)

        if confidence < 0.5:
            tags.append(TAG_LOW_CONFIDENCE)

        if regime == "HIGH_VOLATILITY":
            tags.append(TAG_HIGH_VOLATILITY)

        # Detect BUY bias: if PPO is always positive
        if abs(ppo_bias) > 0.001 and action == "BUY":
            tags.append(TAG_BUY_BIAS)

        # If trade lost and signal was BUY but PPO output was tiny
        if trade["profit"] < 0 and abs(ppo_action) < 0.01:
            tags.append(TAG_SIGNAL_WRONG)

    # If no decision matched, flag as unknown
    if decision is None:
        tags.append(TAG_UNKNOWN)

    # If trade lost but wasn't SL (manual close or other)
    if trade["profit"] < 0 and not trade["is_sl"] and not trade["is_tp"]:
        tags.append(TAG_REVERSAL)

    return tags


def analyze_trades(trades: list[dict], decisions: list[dict]) -> dict:
    """Full trade analysis with annotations. Returns enriched trades + summary."""
    enriched = []
    by_symbol = defaultdict(list)
    tag_counts = defaultdict(int)

    for trade in trades:
        decision = match_trade_to_decision(trade, decisions)
        tags = annotate_trade(trade, decision)

        record = {
            **trade,
            "decision_context": decision,
            "tags": tags,
            "tags_str": ", ".join(tags),
        }
        enriched.append(record)
        by_symbol[trade["symbol"]].append(record)
        for t in tags:
            tag_counts[t] += 1

    # Compute summary
    total = len(trades)
    if total == 0:
        return {"enriched": [], "summary": {}}

    wins = [t for t in enriched if t["profit"] > 0]
    losses = [t for t in enriched if t["profit"] <= 0]
    sl_trades = [t for t in enriched if t["is_sl"]]
    tp_trades = [t for t in enriched if t["is_tp"]]

    summary = {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / total * 100, 1),
        "total_pnl": round(sum(t["profit"] for t in trades), 2),
        "avg_win": round(sum(t["profit"] for t in wins) / max(len(wins), 1), 2),
        "avg_loss": round(sum(t["profit"] for t in losses) / max(len(losses), 1), 2),
        "profit_factor": round(
            abs(sum(t["profit"] for t in wins)) / max(abs(sum(t["profit"] for t in losses)), 0.01), 2
        ),
        "sl_hits": len(sl_trades),
        "tp_hits": len(tp_trades),
        "sl_rate": round(len(sl_trades) / total * 100, 1) if total else 0,
        "tp_rate": round(len(tp_trades) / total * 100, 1) if total else 0,
        "tag_distribution": dict(tag_counts),
        "by_symbol": {},
    }

    for sym, sym_trades in by_symbol.items():
        sym_wins = [t for t in sym_trades if t["profit"] > 0]
        sym_total = len(sym_trades)
        summary["by_symbol"][sym] = {
            "trades": sym_total,
            "wins": len(sym_wins),
            "win_rate": round(len(sym_wins) / max(sym_total, 1) * 100, 1),
            "pnl": round(sum(t["profit"] for t in sym_trades), 2),
            "sl_hits": len([t for t in sym_trades if t["is_sl"]]),
            "tp_hits": len([t for t in sym_trades if t["is_tp"]]),
        }

    return {"enriched": enriched, "summary": summary}


def save_review(result: dict) -> str:
    """Save trade review to a timestamped JSON file."""
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REVIEW_DIR, f"review_{now}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Trade review saved: {path}")
    return path


def run_review(days_back: int = 7) -> dict:
    """Run a full trade review cycle."""
    logger.info(f"Starting trade review (last {days_back} days)...")

    trades = gather_closed_trades(days_back=days_back)
    decisions = load_decision_log(hours_back=days_back * 24)

    logger.info(f"Gathered {len(trades)} closed trades, {len(decisions)} decisions")

    result = analyze_trades(trades, decisions)
    path = save_review(result)

    summary = result["summary"]
    logger.info(
        f"Review complete: {summary.get('total_trades', 0)} trades | "
        f"Win rate: {summary.get('win_rate', 0)}% | "
        f"PnL: ${summary.get('total_pnl', 0):.2f} | "
        f"PF: {summary.get('profit_factor', 0)}"
    )
    logger.info(f"Tag distribution: {summary.get('tag_distribution', {})}")

    return result


def get_latest_review() -> dict | None:
    """Load the most recent trade review."""
    reviews = sorted(
        [f for f in os.listdir(REVIEW_DIR) if f.startswith("review_") and f.endswith(".json")],
        reverse=True,
    )
    if not reviews:
        return None
    path = os.path.join(REVIEW_DIR, reviews[0])
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_economic_calendar(days_ahead: int = 7) -> list[dict]:
    """
    Fetch upcoming economic calendar events from MT5.

    Returns a list of dicts with keys: country, name, time, importance.
    Uses calendar_country() to list countries, then
    calendar_value_last_by_country() (or calendar_value_last()) per country
    to get events within the time window.
    """
    if mt5 is None:
        logger.debug("MT5 not available — cannot fetch economic calendar")
        return []

    if not mt5.initialize():
        logger.warning("MT5 init failed — cannot fetch economic calendar")
        return []

    try:
        events = []
        now = datetime.now(timezone.utc)
        to_date = now + timedelta(days=days_ahead)

        countries = mt5.calendar_country()
        if not countries:
            logger.debug("MT5 calendar_country() returned no countries")
            return []

        for country in countries:
            country_code = getattr(country, "code", "")
            country_name = getattr(country, "name", country_code)
            currency = getattr(country, "currency", country_code)

            try:
                # Prefer the by-country variant (available in newer MT5 builds)
                if hasattr(mt5, "calendar_value_last_by_country"):
                    country_events = mt5.calendar_value_last_by_country(
                        country_code, now, to_date
                    )
                else:
                    country_events = mt5.calendar_value_last(
                        country_code, now, to_date
                    )
            except (AttributeError, TypeError) as e:
                logger.debug(f"Calendar API unavailable for {country_code}: {e}")
                continue

            if not country_events:
                continue

            for ev in country_events:
                ev_time_raw = getattr(ev, "time", None)
                if ev_time_raw is None:
                    continue

                # Parse the event time — MT5 returns either a datetime or a timestamp
                try:
                    if isinstance(ev_time_raw, datetime):
                        ev_dt = ev_time_raw
                    else:
                        ev_dt = datetime.fromtimestamp(int(ev_time_raw), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    ev_dt = None

                importance = getattr(ev, "importance", 0)
                # MT5 importance: 0=none/low, 1=medium, 2=high
                importance_label = {0: "low", 1: "medium", 2: "high"}.get(importance, "unknown")

                events.append({
                    "country": country_code,
                    "country_name": country_name,
                    "currency": currency,
                    "name": getattr(ev, "name", ""),
                    "event_id": getattr(ev, "event_id", ""),
                    "time": ev_dt.isoformat() if ev_dt else str(ev_time_raw),
                    "importance": importance,
                    "importance_label": importance_label,
                })

        # Sort by time ascending
        events.sort(key=lambda e: e["time"])

        return events
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    result = run_review()
    print(json.dumps(result["summary"], indent=2, default=str))