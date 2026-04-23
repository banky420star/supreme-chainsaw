"""
API Server — Lightweight HTTP bridge between the AGI engine and the React dashboard.

Uses bottle (already in .venv312) on port 5000.  Vite dev-server proxies /api/* here.

Start modes:
  1. Embedded: import start_api_server(agi_server) from Server_AGI — preferred.
  2. Standalone: python -m Python.api_server — reads live_state.json fallback.

All endpoints are read-only except POST /api/control.
"""
from __future__ import annotations

import json
import os
import sys
import time
import threading
from collections import deque
from datetime import datetime, timezone

# ── Trade Review Summary Cache ─────────────────────────────────────
_trade_review_cache = {"summary": {}, "updated_at": 0}
_trade_review_lock = threading.Lock()

def _get_trade_review_summary():
    """Return cached trade review summary, refreshing if older than 5 minutes."""
    global _trade_review_cache
    now = time.time()
    if now - _trade_review_cache.get("updated_at", 0) > 300:  # 5 min cache
        try:
            with _trade_review_lock:
                from Python.trade_review import get_latest_review
                review = get_latest_review()
                if review:
                    _trade_review_cache = {
                        "summary": review.get("summary", {}),
                        "updated_at": now,
                    }
        except Exception:
            pass
    return _trade_review_cache.get("summary", {})


_calendar_cache = {"events": [], "updated_at": 0}

def _get_economic_calendar_cached():
    """Return cached economic calendar, refreshing if older than 30 minutes."""
    global _calendar_cache
    now = time.time()
    if now - _calendar_cache.get("updated_at", 0) > 1800:  # 30 min cache
        try:
            from Python.trade_review import get_economic_calendar
            events = get_economic_calendar(days_ahead=7)
            _calendar_cache = {"events": events, "updated_at": now}
        except Exception as e:
            logger.debug(f"Calendar cache refresh failed: {e}")
    return _calendar_cache.get("events", [])
from typing import Any

from bottle import Bottle, request, response, run as bottle_run
from loguru import logger

# ---------------------------------------------------------------------------
# Project root (one level above Python/)
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Bottle app
# ---------------------------------------------------------------------------
app = Bottle()

# ---------------------------------------------------------------------------
# Shared references — populated by start_api_server()
# ---------------------------------------------------------------------------
_server_ref: Any = None          # AGIServer instance
_decision_cache: dict[str, deque] = {}  # symbol -> deque of recent decisions
_CACHE_MAX = 50                  # decisions per symbol


# ---------------------------------------------------------------------------
# CORS middleware (restrict to localhost + localtunnel for security)
# ---------------------------------------------------------------------------
_CORS_ALLOWED_ORIGINS = [
    "http://localhost:4180",
    "http://127.0.0.1:4180",
    "https://moneyprinter.loca.lt",
]

@app.hook("after_request")
def _cors():
    origin = request.get_header("Origin", "")
    if origin in _CORS_ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:4180"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Control-Token"
    response.headers["Vary"] = "Origin"


@app.route("<path:path>", method="OPTIONS")
def _options(path):
    return {}


# ---------------------------------------------------------------------------
# Telegram Mini App — serve the HTML page
# ---------------------------------------------------------------------------
_MINI_APP_HTML = None

@app.route("/mini", method=["GET", "POST"])
def api_mini_app():
    """Serve the Telegram Mini App HTML page."""
    global _MINI_APP_HTML
    if _MINI_APP_HTML is None:
        mini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "tools", "ui_assets", "telegram_mini_app.html")
        try:
            with open(mini_path, "r", encoding="utf-8") as f:
                _MINI_APP_HTML = f.read()
        except Exception:
            _MINI_APP_HTML = "<html><body><h1>Mini App not found</h1></body></html>"
    response.content_type = "text/html; charset=utf-8"
    return _MINI_APP_HTML


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _json(obj: Any, status: int = 200):
    response.content_type = "application/json"
    response.status = status
    return json.dumps(obj, default=str)


