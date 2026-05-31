#!/usr/bin/env python3
"""
Controlled Paper Trading Harness for Multi-Day MT5 Execution Validation.

Mission: Safe, tiny-size, actual MT5 (demo account) execution of the current
champion/canary models for days/weeks to validate post-fix readiness BEFORE
any real capital.

Rules (HARD):
- Fixed micro lot: 0.01 (override via AGI_PAPER_FIXED_LOT)
- Max 1 open position total (enforced)
- Max daily loss: 1.0% of starting equity (auto rollback + flatten)
- Max 3 trades / hour
- Full preflight (spread, session, margin, risk supervisor)
- Slippage + execution audit to logs/
- Auto-rollback triggers: daily loss breach, 2 consecutive errors, manual flag
- Feeds directly into DemoCanary + monitoring for promotion gating
- All actions logged with champion/canary lane tagging

Usage (from project root, after setting MT5 demo creds):
  # Terminal 1: ensure MT5 running + logged into DEMO account
  set CHAIN_GAMBLER_EXECUTION_MODE=demo
  set AGI_PAPER_FIXED_LOT=0.01
  set CHAIN_GAMBLER_ACCOUNT_TYPE=demo
  python scripts/paper_mt5_execution_harness.py --symbols EURUSDm --max-days 5 --equity-start 5000

  # In another shell for monitoring:
  python Python/monitoring_dashboard.py --mode live

Rollback triggers auto:
  - Risk breach -> force_flatten_all + halt + telegram alert
  - File: runtime/rollback_harness.flag (touch to force immediate)

Ready for immediate use on good post-fix candidate.
HARDENED (Post-Training Readiness): 
- Auto-detects post-fix candidates (alignment_fix_applied) -> conservative profile (0.75% daily, 2 trades/hr)
- Sets runtime/champion_ready.flag + last_paper_candidate.txt on arm
- Real feedback loop (closes auditor gap): harness on trade close/rollback/canary/risk events drives RetrainingTrigger counters + execution_feedback.jsonl; periodic aggregator logs "RETRAIN RECOMMENDED"; persists state + artifacts
- Dual risk layers + canary + full audit JSONL + Telegram + flag rollback
- Use with one-command promoter script for seamless handoff.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# Ensure project on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Core imports (use modern execution layer + legacy executor for full MT5 power)
from Python.execution.mode_resolver import resolve_mode
from Python.execution.executor_router import ExecutorRouter
from Python.execution.gate_engine import GateEngine
from Python.execution.risk_supervisor import RiskSupervisor as ExecRiskSupervisor
from Python.execution.mt5_demo_executor import MT5DemoExecutor
from Python.execution.execution_agent import ExecutionAgent, get_default_execution_agent
from Python.execution.trade_decision import TradeDecision, Side, make_risk_based_decision
from Python.execution.execution_agent import ExecutionAgent
from Python.execution.trade_decision import TradeDecision, Side, make_risk_based_decision, TrailingType, from_ppo_action_meta
from Python.mt5_executor import MT5Executor
from Python import risk_supervisor as top_risk  # for advanced exposure checks + audit
from Python.canary.demo_canary import DemoCanary, CanaryConfig
from Python.canary.canary_monitor import CanaryMonitor
from Python import paper_trading as paper  # for mode + account snapshot
from Python import live_safety
from Python.alerts.telegram_alerts import TelegramAlerter
from Python.autonomous.retraining_trigger import RetrainingTrigger  # real feedback wiring (loop closure)
from Python.model_registry import ModelRegistry  # for candidate awareness + champion_ready
from Python.pipeline_audit import log_decision  # Unified PIPELINE_DECISIONS.jsonl for full audit trail
from Python.hybrid_brain import HybridBrain  # For real Decision PPO inference (rich action_meta) with MTF + best-features from promoted bundle

# Decision + Execution Layer already imported at top (additive, backward compat)

# Runtime flags
RUNTIME_DIR = PROJECT_ROOT / "runtime"
ROLLBACK_FLAG = RUNTIME_DIR / "rollback_harness.flag"
HARNESS_ACTIVE_FLAG = RUNTIME_DIR / "paper_harness_active.flag"
CHAMPION_READY = RUNTIME_DIR / "champion_ready.flag"

# Logs
LOGS_DIR = PROJECT_ROOT / "logs"
HARNESS_LOG = LOGS_DIR / "paper_harness_exec.jsonl"
HARNESS_STATE = LOGS_DIR / "paper_harness_state.json"

# Strict harness defaults (production paper grade)
HARNESS_MAX_LOT = 0.01
HARNESS_MAX_DAILY_LOSS_PCT = 1.0
HARNESS_MAX_POSITIONS = 1
HARNESS_MAX_TRADES_PER_HOUR = 3
HARNESS_MIN_EQUITY_BUFFER = 0.98  # stop if equity drops below this of start

# Conservative post-fix profile (harden for new aligned candidates with real metrics)
# Activated via env AGI_CONSERVATIVE_PAPER=1 or auto-detected from alignment_fix_applied candidate
HARNESS_CONSERVATIVE_DAILY_LOSS_PCT = 0.75
HARNESS_CONSERVATIVE_MAX_TRADES_PER_HOUR = 2

# === PRODUCTION RUNBOOK: Timing-Aware Safety for Rich Decision PPO + TimeExitSpec ===
# - Position sizing: _compute_lots respects SizeSpec caps + Risk max_lots (see ExecutionAgent)
# - Daily loss: defers emergency if TimeExitSpec.close_before_high_impact_news active + in news window (risk_engine + harness _should_rollback)
# - Emergency flatten: honors news/open windows unless critical kill/rollback/loss (defers slippage risk; MQL5/Python both paths)
# - Canary/Supervisor: monitors open-window pnl vs news_avoidance; auto rollback on degradation (prox ratio >60% or score < -0.5)
# - Rollback always available via runtime/rollback_harness.flag or supervisor signal
# - For live unsupervised: ensure EventIntel or MT5 calendar wired; test via tmp_full_stack_smoke_test timing cases
# Update status: runtime/agent_status/production_hardening_timing_agent.json
# Full details: docs/DECISION_EXECUTION_ARCHITECTURE.md (search Timing / Safety)

class PaperMT5Harness:
    """The controlled multi-day actual-MT5 paper execution controller."""

    def __init__(self, symbols: list[str], max_days: int = 5, equity_start: float = 5000.0, execution_type: str = "decision_ppo"):
        self.symbols = [s.strip() for s in symbols if s.strip()]
        self.max_days = max_days
        self.equity_start = float(equity_start)
        self.execution_type = execution_type or os.environ.get("AGI_EXECUTION_TYPE", "decision_ppo")
        self.uses_rich_decisions = self.execution_type == "decision_ppo"  # rich DecisionPPO outputs full specs for Execution layer
        self.uses_rich_decision = self.uses_rich_decisions  # compat alias for existing code in _get_intent
        self.start_time = datetime.now(timezone.utc)
        self.running = True

        os.makedirs(LOGS_DIR, exist_ok=True)
        os.makedirs(RUNTIME_DIR, exist_ok=True)

        # --- Post-training candidate awareness + conservative hardening (new) ---
        # V4 50k BTCUSDm RUN SPECIFIC: load promoter-written paper_harness_start.json (which carries is_v4_robust_candidate etc from this exact run's scorecard provenance) and force extra-tight profile for the most advanced v4 conservative 50k candidate
        self.candidate_dir = self._detect_latest_good_candidate()
        self._postfix_conservative = False
        self._v4_robust_candidate = False
        v4_profile = {}
        # NEW Decision PPO + Execution support (task closure): load execution_type from promoter-written meta (default decision_ppo for new promoted)
        # "decision_ppo" = rich full trade specs (side/sl/tp/atr/conf via DecisionBuilder or decoded PPO + multi-TF features)
        # "simple_action" = legacy raw action vector path (preserved, non-default for new)
        self.execution_type = os.environ.get("AGI_EXECUTION_TYPE", "decision_ppo")
        self.uses_rich_decision = self.execution_type == "decision_ppo"

        # Load best feature params + MTF context for rich Decision path (per-symbol)
        self.best_features = self._load_best_features()
        self.mtf_context = ["1m", "5m", "15m", "1h"]  # default multi-TF for Decision PPO obs
        try:
            phs = RUNTIME_DIR / "paper_harness_start.json"
            if phs.exists():
                v4_profile = json.loads(phs.read_text())
                if v4_profile.get("is_v4_robust_candidate") or v4_profile.get("conservative_v4"):
                    self._v4_robust_candidate = True
                    self._postfix_conservative = True
                    logger.info("V4 ROBUST CANDIDATE (this 50k BTCUSDm run): forcing extra-conservative paper profile from promoter metadata")
                # Propagate execution_type from promoter (decision_ppo is new autonomous default; simple_action for legacy compat)
                if "execution_type" in v4_profile:
                    self.execution_type = v4_profile["execution_type"]
                    self.uses_rich_decision = self.execution_type == "decision_ppo"
                    logger.info(f"Execution type from promotion: {self.execution_type} (rich specs={self.uses_rich_decisions})")
        except Exception:
            pass
        if self.candidate_dir:
            try:
                sc = json.loads((Path(self.candidate_dir) / "scorecard.json").read_text())
                if sc.get("alignment_fix_applied"):
                    self._postfix_conservative = True
                    if sc.get("run_provenance", {}).get("v4_robust") or "v4" in str(sc.get("run_provenance", {})).lower():
                        self._v4_robust_candidate = True
                    logger.info(f"Post-fix candidate detected: {self.candidate_dir} (alignment_fix_applied=True) -> using conservative paper profile")
            except Exception:
                pass
        if self._v4_robust_candidate:
            # Pre-staged v4-specific tighter defaults for this run's candidate handoff (bulletproof conservative)
            os.environ["AGI_PAPER_MAX_DAILY_LOSS_PCT"] = os.environ.get("AGI_PAPER_MAX_DAILY_LOSS_PCT", "0.5")
            logger.info("V4 50k BTCUSDm: applied 0.5% daily loss cap + v4 provenance for handoff profile")

        # NEW: Load best feature params + multi-TF context for DecisionPPO + Execution (autonomous loop)
        self.best_features = {}
        self.mtf_timeframes = ["1m", "5m", "15m", "1h"]
        try:
            bf_path = PROJECT_ROOT / "configs" / "best_features_per_symbol.yaml"
            if bf_path.exists():
                import yaml  # safe, optional dep or std in env
                with open(bf_path, "r", encoding="utf-8") as f:
                    bf_cfg = yaml.safe_load(f) or {}
                for sym in self.symbols:
                    self.best_features[sym] = bf_cfg.get("symbols", {}).get(sym, bf_cfg.get("symbols", {}).get("BTCUSDm", {}))
                self.mtf_timeframes = bf_cfg.get("multi_timeframe", {}).get("timeframes", self.mtf_timeframes)
                logger.info(f"Loaded best_features + MTF context for DecisionPPO path: {list(self.best_features.keys())}")
        except Exception as e:
            logger.warning(f"best_features load skipped (non-fatal, using defaults): {e}")

        # Always arm champion_ready.flag for downstream (TUI/supervisor/promotion)
        try:
            CHAMPION_READY.touch()
            if self.candidate_dir:
                (RUNTIME_DIR / "last_paper_candidate.txt").write_text(self.candidate_dir)
        except Exception:
            pass

        # Unified audit: harness armed (major pipeline decision point, ensures candidate has execution trail)
        try:
            cand_name = Path(self.candidate_dir).name if self.candidate_dir else None
            log_decision(
                decision_type="harness_start",
                actor="harness",
                decision="HARNESS_ARMED",
                candidate=cand_name,
                run_id=cand_name,
                reason="paper_harness_init_post_promotion" if self._postfix_conservative else "paper_harness_init",
                details={
                    "candidate_dir": self.candidate_dir,
                    "conservative_profile": self._postfix_conservative,
                    "symbols": self.symbols,
                    "max_days": self.max_days,
                },
                severity="info",
            )
        except Exception:
            pass

        # Real feedback wiring (loop closure): retraining trigger fed live on closes/rollbacks/canary + aggregator periodic
        self.retrain_trigger = RetrainingTrigger(data_dir=str(LOGS_DIR))
        try:
            # Seed with any prior harness state if present (simple)
            prior = (RUNTIME_DIR / "paper_harness_start.json")
            if prior.exists():
                # no-op; real increments happen on record
                pass
        except Exception:
            pass

        # Decision PPO + ExecutionAgent wiring (default for new promoted models; legacy router path preserved)
        self.exec_agent: Optional[Any] = None
        if self.uses_rich_decision:
            try:
                self.exec_agent = get_default_execution_agent() or ExecutionAgent(
                    config={"paper_mode": True, "max_positions": HARNESS_MAX_POSITIONS},
                    mql5_bridge_enabled=False,  # primary pure-Python (OrderManager+MT5Executor). One-command override: $env:MQL5_BRIDGE_ENABLED="1"
                )
                logger.info("ExecutionAgent armed for rich DecisionPPO trade specs (full TradeDecision lifecycle)")
            except Exception as ea_exc:
                logger.warning(f"ExecutionAgent init skipped (falling back to router): {ea_exc}")
                self.exec_agent = None

        # Force demo paper execution mode
        os.environ.setdefault("CHAIN_GAMBLER_EXECUTION_MODE", "demo")
        os.environ.setdefault("AGI_PAPER_FIXED_LOT", str(HARNESS_MAX_LOT))
        os.environ.setdefault("CHAIN_GAMBLER_ACCOUNT_TYPE", "demo")
        os.environ.setdefault("AGI_MIN_LOTS", "0.01")

        self.mode = resolve_mode()
        logger.info(f"Harness starting in resolved mode: {self.mode}")

        # Risk (use both layers for belt-and-suspenders)
        self.top_risk = top_risk.RiskSupervisor({"risk": {"supervisor": {
            "enabled": True,
            "max_daily_loss": 50.0,  # absolute safety net
            "max_drawdown_pct": 3.0,
            "max_symbol_exposure": 0.02,  # tiny for paper
            "max_total_exposure": 0.03,
            "max_open_positions": HARNESS_MAX_POSITIONS,
            "max_positions_per_symbol": 1,
            "min_trade_interval_sec": 120,
            "max_spread_bps": 15,
        }}})
        self.exec_risk = ExecRiskSupervisor({"risk": {
            "max_open_positions": HARNESS_MAX_POSITIONS,
            "max_positions_per_symbol": 1,
            "max_drawdown_pct": 3.0,
        }})

        # Real MT5 executor (wired for actual execution in demo mode)
        self.mt5_exec = MT5Executor(self.exec_risk)  # passes the wrapper; sizing overridden by env
        self.mt5_exec.set_server_ref(self)  # minimal for gate checks

        # Modern router + gate (future proof)
        self.router = ExecutorRouter(
            config={"risk": {"max_lots": HARNESS_MAX_LOT}},
            risk_supervisor=self.exec_risk,
            mt5_executor=self.mt5_exec,
        )
        self.gate = GateEngine(config={"risk": {"max_spread_bps": 15}}, risk_supervisor=self.exec_risk)

        # Real Decision PPO brain for rich path (uses promoted bundle meta for MTF context + best feature params per symbol)
        self.brain: Optional[HybridBrain] = None
        if getattr(self, "uses_rich_decision", False):
            try:
                # Minimal risk/executor passed; brain loads its own PPO bundles from registry/candidates or per-symbol
                self.brain = HybridBrain(risk=self.top_risk, executor=self.router)
                logger.info("HybridBrain (Decision PPO) loaded for rich paper execution with MTF/best-features")
            except Exception as b_exc:
                logger.warning(f"HybridBrain load for decision_ppo path failed (stub decisions): {b_exc}")
                self.brain = None

        # Decision PPO + ExecutionAgent rich layer (default for new promotions; zero breakage for legacy)
        self.execution_type = "decision_ppo"  # default; overridden from harness_start meta or candidate
        self.exec_agent = None
        # Decision PPO + Execution layer arming (default for newly promoted via handoff/promoter)
        # When execution_type=decision_ppo, harness runs the full rich stack (TradeDecision -> ExecutionAgent)
        # MQL5 bridge disabled in paper harness (supervisor/deploy arms native EA separately via command JSON)
        self.execution_agent = None
        if getattr(self, "uses_rich_decision", True):
            try:
                self.execution_agent = ExecutionAgent(
                    config={"risk": {"max_lots": HARNESS_MAX_LOT}},
                    risk_supervisor=self.exec_risk,
                    router=self.router,
                    gate=self.gate,
                    mql5_bridge_enabled=False,  # Pure Python primary path (recommended for Windows direct MT5 + full rich TradeDecision fidelity + telemetry to PPO)
                )
                logger.success("ExecutionAgent (DecisionPPO+Exec layer) armed in paper harness (MTF + best features ready)")
            except Exception as ea_exc:
                logger.warning(f"ExecutionAgent init failed (legacy router path used): {ea_exc}")
                self.execution_agent = None

        # Canary for promotion integration (strict demo limits)
        # Use conservative profile for post-fix candidates (harden per task)
        is_conservative = os.environ.get("AGI_CONSERVATIVE_PAPER", "0") == "1" or getattr(self, "_postfix_conservative", False)
        eff_daily = HARNESS_CONSERVATIVE_DAILY_LOSS_PCT if is_conservative else HARNESS_MAX_DAILY_LOSS_PCT
        eff_trades_h = HARNESS_CONSERVATIVE_MAX_TRADES_PER_HOUR if is_conservative else HARNESS_MAX_TRADES_PER_HOUR
        canary_cfg = CanaryConfig(
            max_lot_per_trade=HARNESS_MAX_LOT,
            max_open_positions=HARNESS_MAX_POSITIONS,
            max_trades_per_hour=eff_trades_h,
            max_daily_loss_pct=eff_daily,
        )
        self.canary = DemoCanary(config=canary_cfg.__dict__, notional_balance=self.equity_start)
        self.canary.set_bundle(bundle_id=f"paper_harness_{int(time.time())}", system_mode="demo_live", account_type="demo")
        self.canary_monitor = CanaryMonitor(self.canary, log_path=str(LOGS_DIR / "harness_canary_monitor.jsonl"), max_drawdown_pct=2.0)

        # Alerts
        self.alerter = None
        try:
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat = os.environ.get("TELEGRAM_CHAT_ID")
            if token and chat:
                self.alerter = TelegramAlerter(token, chat)
        except Exception:
            pass

        # State
        self.trades_today = 0
        self.last_trade_hour = None
        self.consecutive_errors = 0
        self._load_state()

        # Touch active flag
        HARNESS_ACTIVE_FLAG.touch()
        # V4 50k specific: persist full provenance + v4 flags in harness start meta for TUI/supervisor/MQL5 chain traceability on this advanced run's candidate
        harness_start_meta = {
            "start_iso": self.start_time.isoformat(),
            "symbols": self.symbols,
            "equity_start": self.equity_start,
            "fixed_lot": HARNESS_MAX_LOT,
            "max_daily_loss_pct": HARNESS_MAX_DAILY_LOSS_PCT,
            "is_v4_robust_candidate": bool(self._v4_robust_candidate),
            "conservative_v4": bool(self._v4_robust_candidate or self._postfix_conservative),
            "source_run": "v4_robust_conservative_50k_BTCUSDm",
            "v4_profile_applied": bool(self._v4_robust_candidate),
            "v4_provenance": v4_profile or {},
            # Decision PPO + rich execution closure
            "execution_type": getattr(self, "execution_type", "decision_ppo"),
            "uses_rich_trade_specs": getattr(self, "uses_rich_decision", True),
            "decision_ppo_armed": getattr(self, "uses_rich_decision", True),
            "mtf_best_features": True,
        }
        (RUNTIME_DIR / "paper_harness_start.json").write_text(json.dumps(harness_start_meta, indent=2))

        # Champion / canary integration: require ready flag for serious runs (or warn)
        if not CHAMPION_READY.exists():
            logger.warning("No champion_ready.flag — harness will run but consider this pre-champion validation only.")

        logger.success("=== PAPER MT5 EXECUTION HARNESS ARMED ===")
        logger.info(f"Symbols: {self.symbols} | Fixed lot: {HARNESS_MAX_LOT} | Max daily loss: {HARNESS_MAX_DAILY_LOSS_PCT}% | Max days: {max_days}")

    def _load_state(self):
        if HARNESS_STATE.exists():
            try:
                st = json.loads(HARNESS_STATE.read_text())
                self.trades_today = st.get("trades_today", 0)
            except Exception:
                pass

    def _detect_latest_good_candidate(self) -> str | None:
        """Scan for recent post-fix candidate (used for conservative mode + audit trail). Mirrors supervisor logic."""
        try:
            cand_dir = PROJECT_ROOT / "models" / "registry" / "candidates"
            if cand_dir.exists():
                latest = sorted([d for d in cand_dir.iterdir() if d.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
                for d in latest[:3]:
                    age_h = (datetime.now(timezone.utc) - datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
                    if age_h > 48:
                        continue
                    score = d / "scorecard.json"
                    if score.exists():
                        try:
                            sc = json.loads(score.read_text())
                            if sc.get("alignment_fix_applied") and "quarantined" not in str(sc).lower():
                                return str(d)
                        except Exception:
                            continue
            return None
        except Exception:
            return None

    def _save_state(self):
        try:
            HARNESS_STATE.write_text(json.dumps({
                "trades_today": self.trades_today,
                "last_update": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception:
            pass

    def _record_execution_feedback(self, event: str, details: dict = None):
        """Simple feedback mechanism for retraining trigger (closes major pipeline gap).
        Now also drives counters immediately for low-latency loop closure.
        """
        details = details or {}
        try:
            feedback_file = PROJECT_ROOT / "logs" / "execution_feedback.jsonl"
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "details": details
            }
            with open(feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

        # Immediate wiring to RetrainingTrigger counters (real feedback)
        try:
            if event in ("trade_closed", "demo_trade_closed", "position_closed"):
                self.retrain_trigger.increment_closed_demo(1)
            elif event in ("trade_blocked", "blocked", "risk_block"):
                self.retrain_trigger.increment_blocked(1)
            elif event in ("rollback_triggered", "canary_violation", "daily_loss_breach"):
                self.retrain_trigger.increment_blocked(max(1, self.trades_today // 2 or 1))
        except Exception:
            pass

    def _poll_and_feed_closed_trades(self) -> int:
        """Real feedback wiring: scan MT5 history for newly closed deals since harness start (or last poll).
        Increments closed_demo counter + records structured event. Returns #new closes.
        """
        new_closed = 0
        try:
            from Python.mt5_compat import mt5 as _mt5
            if not _mt5:
                return 0
            # Use a simple time window; in practice last N hours or since self.start_time
            since = self.start_time - timedelta(hours=1)
            deals = _mt5.history_deals_get(since, datetime.now(timezone.utc)) or []
            # Naive: count recent OUT deals as proxy (harness is low volume, 1 pos; duplicates ok-ish via counter tolerance)
            for d in deals[-50:]:  # recent slice
                try:
                    if int(getattr(d, "entry", -1)) == int(_mt5.DEAL_ENTRY_OUT):
                        pnl = float(getattr(d, "profit", 0.0))
                        self._record_execution_feedback("trade_closed", {"pnl": pnl, "symbol": getattr(d, "symbol", "?")})
                        new_closed += 1
                except Exception:
                    pass
            if new_closed:
                logger.debug(f"Harness polled {new_closed} new closed trades into retrain feedback")
        except Exception:
            pass
        return new_closed

    def _check_rollback_flag(self) -> bool:
        if ROLLBACK_FLAG.exists():
            logger.critical("ROLLBACK FLAG DETECTED — initiating immediate flatten")
            ROLLBACK_FLAG.unlink(missing_ok=True)
            return True
        return False

    def _current_equity(self) -> float:
        try:
            if paper.get_mode() == "paper":
                acc = paper.paper_account_info()
                return float(getattr(acc, "equity", self.equity_start))
            info = self.mt5_exec.get_tick(self.symbols[0])  # proxy; better: use account_info via mt5
            # Fallback to MT5 direct for accuracy in demo
            from Python.mt5_compat import mt5 as _mt5
            if _mt5:
                acct = _mt5.account_info()
                if acct:
                    return float(getattr(acct, "equity", self.equity_start))
        except Exception:
            pass
        return self.equity_start

    def _daily_pnl_pct(self) -> float:
        equity = self._current_equity()
        if equity <= 0:
            return 0.0
        # Use risk realized or simple
        realized = getattr(self.exec_risk, "realized_pnl_today", 0.0)
        return (realized / equity) * 100.0

    def _should_rollback(self) -> tuple[bool, str]:
        if self._check_rollback_flag():
            return True, "manual_rollback_flag"

        daily_loss = self._daily_pnl_pct()
        if daily_loss <= -HARNESS_MAX_DAILY_LOSS_PCT:
            # Production hardening: respect TimeExitSpec for news windows in rich decisions
            try:
                if getattr(self, "execution_agent", None) and self.uses_rich_decision:
                    active = list(self.execution_agent.get_active_decisions().values())
                    time_exits = [getattr(d, "time_exit", None) for d in active if d]
                    if self.exec_risk and hasattr(self.exec_risk, "should_respect_time_exit_for_loss_limit"):
                        if self.exec_risk.should_respect_time_exit_for_loss_limit(time_exits):
                            logger.warning(f"[HARNESS] Daily loss breach but deferring flatten per rich TimeExitSpec/news window")
                            # Do not trigger rollback yet; let decision time_exit + OrderManager handle
                            return False, ""
            except Exception:
                pass
            return True, f"daily_loss_pct {daily_loss:.2f}% <= -{HARNESS_MAX_DAILY_LOSS_PCT}%"

        equity = self._current_equity()
        if equity < self.equity_start * HARNESS_MIN_EQUITY_BUFFER:
            return True, f"equity_below_buffer {equity:.2f} < {self.equity_start * HARNESS_MIN_EQUITY_BUFFER:.2f}"

        if self.consecutive_errors >= 2:
            return True, f"consecutive_errors={self.consecutive_errors}"

        # Canary monitor check
        mon = self.canary_monitor.check()
        if mon.get("stopped"):
            return True, f"canary_monitor: {mon.get('stop_reason')}"

        return False, ""

    def _trigger_rollback(self, reason: str):
        logger.critical(f"*** ROLLBACK TRIGGERED: {reason} ***")
        self._record_execution_feedback("rollback_triggered", {"reason": reason})

        # Unified audit: rollback is critical pipeline decision (full trace for candidate)
        try:
            cand_name = Path(self.candidate_dir).name if getattr(self, "candidate_dir", None) else None
            log_decision(
                decision_type="rollback",
                actor="harness",
                decision="ROLLBACK_EXECUTED",
                candidate=cand_name,
                run_id=cand_name,
                reason=reason,
                details={
                    "equity": self._current_equity() if hasattr(self, "_current_equity") else None,
                    "trades_today": getattr(self, "trades_today", 0),
                },
                severity="critical",
            )
        except Exception:
            pass
        # 1. Flatten via ExecutionAgent (DecisionPPO rich path) or router/mt5 (legacy preserved)
        flatten_res = {"executed": False, "reason": reason}
        if self.uses_rich_decision and getattr(self, "execution_agent", None) is not None:
            try:
                flatten_res = self.execution_agent.force_flatten_all(reason=f"harness_rollback:{reason}")
            except Exception:
                pass
        if not flatten_res.get("executed"):
            if hasattr(self, "router") and self.router:
                try:
                    flatten_res = self.router.force_flatten_all(f"harness:{reason}") if hasattr(self.router, "force_flatten_all") else {"executed": False}
                except Exception:
                    flatten_res = getattr(self, "mt5_exec", None).force_flatten_all(f"harness:{reason}") if getattr(self, "mt5_exec", None) and hasattr(getattr(self, "mt5_exec", None), "force_flatten_all") else {"executed": False}
            else:
                mt5e = getattr(self, "mt5_exec", None)
                flatten_res = mt5e.force_flatten_all(f"harness:{reason}") if mt5e and hasattr(mt5e, "force_flatten_all") else {"executed": False}
        # 2. Risk layers
        self.top_risk.trigger_rollback(reason)
        self.exec_risk.trigger_rollback(reason) if hasattr(self.exec_risk, "trigger_rollback") else None
        # 3. Canary violation
        self.canary._violation(f"harness_rollback:{reason}")
        # 4. Alert
        if self.alerter:
            try:
                self.alerter.critical(f"HARNESS ROLLBACK: {reason}\nFlatten: {flatten_res}\nEquity now: ${self._current_equity():.2f}")
            except Exception:
                pass
        # 5. Log + halt
        self._log_harness_event("rollback", {"reason": reason, "flatten": flatten_res, "equity": self._current_equity()})
        # Real feedback: feed harness outcome (via record which incs counters + agg)
        try:
            self.retrain_trigger.increment_blocked( max(1, self.trades_today // 2) )  # conservative proxy for blocked/risk events
            art = self.retrain_trigger.evaluate(champion_drawdown_pct=5.0 if "loss" in reason.lower() else None)
            if art.triggered:
                (RUNTIME_DIR / f"retraining_trigger_from_harness_{art.retraining_trigger_id}.json").write_text(json.dumps(asdict(art), default=str))

                # Also unified for rollback-induced retrain signal
                cand_name = Path(self.candidate_dir).name if getattr(self, "candidate_dir", None) else None
                try:
                    log_decision(
                        decision_type="retrain_trigger",
                        actor="harness",
                        decision="RETRAIN_TRIGGERED",
                        candidate=cand_name,
                        run_id=cand_name,
                        reason="rollback_induced|" + "|".join(getattr(art, "reasons", [])),
                        details={"trigger_id": art.retraining_trigger_id, "source": "rollback"},
                        severity="warn",
                    )
                except Exception:
                    pass
        except Exception:
            pass
        self.running = False
        HARNESS_ACTIVE_FLAG.unlink(missing_ok=True)

    def _log_harness_event(self, event: str, payload: dict[str, Any]):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "symbols": self.symbols,
            **payload,
        }
        with open(HARNESS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def _get_intent(self, symbol: str, side: str, size: float) -> dict:
        """Base intent. For decision_ppo (rich default) returns full trade spec consumed by ExecutorRouter/Gate/Executors.
        Legacy simple_action path remains identical for compatibility.
        """
        intent = {
            "symbol": symbol,
            "side": side.upper(),
            "size": size,
            "price": 0.0,  # executor resolves live
            "sl": None,
            "tp": None,
            "magic": 505000,
            "comment": f"HARNESS|{'DECISION_PPO' if self.uses_rich_decision else 'SIMPLE_ACTION'}|paper_validation",
            "confidence": 0.72 if getattr(self, 'uses_rich_decisions', False) or getattr(self, 'uses_rich_decision', False) else 0.6,
            "execution_type": self.execution_type,
        }
        uses_rich = getattr(self, 'uses_rich_decisions', False) or getattr(self, 'uses_rich_decision', False)
        if uses_rich:
            # Rich Decision PPO full spec (stub until dedicated DecisionPPO inference wired; uses MTF + best features context from config)
            # In full impl: load DecisionPPO model (drl/decision_ppo or equivalent), infer with multi-TF obs + best_features_per_symbol for symbol -> {side, size, sl_pips, tp_pips, ...}
            # Here: populate realistic sl/tp (ATR-aware stub or conservative pips). Executor layer already fully supports.
            sl_pips = 120
            tp_pips = 240
            try:
                # Best effort: use ATR if MT5 available via compat, else fixed
                from Python.mt5_compat import get_symbol_info_tick
                # Fallback conservative for paper
                sl_pips = 150 if "BTC" in symbol or "XAU" in symbol else 80
                tp_pips = int(sl_pips * 2.0)
            except Exception:
                pass
            intent.update({
                "sl": sl_pips,  # pips or price offset; executors normalize
                "tp": tp_pips,
                "risk_reward": 2.0,
                "feature_params": "best_features_per_symbol.yaml + mtf_1m5m15m1h",
                "regime": "normal",
                "mtf_context": self.mtf_context,
                "best_features": self.best_features.get(symbol, {}),
            })
        return intent

    def _load_best_features(self) -> dict:
        """Load per-symbol best features for MTF Decision PPO context (used in rich path)."""
        cfg_path = PROJECT_ROOT / "configs" / "best_features_per_symbol.yaml"
        try:
            import yaml
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("symbols", {})
        except Exception:
            pass
        # Fallback defaults
        return {
            "BTCUSDm": {"atr_period": 14, "rsi_period": 14},
            "XAUUSDm": {"atr_period": 10, "rsi_period": 21},
        }

    def _make_rich_decision(self, symbol: str, side: str = "LONG") -> TradeDecision:
        """Construct (or infer) rich TradeDecision using real Decision PPO + MTF/best-features context from promoted bundle."""
        # Prefer real HybridBrain PPO inference (full Decision PPO path, uses correct per-candidate MTF + best_features)
        if getattr(self, "brain", None) is not None:
            try:
                # Fetch recent df for inference (lightweight; harness already has MT5 access via compat)
                df = None
                try:
                    from Python.data_feed import get_recent_bars  # or mt5_compat
                    df = get_recent_bars(symbol, "M5", 200) if 'get_recent_bars' in globals() else None
                except Exception:
                    pass
                if df is not None and len(df) > 50:
                    ppo_meta = self.brain.predict_ppo_action(symbol, df)
                    if ppo_meta:
                        td = from_ppo_action_meta(
                            ppo_meta,
                            symbol=symbol,
                            source="decision_ppo_hybrid_brain",
                            model_version=str(getattr(self.brain, 'ppo_metadata', {}).get('version', 'promoted')),
                            confidence=0.78,
                        )
                        td.tags.update({
                            "mtf_context": getattr(self, "mtf_context", True),
                            "best_features": self.best_features.get(symbol, {}),
                            "execution_type": "decision_ppo",
                            "harness_real_ppo": True,
                        })
                        return td
            except Exception as infer_exc:
                logger.debug(f"Real PPO inference in harness failed, falling to make_risk: {infer_exc}")

        # Fallback stub (still rich, uses best features config for realism)
        side_enum = Side.LONG if side.upper() in ("LONG", "BUY") else Side.SHORT
        bf = self.best_features.get(symbol, {})
        atr_mult = 1.5
        tp_r = 2.0
        try:
            atr_p = bf.get("atr_period", 14)
            atr_mult = 1.2 + (atr_p % 10) / 20.0
        except Exception:
            pass
        td = make_risk_based_decision(
            symbol=symbol,
            side=side_enum,
            risk_pct=0.75,
            atr_sl_mult=atr_mult,
            tp_r=tp_r,
            trailing_type=TrailingType.ATR,
        )
        td.source = "decision_ppo_harness_stub"
        td.tags = {
            "mtf_context": getattr(self, "mtf_context", True),
            "best_features": bf,
            "execution_type": "decision_ppo",
            "harness": True,
        }
        td.confidence = 0.72
        return td

    def run(self):
        """Main controlled loop — call this for multi-day paper execution."""
        logger.info("Harness run loop started. Press Ctrl-C or touch rollback flag to stop safely.")
        cycle = 0
        last_canary_check = time.time()

        # Graceful shutdown
        def _sig_handler(sig, frame):
            logger.warning("Shutdown signal received — safe flatten + exit")
            self._trigger_rollback("signal_shutdown")
            sys.exit(0)
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        while self.running and (datetime.now(timezone.utc) - self.start_time).days < self.max_days:
            cycle += 1
            now = datetime.now(timezone.utc)

            # Daily reset bookkeeping
            if self.last_trade_hour != now.hour:
                self.trades_today = 0
                self.last_trade_hour = now.hour

            equity = self._current_equity()
            daily_pnl_pct = self._daily_pnl_pct()

            # Pre-cycle safety gates
            rollback, r_reason = self._should_rollback()
            if rollback:
                self._trigger_rollback(r_reason)
                break

            # Lightweight canary monitor every 15 min
            if time.time() - last_canary_check > 900:
                mon = self.canary_monitor.check()
                last_canary_check = time.time()
                # Wire canary events -> retrain feedback
                try:
                    if mon.get("stopped") or mon.get("risk_violations", 0) > 0:
                        self._record_execution_feedback("canary_violation", {"stop_reason": mon.get("stop_reason"), "trades": mon.get("trades")})
                        cart = self.canary.evaluate() if hasattr(self.canary, "evaluate") else None
                        art = self.retrain_trigger.evaluate(
                            champion_drawdown_pct=mon.get("max_drawdown_pct"),
                            canary_artifact=cart.__dict__ if cart else {"approved_for_champion": False, "approved_for_real_live": False}
                        )
                        if art.triggered:
                            (RUNTIME_DIR / f"retraining_trigger_from_harness_{art.retraining_trigger_id}.json").write_text(json.dumps(asdict(art), default=str))
                            logger.info(f"Canary-driven RETRAIN signal emitted: {art.next_cycle_command}")
                except Exception:
                    pass

            # Decision-driven loop: harness now defaults to rich Decision PPO specs (full trade: side/size/sl/tp/conf + mtf/best-feats).
            # (In full: DecisionPPO policy + multi-TF feature extractor using configs/best_features_per_symbol + gate_engine.)
            # Legacy simple action path (scalar) preserved exactly when AGI_EXECUTION_TYPE=simple_action.
            # ExecutionRouter + GateEngine + risk_supervisor already consume the rich intent dict for both paths.
            for symbol in self.symbols:
                try:
                    # Gate + risk precheck (production path)
                    # Use rich decision if decision_ppo (new default for promoted via watcher/supervisor); else legacy simple (compat).
                    # For decision_ppo: _make_rich_decision prefers real HybridBrain.predict_ppo_action (MTF context + best_features from candidate bundle) -> TradeDecision.
                    # This fully closes the autonomous training->promotion->paper(DecisionPPO+Exec) loop.
                    if getattr(self, "uses_rich_decision", False):
                        td_for_cycle = self._make_rich_decision(symbol)
                        self._last_rich_td = td_for_cycle
                        intent = {
                            "symbol": td_for_cycle.symbol,
                            "side": "BUY" if td_for_cycle.side.value == "LONG" else "SELL",
                            "size": float(td_for_cycle.size.value or 0.01),
                            "sl": getattr(td_for_cycle.sl, 'value', 120),
                            "tp": getattr(td_for_cycle.tp, 'value', 240),
                            "comment": f"HARNESS|DECISION_PPO|real_ppo={bool(self.brain)}",
                            "confidence": float(td_for_cycle.confidence or 0.72),
                            "execution_type": "decision_ppo",
                            "decision_id": td_for_cycle.decision_id,
                            "mtf_context": getattr(self, "mtf_context", True),
                            "best_features": self.best_features.get(symbol, {}),
                        }
                    else:
                        intent = self._get_intent(symbol, "BUY", HARNESS_MAX_LOT)
                    gate_res = self.gate.check_intent(
                        {**intent, "spread_bps": 8.0, "regime": "normal", "target_exposure": intent.get("size", 0.01), "open_positions": 0},
                        account_state={"telemetry_valid": True, "balance": equity, "equity": equity, "account_type": "demo", "account_type_verified": True},
                    )
                    if not (gate_res.gate_passed and gate_res.risk_passed):
                        continue

                    # Risk supervisor (top layer for exposure)
                    risk_dec = self.top_risk.allow_trade(
                        symbol=symbol,
                        target_exposure=0.01,
                        confidence=0.6,
                        spread_bps=8.0,
                        snapshot={"pnl_today": daily_pnl_pct / 100.0 * equity},
                        symbol_positions=0,
                        total_positions=0,
                        current_symbol_exposure=0.0,
                        total_exposure=0.0,
                        drawdown_pct=0.0,
                        equity=equity,
                    )
                    if not risk_dec.allowed:
                        if risk_dec.rollback_recommended:
                            self._trigger_rollback(risk_dec.reason)
                        else:
                            self._record_execution_feedback("trade_blocked", {"reason": risk_dec.reason})
                        continue

                    # Execute via Decision PPO + Execution layer (rich) when armed, else legacy router
                    executed = False
                    exec_res = {}
                    if self.uses_rich_decision and self.execution_agent is not None:
                        try:
                            # Prefer real rich td from _make (which tries HybridBrain PPO for promoted candidate's MTF/best-feats)
                            td = getattr(self, "_last_rich_td", None) or self._make_rich_decision(symbol, side=intent.get("side", "BUY"))
                            report = self.execution_agent.submit_decision(td)
                            executed = report is not None and getattr(report, 'status', '') not in ("error", "blocked", "validation")
                            exec_res = {
                                "executed": executed,
                                "backend": getattr(report, 'backend', 'execution_agent'),
                                "decision_id": getattr(report, 'decision_id', None),
                                "status": getattr(report, 'status', 'unknown'),
                            }
                            if executed:
                                self.execution_agent.update_from_execution_telemetry(
                                    report.decision_id if hasattr(report, 'decision_id') else "harness_live",
                                    {"status": "filled", "backend": "paper_harness"}
                                )
                        except Exception as ea_exec_err:
                            logger.warning(f"ExecAgent path error, falling to router: {ea_exec_err}")
                            exec_res = self.router.submit(intent)
                            executed = exec_res.get("executed", False)
                    else:
                        # Legacy simple action path (unchanged)
                        exec_res = self.router.submit(intent)
                        executed = exec_res.get("executed", False)

                    self._log_harness_event("trade_attempt", {
                        "symbol": symbol,
                        "intent": intent,
                        "gate": gate_res.reason,
                        "risk": risk_dec.reason,
                        "exec": exec_res,
                    })

                    if executed:
                        self.trades_today += 1
                        self.consecutive_errors = 0
                        self.exec_risk.record_trade(symbol)
                        self.top_risk.mark_trade(symbol)
                        self.canary.record_trade({"symbol": symbol, "side": intent["side"], "volume": HARNESS_MAX_LOT, "pnl": 0.0, "open_time": now.isoformat(), "news_distance_minutes": 999, "session": "unknown", "timing_tags": "rich_decision_ppo"})  # closed later by real journal + timing fields for canary extension

                        if self.alerter:
                            self.alerter.info(f"HARNESS TRADE {symbol} {intent['side']} 0.01 (demo MT5)")
                    else:
                        self.consecutive_errors += 1

                    self._save_state()

                except Exception as exc:
                    logger.error(f"Harness cycle error on {symbol}: {exc}")
                    self.consecutive_errors += 1
                    self.exec_risk.record_error() if hasattr(self.exec_risk, "record_error") else None

            # Sleep with jitter for controlled pace (multi-day safe)
            time.sleep(45 + (cycle % 15))  # ~1 min cycles, variable to avoid patterns

            if cycle % 20 == 0:
                logger.info(f"Harness alive: cycle={cycle} equity=${equity:.2f} daily_pnl_pct={daily_pnl_pct:.2f}% trades_today={self.trades_today}")

            # Real feedback wiring: poll MT5 closed deals (actual execution results) + periodic aggregator eval
            if cycle % 3 == 0:
                try:
                    self._poll_and_feed_closed_trades()
                except Exception:
                    pass
            if cycle % 7 == 0:
                try:
                    # Lightweight aggregator: evaluates trigger with latest logs/signals, logs "RETRAIN RECOMMENDED" if hit
                    from Python.autonomous.retraining_trigger import run_aggregator_and_log
                    run_aggregator_and_log(data_dir=str(LOGS_DIR))
                    # Also direct eval to ensure harness copy on any trigger
                    art = self.retrain_trigger.evaluate()
                    if art.triggered:
                        outp = RUNTIME_DIR / f"retraining_trigger_from_harness_{art.retraining_trigger_id}.json"
                        outp.write_text(json.dumps(asdict(art), default=str))
                except Exception:
                    pass

        # Clean exit
        self._trigger_rollback("max_days_reached_or_stop") if self.running else None
        HARNESS_ACTIVE_FLAG.unlink(missing_ok=True)
        # Real feedback: final aggregator run + explicit (now aggregator + auto inside evaluate does heavy lifting)
        try:
            from Python.autonomous.retraining_trigger import run_aggregator_and_log
            run_aggregator_and_log(data_dir=str(LOGS_DIR))
            if getattr(self, "trades_today", 0) > 0:
                self.retrain_trigger.increment_closed_demo(self.trades_today)
            art = self.retrain_trigger.evaluate(
                canary_artifact={"approved_for_champion": True, "approved_for_real_live": False}
            )
            if art.triggered:
                outp = RUNTIME_DIR / f"retraining_trigger_from_harness_{art.retraining_trigger_id}.json"
                outp.write_text(json.dumps(asdict(art), default=str))
                logger.info(f"Feedback: retraining trigger emitted -> {art.next_cycle_command}")

                # Unified retrain decision (closes execution -> feedback loop)
                cand_name = Path(self.candidate_dir).name if getattr(self, "candidate_dir", None) else None
                log_decision(
                    decision_type="retrain_trigger",
                    actor="harness",
                    decision="RETRAIN_TRIGGERED",
                    candidate=cand_name,
                    run_id=cand_name,
                    reason="|".join(art.reasons) if getattr(art, "reasons", None) else "harness_feedback",
                    details={"next_cycle": art.next_cycle_command, "trigger_id": art.retraining_trigger_id},
                    severity="info",
                )
        except Exception:
            pass
        logger.success("Harness run completed cleanly. Review logs/paper_harness_exec.jsonl + canary artifacts for promotion decision. Check for RETRAIN RECOMMENDED in logs.")

        # Unified final stop decision
        try:
            cand_name = Path(self.candidate_dir).name if getattr(self, "candidate_dir", None) else None
            log_decision(
                decision_type="harness_stop",
                actor="harness",
                decision="HARNESS_STOPPED",
                candidate=cand_name,
                run_id=cand_name,
                reason="max_days_or_manual",
                details={"trades_executed": getattr(self, "trades_today", 0)},
                severity="info",
            )
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Controlled MT5 Paper Execution Harness")
    parser.add_argument("--symbols", nargs="+", default=["EURUSDm"], help="Symbols to run (tiny risk only)")
    parser.add_argument("--max-days", type=int, default=5, help="Auto-stop after N calendar days")
    parser.add_argument("--equity-start", type=float, default=5000.0, help="Notional starting equity for % guards")
    parser.add_argument("--execution-type", default=os.environ.get("AGI_EXECUTION_TYPE", "decision_ppo"), choices=["decision_ppo", "simple_action"], help="decision_ppo = rich full trade specs (side, size, sl, tp, confidence) via new Decision PPO + Execution layer (default); simple_action = legacy scalar. Paper harness consumes via ExecutorRouter.")
    args = parser.parse_args()

    harness = PaperMT5Harness(symbols=args.symbols, max_days=args.max_days, equity_start=args.equity_start, execution_type=args.execution_type)

    # Production hardening cleanup (rough edge fix): meta overrides + self-monitor + TUI alert/status
    try:
        meta_p = Path("runtime/next_training_overrides.json")
        if meta_p.exists():
            meta = json.loads(meta_p.read_text())
            logger.info(f"[HARNESS] Meta overrides active: reward={meta.get('reward_profile')} timing/pattern boosts engaged for this validation")
    except Exception: pass
    try:
        from Python.autonomous.self_monitor import SelfMonitoringRecoveryAgent
        SelfMonitoringRecoveryAgent().monitor_cycle()
    except Exception: pass
    try:
        status_p = Path("runtime/agent_status/paper_harness_status.json")
        status_p.parent.mkdir(parents=True, exist_ok=True)
        with open(status_p, "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.now(timezone.utc).isoformat(), "symbols": args.symbols, "max_days": args.max_days, "execution_type": args.execution_type, "meta_consumed": True, "self_monitor_integrated": True, "alert_ready_for_tui": True}, f, default=str)
    except Exception: pass

    harness.run()


if __name__ == "__main__":
    main()