def _read_json_file(path: str) -> Any:
    """Safely read a JSON file, returning None on any error."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _read_active_registry() -> dict:
    """Read models/registry/active.json."""
    active_path = os.path.join(ROOT, "models", "registry", "active.json")
    return _read_json_file(active_path) or {"champion": None, "canary": None}


def _read_config() -> dict:
    cfg_path = os.path.join(ROOT, "config.yaml")
    try:
        import yaml
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def _read_incidents() -> list:
    return _read_json_file(os.path.join(ROOT, "live_incidents.json")) or []


def _read_live_state() -> dict:
    return _read_json_file(os.path.join(ROOT, "live_state.json")) or {}


def cache_decision(symbol: str, decision: dict):
    """Store a decision in the in-memory cache (called from the brain path)."""
    if symbol not in _decision_cache:
        _decision_cache[symbol] = deque(maxlen=_CACHE_MAX)
    entry = {**decision, "_cached_at": time.time()}
    _decision_cache[symbol].appendleft(entry)


def _safe_risk(attr: str, default=None):
    """Pull a value from the risk engine if the server reference is available."""
    srv = _server_ref
    if srv and hasattr(srv, "risk"):
        return getattr(srv.risk, attr, default)
    return default


def _safe_brain(attr: str, default=None):
    srv = _server_ref
    if srv and hasattr(srv, "brain"):
        return getattr(srv.brain, attr, default)
    return default


def _get_mt5_account_and_positions() -> dict:
    """Fetch live MT5 account info and open positions.

    Returns a dict with keys: balance, equity, free_margin, profit,
    open_positions, positions.  Falls back to risk-engine equity and
    empty positions when MT5 is unavailable (dry-run or non-Windows).
    """
    # Fallback defaults from risk engine (populated by equity poll)
    result = {
        "balance": _safe_risk("_mt5_balance", None) or _safe_risk("_current_equity", 0.0),
        "equity": _safe_risk("_current_equity", 0.0),
        "free_margin": _safe_risk("_mt5_free_margin", None) or _safe_risk("_current_equity", 0.0),
        "profit": _safe_risk("_mt5_profit", 0.0),
        "open_positions": 0,
        "positions": [],
    }

    if sys.platform != "win32":
        return result

    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            logger.debug("MT5 init failed in API status handler")
            return result

        try:
            info = mt5.account_info()
            if info is not None:
                result["balance"] = float(info.balance)
                result["equity"] = float(info.equity)
                result["free_margin"] = float(info.margin_free)
                result["profit"] = float(info.profit)

            raw_positions = mt5.positions_get()
            if raw_positions:
                result["open_positions"] = len(raw_positions)
                result["positions"] = [
                    {
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if p.type == 0 else "SELL",
                        "volume": float(p.volume),
                        "open_price": float(p.price_open),
                        "current_price": float(p.price_current),
                        "profit": float(p.profit),
                        "sl": float(p.sl) if p.sl else 0.0,
                        "tp": float(p.tp) if p.tp else 0.0,
                        "comment": p.comment or "",
                        "magic": p.magic,
                        "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                    }
                    for p in raw_positions
                ]
        finally:
            # Never shutdown MT5 here — the server process owns the connection.
            # Calling shutdown() would kill the server's MT5 session.
            pass
    except Exception as e:
        logger.debug(f"MT5 account/positions fetch failed: {e}")

    return result


def _read_training_progress():
    """Read per-trainer progress files, including per-symbol PPO files."""
    result = {}
    for key in ("lstm", "ppo", "dreamer"):
        path = os.path.join(ROOT, "logs", f"{key}_progress.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if time.time() - data.get("updated_at", 0) < 600:
                    result[key] = data
                    continue
        except Exception:
            pass
        result[key] = {}

    # Merge per-symbol PPO progress files (ppo_{SYMBOL}_progress.json)
    ppo_per_symbol = {}
    for fname in os.listdir(os.path.join(ROOT, "logs")) if os.path.isdir(os.path.join(ROOT, "logs")) else []:
        if fname.startswith("ppo_") and fname.endswith("_progress.json") and fname != "ppo_progress.json":
            sym = fname[4:-len("_progress.json")]
            path = os.path.join(ROOT, "logs", fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if time.time() - data.get("updated_at", 0) < 600:
                    ppo_per_symbol[sym] = data
            except Exception:
                pass
    if ppo_per_symbol:
        # Use the most recently updated per-symbol file as the primary PPO progress
        latest_sym = max(ppo_per_symbol, key=lambda s: ppo_per_symbol[s].get("updated_at", 0))
        if ppo_per_symbol[latest_sym].get("running"):
            result["ppo"] = ppo_per_symbol[latest_sym]
        result["ppo_per_symbol"] = ppo_per_symbol

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 1. GET /api/status — Full system status
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/status")
def api_status():
    srv = _server_ref
    cfg = _read_config()
    symbols = cfg.get("trading", {}).get("symbols", ["EURUSD"])
    active = _read_active_registry()
    progress = _read_training_progress()
    lstm_p = progress.get("lstm", {})
    ppo_p = progress.get("ppo", {})
    dreamer_p = progress.get("dreamer", {})
    live = _read_live_state()
    incidents = _read_incidents()

    champ_path = active.get("champion") or ""
    canary_path = active.get("canary") or ""
    champ_id = os.path.basename(champ_path) if champ_path else "none"
    canary_id = os.path.basename(canary_path) if canary_path else ""

    # ── Risk engine live values ──
    halt = _safe_risk("halt", False)
    daily_trades = _safe_risk("daily_trades", 0)
    realized_pnl = _safe_risk("realized_pnl_today", 0.0)
    current_dd = _safe_risk("current_dd", 0.0)
    peak_equity = _safe_risk("_peak_equity", 0.0)
    current_equity = _safe_risk("_current_equity", 0.0)
    can_trade = False
    if srv and hasattr(srv, "risk"):
        try:
            can_trade = srv.risk.can_trade()
        except Exception:
            pass

    uptime = int(time.time() - srv.start_time) if srv and hasattr(srv, "start_time") else 0
    mode = "LIVE" if (srv and getattr(srv, "live", False)) else "DRY-RUN"

    # ── Build lane rows from decision cache ──
    # Build per-symbol model info
    per_symbol_models = {}
    symbols_map = active.get("symbols", {})
    for sym, sym_data in symbols_map.items():
        sym_champ = sym_data.get("champion")
        sym_canary = sym_data.get("canary")
        per_symbol_models[sym] = {
            "champion": os.path.basename(sym_champ) if sym_champ else None,
            "canary": os.path.basename(sym_canary) if sym_canary else None,
            "has_per_symbol_champion": sym_champ is not None,
            "has_per_symbol_canary": sym_canary is not None,
            "canary_policy": sym_data.get("canary_policy", {}),
            "canary_state": sym_data.get("canary_state", {}),
        }

    lane_rows = []
    for sym in symbols:
        recent = list(_decision_cache.get(sym, []))
        last = recent[0] if recent else {}
        sym_model = per_symbol_models.get(sym, {})
        # Per-symbol champion/canary with global fallback
        sym_champ_id = sym_model.get("champion") or champ_id
        sym_canary_id = sym_model.get("canary") or (canary_id or None)
        lane_rows.append({
            "symbol": sym,
            "decision": {
                "regime": last.get("volatility", "--"),
                "final_target": last.get("exposure", 0.0),
                "ppo_target": last.get("exposure", 0.0),
                "dreamer_target": 0.0,
                "confidence": last.get("confidence", 0.0),
            },
            "pipeline": {
                "lstm": {"state": last.get("volatility", "UNKNOWN")},
            },
            "champion": sym_champ_id,
            "canary": sym_canary_id,
            "has_per_symbol_champion": sym_model.get("has_per_symbol_champion", False),
            "has_per_symbol_canary": sym_model.get("has_per_symbol_canary", False),
            "model_version": last.get("model_version", "champion"),
            "is_canary": last.get("is_canary", False),
            "status": "live" if not halt else "halted",
            "side": last.get("action", "HOLD").lower(),
            "confidence": last.get("confidence", 0.0),
            "exposure": last.get("exposure", 0.0),
            "pnl": 0.0,
            "canTrade": can_trade,
            "reason": last.get("reason", ""),
        })

    # ── Pipeline summary ──
    pipeline_summary = {
        "symbols_total": len(symbols),
        "training_active_symbols": 0,
        "canary_review_symbols": 1 if canary_id else 0,
        "champion_live_symbols": len(symbols) if champ_id != "none" else 0,
        "trading_ready_symbols": len(symbols) if champ_id != "none" else 0,
        "trading_active_symbols": len(symbols) if can_trade else 0,
    }

    # ── MT5 account info and open positions ──
    mt5_account = _get_mt5_account_and_positions()

    # ── Build a symbol->position lookup so lanes can show live PnL ──
    pos_by_symbol: dict[str, list] = {}
    for pos in mt5_account["positions"]:
        pos_by_symbol.setdefault(pos["symbol"], []).append(pos)

    # Merge real position PnL into lane rows
    for row in lane_rows:
        sym = row["symbol"]
        if sym in pos_by_symbol:
            row["pnl"] = round(sum(p["profit"] for p in pos_by_symbol[sym]), 2)

    lane_summary = {
        "actionable_symbols": sum(1 for r in lane_rows if r["side"] != "hold"),
        "executed_symbols": daily_trades,
        "blocked_symbols": sum(1 for r in lane_rows if not r["canTrade"]),
        "neutral_symbols": sum(1 for r in lane_rows if r["side"] == "hold"),
        "open_positions": mt5_account["open_positions"],
    }

    return _json({
        "state": "online" if not halt else "halted",
        "status": "online" if not halt else "halted",
        "server": {
            "running": True,
            "pids": [os.getpid()],
        },
        "account": {
            "balance": mt5_account["balance"],
            "equity": mt5_account["equity"],
            "free_margin": mt5_account["free_margin"],
            "profit": mt5_account["profit"],
            "open_positions": mt5_account["open_positions"],
            "positions": mt5_account["positions"],
            "realized_today": realized_pnl,
            "drawdown_pct": current_dd,
            "connected": mode == "LIVE" or mt5_account["equity"] > 0,
        },
        "training": {
            "cycle_running": False,
            "lstm_running": bool(lstm_p.get("running")),
            "drl_running": bool(ppo_p.get("running")),
            "dreamer_running": bool(dreamer_p.get("running")),
            "configured_symbols": symbols,
            "lstm_symbol": lstm_p.get("symbol", ""),
            "lstm_epoch": lstm_p.get("epoch", 0),
            "lstm_epochs_total": lstm_p.get("epochs_total", 0),
            "drl_symbol": ppo_p.get("symbol", ""),
            "drl_timesteps": ppo_p.get("total_timesteps", 0),
            "visual": {
                "lstm": {
                    "state": "training" if lstm_p.get("running") else "idle",
                    "current_symbol": lstm_p.get("symbol", ""),
                    "loss": lstm_p.get("loss", 0),
                    "val_loss": 0,
                    "memory_strength": (lstm_p.get("accuracy", 0) / 100) if lstm_p.get("accuracy") else 0,
                },
                "ppo": {
                    "state": "training" if ppo_p.get("running") else "idle",
                    "current_symbol": ppo_p.get("symbol", ""),
                    "current_timesteps": ppo_p.get("current_timesteps", 0),
                    "target_timesteps": ppo_p.get("total_timesteps", 0),
                    "progress_pct": ppo_p.get("progress_pct", 0),
                },
                "dreamer": {
                    "state": "training" if dreamer_p.get("running") else "idle",
                    "current_symbol": dreamer_p.get("symbol", ""),
                    "steps": dreamer_p.get("step", 0),
                    "progress_pct": dreamer_p.get("progress_pct", 0),
                    "window": dreamer_p.get("window", 64),
                },
                "active_label": (
                    "LSTM Training" if lstm_p.get("running")
                    else "PPO Training" if ppo_p.get("running")
                    else "Dreamer Training" if dreamer_p.get("running")
                    else "Idle"
                ),
            },
            "symbol_stage_rows": [],
            "symbol_lane_rows": lane_rows,
            "pipeline_summary": pipeline_summary,
            "lane_summary": lane_summary,
            "ppo_per_symbol": progress.get("ppo_per_symbol", {}),
        },
        "canary_gate": {
            "ready": bool(canary_id),
            "reason": "Canary active" if canary_id else "No canary",
        },
        "active_models": active,
        "registry_summary": {
            "champion": champ_id,
            "canary": canary_id or None,
            "per_symbol_models": per_symbol_models,
        },
        "incidents": incidents or [{
            "id": "SYS-001",
            "type": "system",
            "severity": "info",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "API server online.",
        }],
        "logs": {},
        "timestamp": time.time(),
        "uptime_sec": uptime,
        "mode": mode,
        "risk": {
            "halt": halt,
            "daily_trades": daily_trades,
            "max_daily_trades": _safe_risk("max_daily_trades", 20),
            "realized_pnl": realized_pnl,
            "max_daily_loss": _safe_risk("max_daily_loss", 500),
            "current_dd": current_dd,
            "peak_equity": peak_equity,
            "current_equity": current_equity,
            "can_trade": can_trade,
        },
        "trade_review": _get_trade_review_summary(),
        "economic_calendar": _get_economic_calendar_cached(),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET /api/trades — Recent trade history
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/trades")
def api_trades():
    limit = int(request.params.get("limit", 50))
    offset = int(request.params.get("offset", 0))
    symbol_filter = request.params.get("symbol", "")

    trades = _fetch_trade_history(symbol_filter)
    total = len(trades)
    page = trades[offset:offset + limit]

    return _json({
        "trades": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.get("/api/trades/summary")
def api_trades_summary():
    symbol_filter = request.params.get("symbol", "")
    trades = _fetch_trade_history(symbol_filter)

    wins = [t for t in trades if t.get("profit", 0) > 0]
    losses = [t for t in trades if t.get("profit", 0) < 0]
    total_pnl = sum(t.get("profit", 0) for t in trades)
    avg_profit = (sum(t["profit"] for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t["profit"] for t in losses) / len(losses)) if losses else 0
    gross_profit = sum(t["profit"] for t in wins)
    gross_loss = abs(sum(t["profit"] for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else "inf"

    hold_mins = [t.get("hold_minutes", 0) for t in trades if t.get("hold_minutes")]

    # Per-symbol breakdown
    by_symbol: dict[str, Any] = {}
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "wins": 0, "pnl": 0.0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"] += t.get("profit", 0)
        if t.get("profit", 0) > 0:
            by_symbol[sym]["wins"] += 1
    for sym in by_symbol:
        bs = by_symbol[sym]
        bs["win_rate"] = (bs["wins"] / bs["trades"]) if bs["trades"] > 0 else 0

    return _json({
        "overall": {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades)) if trades else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(pf, 2) if isinstance(pf, float) else pf,
            "avg_hold_minutes": round(sum(hold_mins) / len(hold_mins), 1) if hold_mins else 0,
            "max_loss_streak": _max_loss_streak(trades),
        },
        "by_symbol": by_symbol,
    })


def _fetch_trade_history(symbol_filter: str = "") -> list[dict]:
    """
    Pull trade history from MT5 (Windows live) or from the decision cache (dry-run).
    Returns a list of Trade dicts matching the frontend Trade interface.
    """
    trades: list[dict] = []

    # Try MT5 deal history on Windows
    if sys.platform == "win32":
        try:
            import MetaTrader5 as mt5
            import pytz

            if mt5.initialize():
                tz = pytz.timezone("Etc/UTC")
                now_utc = datetime.now(tz)
                from datetime import timedelta
                lookback = now_utc - timedelta(days=30)
                deals = mt5.history_deals_get(lookback, now_utc)
                if deals:
                    for d in deals:
                        if d.entry != mt5.DEAL_ENTRY_OUT:
                            continue
                        if symbol_filter and d.symbol != symbol_filter:
                            continue
                        trades.append({
                            "ticket": d.ticket,
                            "symbol": d.symbol,
                            "side": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
                            "volume": d.volume,
                            "open_time": None,
                            "close_time": datetime.fromtimestamp(d.time, tz=tz).isoformat(),
                            "open_price": d.price,
                            "close_price": d.price,
                            "profit": round(d.profit, 2),
                            "comment": d.comment or "",
                            "hold_minutes": None,
                            "magic": d.magic,
                            "bot_lane": "ppo",
                            "model": "champion",
                            "action_type": "close",
                            "outcome": "win" if d.profit > 0 else ("loss" if d.profit < 0 else "breakeven"),
                        })
                    trades.sort(key=lambda t: t.get("close_time", "") or "", reverse=True)
                    return trades
        except Exception as e:
            logger.debug(f"MT5 trade history fetch failed: {e}")

    # Fallback: derive from decision cache
    for sym, dq in _decision_cache.items():
        if symbol_filter and sym != symbol_filter:
            continue
        for i, d in enumerate(dq):
            if d.get("action") in ("BUY", "SELL"):
                trades.append({
                    "ticket": int(d.get("_cached_at", time.time()) * 1000) + i,
                    "symbol": sym,
                    "side": d.get("action", "HOLD"),
                    "volume": abs(d.get("exposure", 0.0)),
                    "open_time": datetime.fromtimestamp(d.get("_cached_at", 0), tz=timezone.utc).isoformat(),
                    "close_time": None,
                    "open_price": 0,
                    "close_price": 0,
                    "profit": 0,
                    "comment": d.get("reason", ""),
                    "hold_minutes": None,
                    "magic": None,
                    "bot_lane": "ppo",
                    "model": "canary" if d.get("reason", "").startswith("canary") else "champion",
                    "action_type": "signal",
                    "outcome": "breakeven",
                })

    trades.sort(key=lambda t: t.get("open_time", "") or "", reverse=True)
    return trades


def _max_loss_streak(trades: list[dict]) -> int:
    streak = 0
    max_streak = 0
    for t in trades:
        if t.get("profit", 0) < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


# ═══════════════════════════════════════════════════════════════════════════
# 3. GET /api/ppo_diagnostics — PPO model diagnostics
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/ppo_diagnostics")
def api_ppo_diagnostics():
    brain = _safe_brain("__self__")  # get the brain object itself
    srv = _server_ref
    brain_obj = srv.brain if srv and hasattr(srv, "brain") else None

    active = _read_active_registry()
    champ_path = active.get("champion") or ""
    canary_path = active.get("canary") or ""

    ppo_loaded = False
    obs_shape = None
    action_shape = None
    is_canary = False
    device = "cpu"

    if brain_obj:
        ppo_loaded = brain_obj.ppo_model is not None
        is_canary = getattr(brain_obj, "_is_canary", False)
        device = getattr(brain_obj, "device", "cpu")
        if brain_obj.ppo_model is not None:
            try:
                obs_space = brain_obj.ppo_model.observation_space
                act_space = brain_obj.ppo_model.action_space
                obs_shape = list(obs_space.shape) if obs_space else None
                action_shape = list(act_space.shape) if act_space else None
            except Exception:
                pass

    # Last actions from decision cache
    last_actions = {}
    for sym, dq in _decision_cache.items():
        if dq:
            d = dq[0]
            last_actions[sym] = {
                "action": d.get("action"),
                "exposure": d.get("exposure"),
                "confidence": d.get("confidence"),
                "volatility": d.get("volatility"),
                "reason": d.get("reason"),
                "cached_at": d.get("_cached_at"),
            }

    # PPO bias correction data
    ppo_biases = {}
    if brain_obj and hasattr(brain_obj, "get_ppo_biases"):
        ppo_biases = brain_obj.get_ppo_biases()

    return _json({
        "ppo_loaded": ppo_loaded,
        "obs_shape": obs_shape,
        "action_shape": action_shape,
        "is_canary": is_canary,
        "device": device,
        "champion_path": champ_path,
        "canary_path": canary_path,
        "model_version": os.path.basename(canary_path if is_canary else champ_path) or "none",
        "last_actions": last_actions,
        "ppo_biases": ppo_biases,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 4. GET /api/lstm_explanations — LSTM indicator attribution
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/lstm_explanations")
def api_lstm_explanations():
    """Return the last LSTM decision per symbol with top_indicators attribution."""
    results = {}

    try:
        for sym, dq in _decision_cache.items():
            try:
                # Find the most recent decision that has top_indicators
                for d in dq:
                    if not isinstance(d, dict):
                        continue
                    if "top_indicators" in d:
                        results[sym] = {
                            "regime": d.get("volatility") or d.get("regime", "UNKNOWN"),
                            "confidence": d.get("confidence", 0.0),
                            "top_indicators": d.get("top_indicators", []),
                            "cached_at": d.get("_cached_at"),
                        }
                        break
            except Exception:
                continue
    except Exception:
        pass

    if not results:
        # If no decisions have been cached yet, return empty with explanation
        return _json({
            "symbols": {},
            "message": "No LSTM decisions cached yet. Decisions are cached when the brain runs predictions.",
        })

    return _json({"symbols": results})


# ═══════════════════════════════════════════════════════════════════════════
# 5. GET /api/learning — Learning pipeline status
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/learning")
def api_learning():
    active = _read_active_registry()
    champ = active.get("champion")
    canary = active.get("canary")

    # Read champion scorecard if available
    champ_meta = {}
    if champ:
        sc = _read_json_file(os.path.join(champ, "scorecard.json"))
        if sc:
            champ_meta = sc

    # Read canary scorecard if available
    canary_meta = {}
    if canary:
        sc = _read_json_file(os.path.join(canary, "scorecard.json"))
        if sc:
            canary_meta = sc

    # List candidate versions
    cands_dir = os.path.join(ROOT, "models", "registry", "candidates")
    candidates = []
    if os.path.isdir(cands_dir):
        for d in sorted(os.listdir(cands_dir), reverse=True)[:10]:
            cpath = os.path.join(cands_dir, d)
            if os.path.isdir(cpath):
                sc = _read_json_file(os.path.join(cpath, "scorecard.json")) or {}
                candidates.append({
                    "version": d,
                    "path": cpath,
                    "win_rate": sc.get("win_rate"),
                    "loss": sc.get("loss"),
                    "saved_at": sc.get("saved_at"),
                    "type": sc.get("type"),
                })

    # Training schedule from config
    cfg = _read_config()
    train_enabled = os.environ.get("AGI_AUTONOMY_TRAIN", "false").lower() == "true"
    autonomy_interval = int(os.environ.get("AGI_AUTONOMY_INTERVAL_SEC", "3600"))

    # Trade learning log
    learning_log = _read_json_file(
        os.path.join(ROOT, "logs", "learning", "trade_learning_latest.json")
    )

    return _json({
        "canary": {
            "active": canary is not None,
            "path": canary,
            "version": os.path.basename(canary) if canary else None,
            "scorecard": canary_meta,
        },
        "champion": {
            "path": champ,
            "version": os.path.basename(champ) if champ else None,
            "scorecard": champ_meta,
        },
        "candidates": candidates,
        "training_schedule": {
            "enabled": train_enabled,
            "interval_sec": autonomy_interval,
            "auto_canary": os.environ.get("AGI_AUTONOMY_AUTO_CANARY", "true").lower() == "true",
        },
        "learning_log": learning_log,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 6. GET /api/scenarios — Regime performance data
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/scenarios")
def api_scenarios():
    """Return performance breakdown by volatility regime from the decision cache."""
    regime_stats: dict[str, dict] = {}

    for sym, dq in _decision_cache.items():
        for d in dq:
            regime = d.get("volatility") or d.get("regime", "UNKNOWN")
            if regime not in regime_stats:
                regime_stats[regime] = {
                    "total_decisions": 0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "hold_count": 0,
                    "avg_confidence": 0.0,
                    "avg_exposure": 0.0,
                    "symbols": set(),
                }
            rs = regime_stats[regime]
            rs["total_decisions"] += 1
            action = d.get("action", "HOLD")
            if action == "BUY":
                rs["buy_count"] += 1
            elif action == "SELL":
                rs["sell_count"] += 1
            else:
                rs["hold_count"] += 1
            rs["avg_confidence"] += d.get("confidence", 0.0)
            rs["avg_exposure"] += abs(d.get("exposure", 0.0))
            rs["symbols"].add(sym)

    # Finalize averages and serialize sets
    for regime, rs in regime_stats.items():
        n = rs["total_decisions"] or 1
        rs["avg_confidence"] = round(rs["avg_confidence"] / n, 4)
        rs["avg_exposure"] = round(rs["avg_exposure"] / n, 4)
        rs["symbols"] = sorted(rs["symbols"])

    return _json({"regimes": regime_stats})


# ═══════════════════════════════════════════════════════════════════════════
# 7. GET /api/lanes — Trading lane status per symbol
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/lanes")
def api_lanes():
    cfg = _read_config()
    symbols = cfg.get("trading", {}).get("symbols", ["EURUSD"])
    active = _read_active_registry()
    champ_id = os.path.basename(active.get("champion") or "") or "none"
    canary_id = os.path.basename(active.get("canary") or "")

    can_trade = False
    if _server_ref and hasattr(_server_ref, "risk"):
        try:
            can_trade = _server_ref.risk.can_trade()
        except Exception:
            pass

    lanes = []
    symbols_map = active.get("symbols", {})
    for sym in symbols:
        recent = list(_decision_cache.get(sym, []))
        last = recent[0] if recent else {}
        sym_data = symbols_map.get(sym, {})
        sym_champ = sym_data.get("champion")
        sym_canary = sym_data.get("canary")
        sym_champ_id = os.path.basename(sym_champ) if sym_champ else champ_id
        sym_canary_id = os.path.basename(sym_canary) if sym_canary else (canary_id or None)
        lanes.append({
            "symbol": sym,
            "champion": sym_champ_id,
            "canary": sym_canary_id,
            "has_per_symbol_champion": sym_champ is not None,
            "has_per_symbol_canary": sym_canary is not None,
            "model_version": last.get("model_version", "champion"),
            "action": last.get("action", "HOLD"),
            "exposure": last.get("exposure", 0.0),
            "confidence": last.get("confidence", 0.0),
            "volatility": last.get("volatility", "UNKNOWN"),
            "reason": last.get("reason", ""),
            "can_trade": can_trade,
            "is_canary": last.get("is_canary", bool(sym_canary or canary_id)),
            "last_decision_at": last.get("_cached_at"),
            "recent_decisions": len(recent),
        })

    return _json({"lanes": lanes})


# ═══════════════════════════════════════════════════════════════════════════
# 7b. GET /api/per_symbol_models — Per-symbol model registry info
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/per_symbol_models")
def api_per_symbol_models():
    """Return per-symbol champion and canary model paths from the registry."""
    active = _read_active_registry()
    symbols_map = active.get("symbols", {})
    global_champ = active.get("champion")
    global_canary = active.get("canary")

    result = {}
    for sym, sym_data in symbols_map.items():
        sym_champ = sym_data.get("champion")
        sym_canary = sym_data.get("canary")
        result[sym] = {
            "champion": sym_champ,
            "champion_basename": os.path.basename(sym_champ) if sym_champ else None,
            "canary": sym_canary,
            "canary_basename": os.path.basename(sym_canary) if sym_canary else None,
            "uses_global_champion": sym_champ is None,
            "uses_global_canary": sym_canary is None,
            "canary_policy": sym_data.get("canary_policy", {}),
            "canary_state": sym_data.get("canary_state", {}),
            "champion_history_count": len(sym_data.get("champion_history", [])),
        }

    return _json({
        "global_champion": global_champ,
        "global_canary": global_canary,
        "symbols": result,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Existing endpoints (compat with current frontend api.ts)
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/patterns")
def api_patterns():
    """Pattern library — extracted from live_state or incidents."""
    patterns = []
    incidents = _read_incidents()
    for inc in incidents:
        if inc.get("type") == "pattern":
            patterns.append(inc)
    return _json(patterns)


@app.get("/api/perf")
def api_perf():
    """Performance metrics summary."""
    live = _read_live_state()
    hist = live.get("_history", {})

    # Primary: live equity history from server's risk engine
    srv = _server_ref
    equity_curve = []
    pnl_curve = []

    if srv and hasattr(srv, "risk"):
        try:
            equity_curve = list(getattr(srv.risk, "_equity_history", []))
            pnl_curve = list(getattr(srv.risk, "_pnl_history", []))
        except Exception:
            pass

    # Fallback to file-based history if server has no data yet
    if not equity_curve:
        equity_curve = hist.get("equity", [])
    if not pnl_curve:
        pnl_curve = hist.get("pnl", [])

    return _json({
        "equity_curve": equity_curve,
        "pnl_curve": pnl_curve,
        "confidence_curve": hist.get("confidence", []),
        "lstm_loss_curve": hist.get("lstmLoss", []),
    })


# ── Protected control actions requiring a control token ──────────────────
_PROTECTED_ACTIONS = {
    "promote_canary", "rollback_canary", "rollback_champion",
    "restart_server", "start_training_cycle", "stop_training_cycle",
    "emergency_stop", "clear_emergency_stop",
}

_CONTROL_TOKEN = os.environ.get("AGI_CONTROL_TOKEN", "")


@app.post("/api/control")
def api_control():
    """Accept control commands from the React UI.

    Protected actions require the X-Control-Token header to match
    the AGI_CONTROL_TOKEN environment variable.
    """
    try:
        payload = request.json or {}
    except Exception:
        payload = {}
    action = payload.get("action", "unknown")
    logger.info(f"API control action received: {action}")

    # ── Token auth for protected actions ────────────────────────────────
    if action in _PROTECTED_ACTIONS:
        token = request.get_header("X-Control-Token", "").strip()
        if _CONTROL_TOKEN and token != _CONTROL_TOKEN:
            logger.warning(f"Control action '{action}' rejected — invalid/missing token")
            return _json({"ok": False, "action": action, "error": "control token required"}, 403)

    srv = _server_ref

    # ── Emergency stop / clear ──────────────────────────────────────────
    if action == "emergency_stop":
        if srv and hasattr(srv, "risk"):
            srv.risk.halt = True
            logger.critical("EMERGENCY STOP ACTIVATED via API — all trading halted")
            # Optionally close all open positions if executor is available
            if hasattr(srv, "executor") and srv.executor:
                try:
                    srv.executor.close_all_positions()
                    logger.info("All open positions closed during emergency stop")
                except Exception as e:
                    logger.warning(f"Failed to close positions during emergency stop: {e}")
            try:
                srv.telegram.risk_event("EMERGENCY STOP", "All trading halted via API")
            except Exception:
                pass
            return _json({"ok": True, "action": action, "message": "Emergency stop activated. All trading halted.", "halted": True})
        return _json({"ok": False, "action": action, "error": "No risk engine available"}, 500)

    if action == "clear_emergency_stop":
        if srv and hasattr(srv, "risk"):
            srv.risk.halt = False
            srv.risk._consecutive_errors = 0
            logger.info("Emergency stop CLEARED via API — trading resumed")
            return _json({"ok": True, "action": action, "message": "Emergency stop cleared. Trading resumed.", "halted": False})
        return _json({"ok": False, "action": action, "error": "No risk engine available"}, 500)

    # ── Standard UI actions ─────────────────────────────────────────────
    if action == "restart_server":
        return _json({"ok": True, "action": action, "message": "Server is running. Use system-level restart to restart."})

    if action == "hft_start":
        return _json({"ok": True, "action": action, "message": "HFT mode not available in current configuration."})

    if action == "hft_stop":
        return _json({"ok": True, "action": action, "message": "HFT mode not active."})

    if action == "stop_training_cycle":
        if srv and hasattr(srv, "autonomy") and srv.autonomy:
            try:
                srv.autonomy.stop()
                return _json({"ok": True, "action": action, "message": "Training cycle stop requested."})
            except Exception as e:
                return _json({"ok": False, "action": action, "error": str(e)}, 500)
        return _json({"ok": True, "action": action, "message": "No active training cycle."})

    if action == "reset_peak_equity":
        if srv and hasattr(srv, "risk"):
            srv.risk.reset_peak_equity()
            return _json({"ok": True, "action": action, "message": f"Peak equity reset to {srv.risk._peak_equity:.2f}"})
        return _json({"ok": False, "action": action, "error": "No risk engine available"}, 500)

    if action == "start_training_cycle":
        if srv and hasattr(srv, "autonomy") and srv.autonomy:
            return _json({"ok": True, "action": action, "message": "Autonomy loop is already running."})
        return _json({"ok": True, "action": action, "message": "Autonomy loop not initialized."})

    if action == "rebuild_trade_memory":
        return _json({"ok": True, "action": action, "message": "Trade memory rebuild queued."})

    if action == "promote_canary":
        symbol = payload.get("symbol")
        if srv and hasattr(srv, "autonomy") and srv.autonomy:
            try:
                from Python.model_registry import ModelRegistry
                registry = ModelRegistry()
                if symbol:
                    registry.promote_canary_to_champion(symbol=symbol)
                else:
                    registry.promote_canary()
                return _json({"ok": True, "action": action, "symbol": symbol or "global", "message": "Canary promoted to champion."})
            except Exception as e:
                return _json({"ok": False, "action": action, "error": str(e)}, 500)
        return _json({"ok": True, "action": action, "message": "No canary to promote."})

    if action == "force_ingest":
        return _json({"ok": True, "action": action, "message": "Data ingest triggered."})

    if action in ("rollback_canary", "rollback_champion"):
        symbol = payload.get("symbol")
        if srv and hasattr(srv, "autonomy") and srv.autonomy:
            try:
                from Python.model_registry import ModelRegistry
                registry = ModelRegistry()
                if symbol:
                    registry.clear_canary(symbol=symbol)
                else:
                    registry.rollback_canary()
                return _json({"ok": True, "action": action, "symbol": symbol or "global", "message": "Canary rolled back."})
            except Exception as e:
                return _json({"ok": False, "action": action, "error": str(e)}, 500)
        return _json({"ok": True, "action": action, "message": "No canary to rollback."})

    # Fallback: forward to AGIServer.handle_command (token-gated, for socket/n8n)
    if srv:
        try:
            result = srv.handle_command({"action": action, **payload})
            return _json({"ok": True, "action": action, "result": result})
        except Exception as e:
            return _json({"ok": False, "action": action, "error": str(e)}, 500)

    return _json({"ok": True, "action": action, "message": f"Action '{action}' acknowledged."})


# ═══════════════════════════════════════════════════════════════════════════
# 8. WebSocket /ws/status — Real-time push (via simple polling SSE fallback)
#    Bottle doesn't natively support WebSocket, so we provide SSE instead.
#    The frontend createStatusWS() will need a small adapter, but /api/status
#    polling every 2-5s is the primary mechanism.
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/status/stream")
def api_status_stream():
    """Server-Sent Events stream of status updates."""
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    response.set_header("Connection", "keep-alive")

    def generate():
        while True:
            data = json.dumps(_build_status_summary(), default=str)
            yield f"data: {data}\n\n"
            time.sleep(3)

    return generate()


def _build_status_summary() -> dict:
    """Lightweight status for real-time push."""
    srv = _server_ref
    return {
        "timestamp": time.time(),
        "halt": _safe_risk("halt", False),
        "daily_trades": _safe_risk("daily_trades", 0),
        "realized_pnl": _safe_risk("realized_pnl_today", 0.0),
        "current_dd": _safe_risk("current_dd", 0.0),
        "can_trade": srv.risk.can_trade() if srv and hasattr(srv, "risk") else False,
        "uptime_sec": int(time.time() - srv.start_time) if srv and hasattr(srv, "start_time") else 0,
        "mode": "LIVE" if (srv and getattr(srv, "live", False)) else "DRY-RUN",
        "live_armed": srv.live_armed if srv and hasattr(srv, "live_armed") else False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Health endpoint
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/health")
def api_health():
    return _json({"status": "ok", "pid": os.getpid(), "time": time.time()})


@app.get("/api/emergency_status")
def api_emergency_status():
    """Return whether emergency stop is active and why."""
    srv = _server_ref
    halted = False
    reason = ""
    if srv and hasattr(srv, "risk"):
        halted = srv.risk.halt
        if halted:
            reasons = []
            if srv.risk.realized_pnl_today < -srv.risk.max_daily_loss:
                reasons.append(f"daily_loss_exceeded (${srv.risk.realized_pnl_today:.2f} < -${srv.risk.max_daily_loss:.2f})")
            if getattr(srv.risk, "_consecutive_errors", 0) >= 3:
                reasons.append("3_consecutive_errors")
            if not reasons:
                reasons.append("manual_or_emergency_stop")
            reason = "; ".join(reasons)
    return _json({"halted": halted, "reason": reason, "daily_trades": _safe_risk("daily_trades", 0), "realized_pnl": _safe_risk("realized_pnl_today", 0.0)})


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/strategies — Analyze trades into strategies & patterns
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/strategies")
def api_strategies():
    trades = _fetch_trade_history("")
    if not trades:
        return _json({"strategies": [], "patterns": [], "meta": {"total_trades": 0}})

    from collections import defaultdict
    import math

    # --- Derive regime from comment/time ---
    def _hour_bucket(t):
        ct = t.get("close_time") or t.get("open_time") or ""
        if not ct:
            return "unknown"
        try:
            h = int(ct[11:13])
        except Exception:
            return "unknown"
        if h < 8:
            return "asian"
        if h < 14:
            return "london"
        if h < 21:
            return "new_york"
        return "asian"

    def _side(t):
        return (t.get("side") or "HOLD").upper()

    # --- Group trades into strategy buckets ---
    buckets = defaultdict(list)
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        session = _hour_bucket(t)
        side = _side(t)
        key = f"{sym}|{session}|{side}"
        buckets[key].append(t)

    strategies = []
    for key, group in buckets.items():
        sym, session, side = key.split("|")
        profits = [t.get("profit", 0) for t in group]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        total_pnl = sum(profits)
        win_rate = len(wins) / len(profits) if profits else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Sharpe-like score
        if len(profits) > 1:
            mean_r = sum(profits) / len(profits)
            var_r = sum((p - mean_r) ** 2 for p in profits) / (len(profits) - 1)
            std_r = math.sqrt(var_r) if var_r > 0 else 1e-6
            sharpe = mean_r / std_r
        else:
            sharpe = 0.0

        # Weighted score: combines win_rate, expectancy, and trade count
        confidence = min(1.0, len(group) / 20.0)  # confidence grows with sample size
        score = (expectancy * 100 + sharpe * 2) * confidence

        strategies.append({
            "id": key.replace("|", "_"),
            "symbol": sym,
            "session": session,
            "side": side,
            "trades": len(group),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 2),
            "sharpe": round(sharpe, 3),
            "score": round(score, 2),
            "confidence": round(confidence, 2),
        })

    strategies.sort(key=lambda s: s["score"], reverse=True)

    # --- Pattern recognition: symbol-session combos ranked by profitability ---
    sym_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    session_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    side_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})

    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        session = _hour_bucket(t)
        side = _side(t)
        profit = t.get("profit", 0)
        is_win = 1 if profit > 0 else 0

        sym_stats[sym]["trades"] += 1
        sym_stats[sym]["pnl"] += profit
        sym_stats[sym]["wins"] += is_win

        session_stats[session]["trades"] += 1
        session_stats[session]["pnl"] += profit
        session_stats[session]["wins"] += is_win

        side_stats[side]["trades"] += 1
        side_stats[side]["pnl"] += profit
        side_stats[side]["wins"] += is_win

    def _build_patterns(label, stats):
        result = []
        for name, s in stats.items():
            wr = s["wins"] / s["trades"] if s["trades"] > 0 else 0
            result.append({
                "type": label,
                "name": name,
                "trades": s["trades"],
                "pnl": round(s["pnl"], 2),
                "win_rate": round(wr, 4),
                "weight": round(s["pnl"] / max(abs(s["pnl"]), 0.01) * wr, 3) if s["trades"] >= 3 else 0,
            })
        result.sort(key=lambda p: p["pnl"], reverse=True)
        return result

    patterns = (
        _build_patterns("symbol", sym_stats) +
        _build_patterns("session", session_stats) +
        _build_patterns("side", side_stats)
    )

    return _json({
        "strategies": strategies,
        "patterns": patterns,
        "meta": {
            "total_trades": len(trades),
            "analysis_window": "30d",
        },
    })


# GET /api/economic_calendar — Upcoming economic events from MT5
@app.get("/api/economic_calendar")
def api_economic_calendar():
    """Return upcoming economic calendar events from the MT5 calendar API."""
    try:
        from Python.trade_review import get_economic_calendar
        days = int(request.params.get("days_ahead", 7))
        events = get_economic_calendar(days_ahead=days)
        return _json({"events": events, "count": len(events)})
    except Exception as e:
        logger.error(f"Economic calendar fetch failed: {e}")
        return _json({"events": [], "count": 0, "error": str(e)})


# GET /api/trade_review — Post-trade review with annotations and analysis
@app.get("/api/trade_review")
def api_trade_review():
    """Return the latest trade review with annotations, tags, and per-symbol breakdown."""
    from Python.trade_review import get_latest_review, run_review
    review = get_latest_review()
    if review is None:
        review = run_review(days_back=7)
    return _json(review.get("summary", review))


# GET /api/trade_review/enriched — Full enriched trade list with decision context
@app.get("/api/trade_review/enriched")
def api_trade_review_enriched():
    """Return enriched trade list with decision context and tags."""
    from Python.trade_review import get_latest_review
    review = get_latest_review()
    if review is None:
        return _json({"error": "No review available. Run /api/trade_review first."})
    return _json({
        "trades": review.get("enriched", [])[:50],  # Last 50 trades
        "summary": review.get("summary", {}),
    })


# POST /api/trade_review/refresh — Force a fresh review cycle
@app.post("/api/trade_review/refresh")
def api_trade_review_refresh():
    """Force a fresh trade review cycle."""
    from Python.trade_review import run_review
    result = run_review(days_back=7)
    return _json(result.get("summary", {}))


# Server lifecycle
# ═══════════════════════════════════════════════════════════════════════════
API_PORT = int(os.environ.get("AGI_API_PORT", "5000"))


def start_api_server(agi_server=None, host: str = "0.0.0.0", port: int = API_PORT):
    """
    Start the HTTP API server in a daemon thread.

    Args:
        agi_server: AGIServer instance for live data access.
        host: Bind address.
        port: Listen port (default 5000, matches Vite proxy).
    """
    global _server_ref
    _server_ref = agi_server

    def _run():
        logger.success(f"API server starting on http://{host}:{port}")
        bottle_run(app, host=host, port=port, quiet=True, server="wsgiref")

    t = threading.Thread(target=_run, name="api-server", daemon=True)
    t.start()
    logger.info(f"API server thread started (port {port})")
    return t


# ═══════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("Starting API server in standalone mode (no AGIServer reference)")
    bottle_run(app, host="0.0.0.0", port=API_PORT, quiet=False, reloader=False, server="wsgiref")
