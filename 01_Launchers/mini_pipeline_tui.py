#!/usr/bin/env python3
"""
Mini Pipeline TUI (standalone light version) - Compact watcher for the FULL ingestion-to-champion-execution pipeline.

PREFERRED (integrated "improved TUI" from swarm): 
  python scripts/monitor_tui.py --mini --once     (or -m; 'p' toggles live)
  This is the canonical dense mini full-pipeline watcher (data ingest → rich Decision PPO + TimeExitSpec → ExecutionAgent → loop).

This standalone is a zero-dep ultra-light alternative for tiny terminals.
Covers: ingestion/MTF/timing/patterns, Decision PPO 18-dim rich (TimeExitSpec), ExecutionAgent pure-py telemetry, PIPELINE_DECISIONS, swarm agents, etc.

Focus: Zero-touch autonomous flow with Decision PPO (rich 18-dim TradeDecision),
classical patterns (doji/hammer/engulfing/flags/breakouts), timing (news/opens),
Rainforest + Dreamer conditioning, gates, promotion, pure-Python ExecutionAgent rich execution,
and telemetry back to journal/PIPELINE/retrain.

Single dense screen. Fast refresh. --once for CI/one-shot. Works in small terminals.

Run (standalone):
  .\\.venv312\\Scripts\\python.exe scripts/mini_pipeline_tui.py
  .\\.venv312\\Scripts\\python.exe scripts/mini_pipeline_tui.py --once

Key watched artifacts (all written by autonomous agents/launcher/harness/ExecutionAgent):
- logs/PIPELINE_DECISIONS.jsonl
- runtime/agent_status/*.json (esp. decision_ppo_*, e2e_*, handoff_*, master_self_evolution_*, experience_memory_*, meta_optimizer_*)
- runtime/execution_reports/*.json (rich TradeDecision + TimeExitSpec + pattern tags)
- runtime/retraining_jobs/meta_suggested_training_overrides_*.json (exact hardened reward/FI/top patterns from real XAU overnight)
- runtime/self_evolution/supervisor_state.json + performance_history.json
- runtime/validation_results/standardized_validation_*.json (pattern_profitability + time_exit_effectiveness)
- runtime/experience_memory.jsonl (high-value experiences for replay)
- logs/decision_ppo_*.log + logs/drl_joint/PPO_*
- logs/trade_journal.jsonl + logs/execution_feedback.jsonl
- models/registry/candidates/*
- runtime/last_handoff.json + runtime/paper_harness_start.json
- (future) *_timing_insights.json from trade_timing_analyzer
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("rich not installed. pip install rich")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)

console = Console()

# Watched paths
PIPELINE_DECISIONS = PROJECT_ROOT / "logs" / "PIPELINE_DECISIONS.jsonl"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
AGENT_STATUS_DIR = RUNTIME_DIR / "agent_status"
EXEC_REPORTS_DIR = RUNTIME_DIR / "execution_reports"
CANDIDATES_DIR = PROJECT_ROOT / "models" / "registry" / "candidates"
LAST_HANDOFF = PROJECT_ROOT / "last_handoff.json"
PAPER_HARNESS_START = RUNTIME_DIR / "paper_harness_start.json"
TRAINING_HEALTH = RUNTIME_DIR / "training_health.json"
TRADE_JOURNAL = PROJECT_ROOT / "logs" / "trade_journal.jsonl"
EXEC_FEEDBACK = PROJECT_ROOT / "logs" / "execution_feedback.jsonl"

# Validation Harness integration (new fast engine long backtests + A/B)
VALIDATION_RESULTS_DIR = RUNTIME_DIR / "validation_results"
VALIDATION_REPORTS_DIR = PROJECT_ROOT / "reports" / "validation"
VALIDATION_STATUS = RUNTIME_DIR / "agent_status" / "validation_harness_agent.json"

# Self-evolution observability paths (new rich panels for autonomous brain)
SELF_EVOL_DIR = RUNTIME_DIR / "self_evolution"
EXPERIENCE_MEM_PATH = RUNTIME_DIR / "experience_memory.jsonl"
EXPERIENCE_AGENT_STATUS = AGENT_STATUS_DIR / "experience_memory_agent.json"
SUPERVISOR_AGENT = AGENT_STATUS_DIR / "master_self_evolution_supervisor_agent.json"
CONTINUAL_COMPLETE = AGENT_STATUS_DIR / "continual_learner_complete.json"  # online adaptation + drift for TUI display
SUPERVISOR_STATE = SELF_EVOL_DIR / "supervisor_state.json"
META_OPTIMIZER_DIR = RUNTIME_DIR / "meta_optimizer"
RETRAIN_JOBS_DIR = RUNTIME_DIR / "retraining_jobs"

# Recent decision_ppo training logs (any)
DECISION_PPO_LOGS = list((PROJECT_ROOT / "logs").glob("decision_ppo_*.log")) + \
                    list((PROJECT_ROOT / "logs").glob("decision_ppo_XAU*.log"))

REFRESH_SEC = 2.0
MAX_PIPELINE_EVENTS = 12
MAX_EXEC_REPORTS = 6
MAX_AGENT_STATUSES = 8


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _tail_jsonl(path: Path, n: int = 50) -> List[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        out = []
        for line in lines[-n:]:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
    except Exception:
        return []


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _load_latest_agent_statuses() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not AGENT_STATUS_DIR.exists():
        return items
    for p in sorted(AGENT_STATUS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:MAX_AGENT_STATUSES]:
        data = _load_json(p)
        if data:
            data["_file"] = p.name
            data["_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S")
            items.append(data)
    return items


def _load_recent_exec_reports() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not EXEC_REPORTS_DIR.exists():
        return items
    for p in sorted(EXEC_REPORTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:MAX_EXEC_REPORTS]:
        data = _load_json(p)
        if data:
            data["_file"] = p.name
            data["_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S")
            items.append(data)
    return items


def _load_validation_harness_status() -> Optional[Dict[str, Any]]:
    """Load the new Validation Harness agent status + latest standardized result (for A/B + TimeExitSpec reports)."""
    try:
        data = _load_json(VALIDATION_STATUS)
        if data:
            data["_file"] = "validation_harness_agent.json"
        # Also attach latest standardized result if present
        latest_ab = None
        if VALIDATION_RESULTS_DIR.exists():
            ab_files = sorted(VALIDATION_RESULTS_DIR.glob("standardized_validation_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if ab_files:
                latest_ab = _load_json(ab_files[0])
                if latest_ab:
                    latest_ab["_file"] = ab_files[0].name
        if data:
            data["latest_ab_result"] = latest_ab
        return data
    except Exception:
        return None


def _load_latest_meta_overrides() -> Optional[Dict[str, Any]]:
    """Load the most recent artifact-driven training overrides produced by MetaOptimizer / full cycle agents."""
    try:
        jobs_dir = RUNTIME_DIR / "retraining_jobs"
        if not jobs_dir.exists():
            return None
        cands = sorted(jobs_dir.glob("meta_suggested_training_overrides_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not cands:
            return None
        data = _load_json(cands[0])
        if data:
            data["_file"] = cands[0].name
            data["_mtime"] = datetime.fromtimestamp(cands[0].stat().st_mtime).strftime("%H:%M")
        return data
    except Exception:
        return None


def _load_latest_full_cycle_report() -> Optional[Dict[str, Any]]:
    """Load the latest 'full cycle with this artifact' or self-evolution supervisor decision report."""
    try:
        for p in sorted(AGENT_STATUS_DIR.glob("full_cycle_with_real_overnight_artifact*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
            data = _load_json(p)
            if data:
                data["_file"] = p.name
                data["_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M")
                return data
        # Fallback: any recent self-evolution / meta_optimizer agent status
        for p in sorted(AGENT_STATUS_DIR.glob("*self_evolution*.json") + AGENT_STATUS_DIR.glob("*meta_optimizer*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
            data = _load_json(p)
            if data:
                data["_file"] = p.name
                data["_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M")
                return data
        return None
    except Exception:
        return None


def _load_latest_meta_overrides_detailed() -> Optional[Dict[str, Any]]:
    """Load richest meta_suggested_training_overrides (exact hardened reward, FI boosts, top patterns from real XAU overnight)."""
    try:
        if not RETRAIN_JOBS_DIR.exists():
            return None
        cands = sorted(RETRAIN_JOBS_DIR.glob("meta_suggested_training_overrides_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not cands:
            # fallback to meta_optimizer current/ applied
            for cand in sorted(META_OPTIMIZER_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                d = _load_json(cand)
                if d and ("reward" in str(d).lower() or "hardened" in str(d).lower()):
                    d["_file"] = cand.name
                    return d
            return None
        data = _load_json(cands[0])
        if data:
            data["_file"] = cands[0].name
            data["_mtime"] = datetime.fromtimestamp(cands[0].stat().st_mtime).strftime("%H:%M")
        return data
    except Exception:
        return None


def _load_experience_memory_stats() -> Dict[str, Any]:
    """ExperienceMemory stats + top high-value experiences (pattern + timing + regime + edge_score). Safe parse of jsonl or agent status."""
    stats: Dict[str, Any] = {
        "size": 0, "high_value_count": 0, "avg_edge": 0.0, "top_patterns": [],
        "top_experiences": [], "source": "none", "note": "No experiences yet — seed from validation pattern_profitability"
    }
    try:
        # Prefer direct jsonl parse (lightweight, no import)
        if EXPERIENCE_MEM_PATH.exists():
            lines = EXPERIENCE_MEM_PATH.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[-500:]
            exps = []
            for ln in lines:
                if not ln.strip(): continue
                try:
                    e = json.loads(ln)
                    exps.append(e)
                except Exception:
                    continue
            stats["size"] = len(exps)
            if exps:
                # top by edge_score
                sorted_exps = sorted(exps, key=lambda x: float(x.get("edge_score", x.get("learning_priority", 0)) or 0), reverse=True)[:5]
                stats["high_value_count"] = sum(1 for e in exps if float(e.get("edge_score", 0) or 0) >= 0.55)
                edges = [float(e.get("edge_score", 0) or 0) for e in exps]
                stats["avg_edge"] = round(sum(edges)/max(1,len(edges)), 3)
                stats["top_experiences"] = []
                for e in sorted_exps:
                    pat = _safe_list(e.get("classical_patterns") or (e.get("pattern_context") or {}).get("patterns", []), 2)
                    tim = _safe_text((e.get("timing_context") or {}).get("regime") or e.get("timing_tags", ""), 18)
                    reg = _safe_text(e.get("regime") or (e.get("rainforest_regime") or "unknown"), 12)
                    edge = _safe_float(e.get("edge_score") or e.get("learning_priority", 0), 0.0, 2)
                    stats["top_experiences"].append(f"pat={pat} tim={tim} reg={reg} edge={edge}")
                stats["source"] = "runtime/experience_memory.jsonl"
                stats["note"] = ""
        # Enrich / fallback from agent status summary (always present)
        agent = _load_json(EXPERIENCE_AGENT_STATUS)
        if agent:
            rs = agent.get("runtime_state", {}) or {}
            if rs.get("ingest_results_from_live_logs"):
                stats["note"] = f"ingested: {rs['ingest_results_from_live_logs']}"
            if not stats["size"]:
                stats["source"] = "experience_memory_agent.json (module ready)"
    except Exception:
        pass
    # Always pull high-value hints from full_cycle if present (real XAU artifact)
    try:
        fc = _load_latest_full_cycle_report()
        if fc:
            emi = fc.get("experience_memory_insights", {})
            if emi.get("usage"):
                stats["note"] = _safe_text(emi.get("usage"), 90)
    except Exception:
        pass
    return stats


def _load_supervisor_status() -> Dict[str, Any]:
    """Master Self-Evolution Supervisor current strategy + recent decisions (from agent status + state)."""
    sup: Dict[str, Any] = {
        "current_strategy": "unknown", "status": "—", "last_cycle": "—",
        "recent_decisions": [], "goals_achieved": [], "next_behaviors": [], "source": "none"
    }
    try:
        data = _load_json(SUPERVISOR_AGENT)
        if data:
            sup["current_strategy"] = data.get("current_strategy", data.get("last_cycle_result", {}).get("strategy", "regime_adaptation_boost"))
            sup["status"] = data.get("status", "ACTIVE")
            sup["last_cycle"] = data.get("last_cycle", "")
            actions = (data.get("last_cycle_result", {}) or {}).get("actions_taken", []) or []
            for a in actions[-4:]:
                typ = a.get("type") or a.get("action", "decision")
                det = str(a.get("details", a.get("summary", "")))[:55]
                sup["recent_decisions"].append(f"{typ}: {det}")
            sup["goals_achieved"] = [g["name"] for g in (data.get("goals", []) or []) if g.get("achieved")]
            sup["next_behaviors"] = data.get("next_autonomous_behaviors", [])[:3]
            sup["source"] = "master_self_evolution_supervisor_agent.json"
        # overlay state
        st = _load_json(SUPERVISOR_STATE)
        if st:
            if st.get("current_strategy"):
                sup["current_strategy"] = st["current_strategy"]
            if not sup["recent_decisions"]:
                sup["recent_decisions"] = ["state persisted @ " + _safe_text(st.get("last_persist"), 16)]
    except Exception:
        pass
    return sup


def _load_validation_key_findings() -> Dict[str, Any]:
    """Recent StandardizedValidationResult key findings (pattern profitability, time_exit_effectiveness) from real XAU artifact."""
    findings: Dict[str, Any] = {
        "symbol": "XAUUSDm", "campaign": "—", "top_patterns": [], "time_exit": {},
        "pattern_profitability": {}, "recommendation": "—", "source": "none"
    }
    try:
        # Prefer direct from validation_results standardized
        if VALIDATION_RESULTS_DIR.exists():
            cands = sorted(VALIDATION_RESULTS_DIR.glob("standardized_validation_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            if cands:
                val = _load_json(cands[0])
                if val:
                    findings["campaign"] = val.get("campaign_id", cands[0].name)
                    findings["symbol"] = (val.get("symbols") or ["XAUUSDm"])[0]
                    findings["recommendation"] = val.get("overall_recommendation", "ITERATE")
                    # pattern_profitability top (use candidate or champ deltas)
                    pp = val.get("pattern_profitability", {}) or {}
                    cand_pp = pp.get("candidate", {}) or pp.get("champion", {})
                    top = sorted([(k, v.get("pnl",0)) for k,v in cand_pp.items() if isinstance(v,dict)], key=lambda x: -x[1])[:4]
                    findings["top_patterns"] = [f"{p}({round(pnl)})" for p,pnl in top]
                    findings["pattern_profitability"] = {k: {"pnl": v.get("pnl"), "winrate": v.get("winrate")} for k,v in list(cand_pp.items())[:6] if isinstance(v,dict)}
                    # time_exit_effectiveness
                    findings["time_exit"] = val.get("time_exit_effectiveness", {}) or {}
                    findings["source"] = cands[0].name
        # Enrich from full_cycle (has exact deltas from overnight)
        fc = _load_latest_full_cycle_report()
        if fc:
            art = fc.get("artifact_summary", {})
            if art.get("key_deltas"):
                findings["key_deltas"] = art["key_deltas"]
            if fc.get("clear_next_action_recommendation"):
                findings["next_action_hint"] = _safe_text(fc.get("clear_next_action_recommendation"), 80)
            if "key_findings" in fc:
                findings["key_findings"] = fc["key_findings"][:3]
    except Exception:
        pass
    return findings


def _safe_text(val: Any, max_len: int = 58, default: str = "—") -> str:
    """Safely convert value to string and truncate. Handles None and missing data from JSON artifacts."""
    if val is None:
        return default
    try:
        s = str(val)
        return s[:max_len] if len(s) > max_len else s
    except Exception:
        return default


def _safe_float(val: Any, default: float = 0.0, ndigits: int = 2) -> str:
    """Safe numeric render for edge_score / pnl / boosts etc."""
    try:
        if val is None:
            return f"{default:.{ndigits}f}"
        f = float(val)
        return f"{f:.{ndigits}f}"
    except Exception:
        return f"{default:.{ndigits}f}"


def _safe_list(val: Any, max_items: int = 4, default: str = "—") -> str:
    """Render top-N list items safely."""
    if not val:
        return default
    try:
        items = [str(x) for x in (val if isinstance(val, (list, tuple)) else [val])][:max_items]
        return ", ".join(items)
    except Exception:
        return default


def _get_training_progress() -> Dict[str, Any]:
    """Extract live decision_ppo progress from health + recent log tails."""
    prog: Dict[str, Any] = {"status": "NO ACTIVE RUN", "step": 0, "pct": 0, "symbol": "XAUUSDm", "timesteps": 50000}
    h = _load_json(TRAINING_HEALTH)
    if h:
        prog["status"] = h.get("status", "RUNNING")
        prog["step"] = h.get("current_step", 0)
        prog["pct"] = h.get("progress_pct", 0)
        prog["symbol"] = h.get("symbol", prog["symbol"])
        if "timesteps" in h:
            prog["timesteps"] = h["timesteps"]

    # Fallback: scan latest decision_ppo log for "step=XXXX/50000"
    for logp in sorted(DECISION_PPO_LOGS, key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
        try:
            tail = logp.read_text(errors="ignore").splitlines()[-30:]
            for line in reversed(tail):
                if "step=" in line and "/50,000" in line:
                    # Parse "step=10,000/50,000 | pct=20.00"
                    try:
                        parts = line.split("|")
                        for p in parts:
                            if "step=" in p:
                                s = p.split("step=")[1].split("/")[0].replace(",", "").strip()
                                prog["step"] = int(s)
                            if "pct=" in p:
                                prog["pct"] = float(p.split("pct=")[1].split()[0])
                        prog["status"] = "TRAINING (decision_ppo 18-dim + patterns + timing)"
                        break
                    except Exception:
                        pass
        except Exception:
            pass
        if prog["step"] > 0:
            break
    return prog


def _get_latest_candidate() -> Optional[Dict[str, Any]]:
    if not CANDIDATES_DIR.exists():
        return None
    cands = sorted(CANDIDATES_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not cands:
        return None
    latest = cands[0]
    meta = latest / "metrics.json" if (latest / "metrics.json").exists() else None
    info = {"name": latest.name, "path": str(latest), "mtime": datetime.fromtimestamp(latest.stat().st_mtime).strftime("%H:%M")}
    if meta:
        m = _load_json(meta)
        if m:
            info["sharpe"] = m.get("sharpe") or m.get("test_sharpe")
            info["pnl"] = m.get("total_pnl") or m.get("test_pnl")
    return info


def _get_last_handoff() -> Optional[Dict[str, Any]]:
    d = _load_json(LAST_HANDOFF)
    if d:
        d["_file"] = "last_handoff.json"
    return d


def _get_paper_harness_state() -> Optional[Dict[str, Any]]:
    d = _load_json(PAPER_HARNESS_START)
    if d:
        d["_file"] = "paper_harness_start.json"
    return d


def _recent_pipeline_events() -> List[Dict[str, Any]]:
    events = _tail_jsonl(PIPELINE_DECISIONS, 80)
    # Prefer decision_ppo / promotion / execution / handoff events
    prio = []
    for e in reversed(events):
        dt = e.get("decision_type") or e.get("event") or ""
        if any(k in str(dt).lower() for k in ["decision_ppo", "trade_decision", "promotion", "handoff", "execution_agent", "champion", "rich"]):
            prio.append(e)
        if len(prio) >= MAX_PIPELINE_EVENTS:
            break
    if not prio:
        prio = list(reversed(events[-MAX_PIPELINE_EVENTS:]))
    return prio


def _render_header() -> Panel:
    title = Text("SUPREME CHAINSAW - MINI FULL PIPELINE WATCHER + SELF-EVOLUTION BRAIN", style="bold cyan")
    sub = Text(f"Ingestion -> DecisionPPO (patterns+timing) -> Gates -> Champion Execution  |  🧠 MetaOverrides + EM + Supervisor + ValidationFindings live  |  {_now()}", style="dim")
    return Panel(Group(title, sub), box=box.ROUNDED, style="cyan", padding=(0,1))


def _render_training_panel(prog: Dict[str, Any], cand: Optional[Dict[str, Any]]) -> Panel:
    t = Table.grid(expand=True)
    t.add_column("k", style="bold yellow", width=18)
    t.add_column("v", style="white")

    t.add_row("Status", prog.get("status", "UNKNOWN"))
    t.add_row("Symbol / Action", f"{prog.get('symbol','?')} | decision_ppo 18-dim")
    step = prog.get("step", 0)
    tot = prog.get("timesteps", 50000)
    pct = prog.get("pct", 0)
    t.add_row("Progress", f"{step:,}/{tot:,}  ({pct:.1f}%)")
    if cand:
        t.add_row("Latest Candidate", f"{cand['name']} @ {cand.get('mtime','?')}  sharpe={cand.get('sharpe')}")
    else:
        t.add_row("Latest Candidate", "none newer than baseline (awaiting training finish + gates)")

    # Pattern / timing note
    t.add_row("Enriched Obs", "MTF(1m+5m+15m+1h) + timing(news/open) + 11 classical patterns (wired in feature_pipeline)")

    return Panel(t, title="TRAINING (Decision PPO + Rainforest/Dreamer + Patterns + Timing)", box=box.ROUNDED, style="green")


def _render_execution_panel(reports: List[Dict[str, Any]], harness: Optional[Dict[str, Any]]) -> Panel:
    t = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE, expand=True)
    t.add_column("Time", width=8)
    t.add_column("Decision", width=22)
    t.add_column("Rich Spec (Size/Exit/Trail/TimeExit)", width=55)
    t.add_column("Backend", width=12)

    if not reports:
        t.add_row("-", "NO RECENT RICH EXEC REPORTS", "Run harness or decision_ppo candidate for live paper trades", "-")
    else:
        for r in reports:
            ts = r.get("_mtime", "?")
            dec = r.get("decision") or r.get("trade_decision") or {}
            did = _safe_text(dec.get("decision_id") or r.get("_file",""), 12)
            side = dec.get("side", "?")
            size_spec = dec.get("size", {}) or {}
            size = size_spec.get("risk_pct_equity") or size_spec.get("fixed_lots") or dec.get("size", 0.01)
            exit_spec = dec.get("exit", {}) or {}
            tp = exit_spec.get("tp_type", exit_spec.get("tp", "?"))
            sl = exit_spec.get("sl_type", "?")
            trail = (dec.get("trailing") or {}).get("type", "NONE")
            time_exit = dec.get("time_exit") or dec.get("TimeExitSpec") or {}
            te_flags = []
            if time_exit.get("close_before_high_impact_news"): te_flags.append("news")
            if time_exit.get("close_at_session_end"): te_flags.append("session")
            if time_exit.get("max_hold_minutes"): te_flags.append(f"max{time_exit.get('max_hold_minutes')}m")
            te_str = "+".join(te_flags) if te_flags else "none"
            size_str = str(size)[:28] if isinstance(size, (int, float, dict)) else str(size)[:28]
            rich = f"{side} sz={size_str} trail={trail} te=[{te_str}]"
            backend = r.get("backend", r.get("executor", "python_order_manager"))
            t.add_row(ts, did, rich, str(backend)[:12])

    foot = ""
    if harness:
        foot = f"Harness armed: execution_type={harness.get('execution_type','decision_ppo')}  uses_rich={harness.get('uses_rich_decision',True)}"
    return Panel(Group(t, Text(foot, style="dim")), title="CHAMPION EXECUTION (ExecutionAgent pure-Python + rich TradeDecision + TimeExitSpec)", box=box.ROUNDED, style="magenta")


def _render_pipeline_events(events: List[Dict[str, Any]]) -> Panel:
    t = Table(show_header=True, header_style="bold blue", box=box.SIMPLE, expand=True)
    t.add_column("TS", width=16)
    t.add_column("Type", width=18)
    t.add_column("Actor / Decision", width=28)
    t.add_column("Details (timing/patterns/execution)", width=40)

    if not events:
        t.add_row("-", "NO PIPELINE DECISIONS YET", "Launch training or harness to populate", "")
    else:
        for e in events:
            ts = str(e.get("ts") or e.get("timestamp", ""))[:16]
            dt = str(e.get("decision_type") or e.get("event", ""))[:17]
            actor = str(e.get("actor", ""))[:26]
            det = e.get("details") or e.get("reason") or e.get("decision") or ""
            if isinstance(det, dict):
                # Extract rich bits
                sym = det.get("symbol", "")
                src = det.get("source", "")
                timing = det.get("timing_tags") or det.get("time_exit") or ""
                det = f"{sym} {src} {timing}" if sym or src else str(det)[:60]
            t.add_row(ts, dt, actor, str(det)[:55])
    return Panel(t, title="PIPELINE_DECISIONS.jsonl (full flow: ingestion->train->gates->champion exec)", box=box.ROUNDED, style="blue")


def _render_swarm_panel(statuses: List[Dict[str, Any]]) -> Panel:
    t = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE, expand=True)
    t.add_column("Agent File", width=28)
    t.add_column("Status", width=12)
    t.add_column("Updated", width=9)
    t.add_column("Key Note (patterns/timing/execution/loop)", width=45)

    if not statuses:
        t.add_row("-", "NO AGENTS", "-", "Spawn agents via swarm or they auto-write on task start")
    else:
        for s in statuses:
            raw_name = s.get("_file", "?")
            name = _safe_text(raw_name, 26)
            st = str(s.get("status", s.get("state", "-")))[:11]
            mt = s.get("_mtime", "?")
            note = ""
            # Prominently highlight recent self-evolution agents (Master Supervisor, Meta, ExperienceMemory, Validation, Retraining)
            is_evol = any(k in str(raw_name).lower() for k in [
                "self_evolution", "master_self", "meta_optimizer", "experience_memory",
                "validation_harness", "retraining_orchestrator", "supervisor"
            ])
            prefix = "🧠 EVOL: " if is_evol else ""
            if is_evol:
                name = prefix + name
            if "decision_ppo" in str(s).lower() or "execution" in str(s).lower():
                note = "decision_ppo + rich TradeDecision + pure py primary"
            elif "pattern" in str(s).lower() or "timing" in str(s).lower():
                note = "PatternDetector (12 patterns) + timing wired to Rainforest/Dreamer/PPO"
            elif "e2e" in name.lower() or "pipeline" in str(s).lower():
                note = "E2E loop armed: watcher->promoter->harness->ExecutionAgent"
            elif "handoff" in name.lower():
                note = "handoff_watcher detecting decision_ppo candidates"
            elif is_evol:
                note = "SELF-EVOLUTION layer: supervisor strategy / meta overrides / EM replay / harness findings"
            else:
                note = str(s.get("description", ""))[:44]
            t.add_row(name, st, mt, note[:44])
    return Panel(t, title="SWARM / AGENTS (full pipeline coverage)  —  🧠 EVOL agents highlighted for self-evolution observability", box=box.ROUNDED, style="cyan")


def _render_validation_panel(val: Optional[Dict[str, Any]]) -> Panel:
    """Render Validation Harness A/B results + TimeExitSpec / pattern analysis visibility."""
    if not val:
        return Panel(Text("Validation Harness: no recent run (run scripts/run_overnight_validation.py)", style="dim"), title="VALIDATION HARNESS (FastBacktester A/B)", box=box.ROUNDED, style="yellow")

    status = val.get("status", "UNKNOWN")
    tests = val.get("tests_run", 0)
    promoted = val.get("candidates_promoted", 0)
    latest = val.get("latest_ab_result") or {}
    beats = latest.get("ab_comparison", {}).get("candidate_beats_champion", "?")
    promote = latest.get("ab_comparison", {}).get("recommend_for_promotion", "?")
    sym = (latest.get("symbols") or ["?"])[0]
    delta = latest.get("ab_comparison", {}).get("delta", {}).get("return", 0.0)

    txt = Text()
    txt.append(f"Status: {status}  |  Tests: {tests}  Promoted: {promoted}\n", style="bold")
    txt.append(f"Latest: {sym} | Beats champion: {beats} | Promote: {promote} | Δret={delta:+.2%}\n", style="green" if beats else "red")
    if latest:
        txt.append(f"Report: {_safe_text(latest.get('rich_report_path'), 58)}\n", style="dim")
    txt.append("Rich outputs: pattern profitability • timing windows • TimeExitSpec effectiveness • standardized for retrainer", style="dim")
    return Panel(txt, title="VALIDATION HARNESS (FastBacktester A/B + Pattern+Timing)", box=box.ROUNDED, style="green")


def _render_self_evolution_panel(meta: Optional[Dict[str, Any]], cycle: Optional[Dict[str, Any]]) -> Panel:
    """Rich expanded panel for SELF-EVOLUTION / META OVERRIDES (hardened reward, FI, patterns from real XAU overnight artifact)."""
    t = Table.grid(expand=True)
    t.add_column("k", style="bold magenta", width=18)
    t.add_column("v", style="white")

    if not meta and not cycle:
        t.add_row("Status", "No meta overrides or full-cycle report yet (spawned agents write these)")
        t.add_row("Next", "Run overnight validation or full_cycle agent -> overrides appear here automatically")
        return Panel(t, title="SELF-EVOLUTION / META OVERRIDES (real XAU overnight artifact → hardened reward + FI boosts)", box=box.ROUNDED, style="magenta")

    # Meta overrides (exact from meta_suggested_training_overrides_*.json produced by full_cycle + orchestrator)
    if meta:
        rp = meta.get("reward_profile", meta.get("suggest_output_recommended_profile", "?"))
        ps = meta.get("penalty_scale", meta.get("exact_suggested_config_for_next_training", {}).get("penalty_scale", 1.0))
        t.add_row("Reward Profile", f"HARDENED: {rp}  penalty_scale={ps}")
        fi = meta.get("feature_importance_overrides") or meta.get("exact_suggested_config_for_next_training", {}).get("feature_importance_overrides", {})
        t.add_row("FI Boosts (XAU)", f"patterns={_safe_float(fi.get('patterns',1.0),1.0,2)}  timing={_safe_float(fi.get('timing',1.0),1.0,2)}  news={_safe_float(fi.get('news_proximity',1.0),1.0,2)}")
        ens = meta.get("ensemble_weight_deltas") or meta.get("exact_suggested_config_for_next_training", {}).get("ensemble_weight_deltas", {})
        if ens:
            t.add_row("Ensemble Δ", f"classical+{_safe_float(ens.get('classical',0))} rainforest+{_safe_float(ens.get('rainforest',0))} ppo{_safe_float(ens.get('ppo',0))}")
        pats = meta.get("top_boost_patterns") or meta.get("exact_suggested_config_for_next_training", {}).get("top_boost_patterns", [])
        if pats:
            t.add_row("Top Boost Patterns", _safe_list(pats, 4))
        src = meta.get("_file", "meta_suggested...") + f" @{meta.get('_mtime','?')}"
        t.add_row("Source Artifact", src)
        notes = meta.get("apply_notes") or meta.get("exact_suggested_config_for_next_training", {}).get("apply_notes", [])
        if notes:
            t.add_row("Why (real artifact)", _safe_text(notes[0] if isinstance(notes, list) else notes, 72))

    # Full cycle + next recommended action (orchestrator + agent)
    if cycle:
        ab = (cycle.get("artifact_summary", {}) or {}).get("ab", {})
        beats = ab.get("candidate_beats_champion", "?")
        prom = ab.get("recommend_for_promotion", "?")
        dpnl = (cycle.get("artifact_summary", {}) or {}).get("key_deltas", {}).get("pnl_delta", 0)
        t.add_row("Last Cycle (XAU)", f"Beats={beats} Promote={prom} Δpnl={dpnl:+.0f}")
        verdict = _safe_text((cycle.get("artifact_summary", {}) or {}).get("verdict"), 52)
        if verdict and verdict != "—":
            t.add_row("Verdict", verdict)
        next_act = _safe_text(cycle.get("clear_next_action_recommendation") or cycle.get("exact_suggested_config_for_next_training", {}).get("exact_training_command_example"), 78)
        if next_act and next_act != "—":
            t.add_row("NEXT RECOMMENDED", next_act[:85] + ("..." if len(next_act)>85 else ""))
        keyf = cycle.get("key_findings", [])
        if keyf:
            t.add_row("Key Finding", _safe_text(keyf[0], 70))

    # Supervisor quick peek
    try:
        sup = _load_supervisor_status()
        if sup.get("current_strategy") and sup["current_strategy"] != "unknown":
            t.add_row("Supervisor Strat", f"{sup['current_strategy']} | {sup.get('status','')}")
    except Exception:
        pass

    return Panel(t, title="SELF-EVOLUTION / META OVERRIDES (real XAU overnight → hardened reward + pattern/timing FI + next action)", box=box.ROUNDED, style="magenta")


def _render_experience_memory_panel(stats: Dict[str, Any]) -> Panel:
    """New dedicated panel: ExperienceMemory stats + top high-value experiences (pattern + timing + regime + edge_score)."""
    t = Table.grid(expand=True)
    t.add_column("k", style="bold cyan", width=18)
    t.add_column("v", style="white")

    t.add_row("Size / High-Val", f"{stats.get('size',0)} total | {stats.get('high_value_count',0)} high-edge (>=0.55)")
    t.add_row("Avg / Max Edge", f"avg={_safe_float(stats.get('avg_edge',0),0,3)}  source={stats.get('source','file')}")
    tops = stats.get("top_experiences", [])
    if tops:
        for i, ex in enumerate(tops[:3]):
            t.add_row(f"Top HV #{i+1}", ex[:68])
    else:
        t.add_row("Top Experiences", _safe_text(stats.get("note", "seed from validation pattern_profitability + timing"), 68))
    if stats.get("top_patterns"):
        t.add_row("Top Patterns", _safe_list(stats.get("top_patterns"), 5))
    return Panel(t, title="EXPERIENCEMEMORY (stats + high-value pattern+timing+regime+edge for replay/self-evol)", box=box.ROUNDED, style="cyan")


def _render_supervisor_panel(sup: Dict[str, Any]) -> Panel:
    """New dedicated panel: Master Self-Evolution Supervisor current strategy + recent decisions."""
    t = Table.grid(expand=True)
    t.add_column("k", style="bold yellow", width=18)
    t.add_column("v", style="white")

    t.add_row("Current Strategy", sup.get("current_strategy", "—"))
    t.add_row("Status / Last", f"{sup.get('status','—')}  cycle={_safe_text(sup.get('last_cycle'), 22)}")
    rec = sup.get("recent_decisions", [])
    if rec:
        t.add_row("Recent Decisions", _safe_text(rec[0], 68))
        if len(rec) > 1:
            t.add_row("", _safe_text(rec[1], 68))
    goals = sup.get("goals_achieved", [])
    if goals:
        t.add_row("Goals Achieved", _safe_list(goals, 4))
    nextb = sup.get("next_behaviors", [])
    if nextb:
        t.add_row("Next Behaviors", _safe_text(nextb[0] if isinstance(nextb, list) else nextb, 68))
    t.add_row("Source", sup.get("source", "agent_status"))
    return Panel(t, title="MASTER SELF-EVOLUTION SUPERVISOR (strategy + recent decisions/actions from central brain)", box=box.ROUNDED, style="yellow")


def _render_validation_findings_panel(findings: Dict[str, Any]) -> Panel:
    """New dedicated panel: Recent StandardizedValidationResult key findings (pattern profitability, time_exit_effectiveness)."""
    t = Table.grid(expand=True)
    t.add_column("k", style="bold green", width=18)
    t.add_column("v", style="white")

    t.add_row("Campaign", f"{findings.get('symbol','XAU')} {findings.get('campaign','—')}")
    t.add_row("Recommendation", findings.get("recommendation", "—"))
    tops = findings.get("top_patterns", [])
    if tops:
        t.add_row("Top Patterns (PnL)", _safe_list(tops, 4))
    te = findings.get("time_exit", {})
    if te:
        # Show candidate time_exit_effectiveness highlights
        cand_te = te.get("candidate", {}) or {}
        if cand_te:
            mh = cand_te.get("max_hold", {})
            news = cand_te.get("news_forced", {})
            t.add_row("TimeExit Cand", f"max_hold_pnl={_safe_float(mh.get('pnl',0))}  news_pnl={_safe_float(news.get('pnl',0))}")
    kd = findings.get("key_deltas", {})
    if kd:
        t.add_row("Key Deltas", f"double_bottom+{kd.get('double_bottom_cand_better_pnl',0)}  low_news+{kd.get('low_news_prox_cand_better_pnl',0)}")
    if findings.get("key_findings"):
        t.add_row("Artifact Finding", _safe_text(findings.get("key_findings", [""])[0], 65))
    next_h = findings.get("next_action_hint")
    if next_h:
        t.add_row("From Validation", next_h[:72])
    t.add_row("Source", findings.get("source", "standardized_validation_*.json"))
    return Panel(t, title="STANDARDIZED VALIDATION RESULT (pattern profitability + time_exit_effectiveness from real XAU overnight)", box=box.ROUNDED, style="green")


def _render_footer() -> Text:
    return Text(
        "Pure-Python primary.  🧠 SELF-EVOLUTION LAYER visible: meta_overrides (hardened+FI+patterns from real XAU overnight), ExperienceMemory, Master Supervisor strategy/decisions, StandardizedValidation key findings (profit+time_exit).  Next action from full_cycle orchestrator.  Ctrl+C to exit.  --once for snapshot.",
        style="dim"
    )


def build_layout() -> Group:
    prog = _get_training_progress()
    cand = _get_latest_candidate()
    reports = _load_recent_exec_reports()
    harness = _get_paper_harness_state()
    events = _recent_pipeline_events()
    swarm = _load_latest_agent_statuses()
    val_status = _load_validation_harness_status()
    meta_over = _load_latest_meta_overrides()
    full_cycle = _load_latest_full_cycle_report()

    # New self-evolution deep observability loads (safe, never crash)
    meta_detailed = _load_latest_meta_overrides_detailed()
    em_stats = _load_experience_memory_stats()
    sup_status = _load_supervisor_status()
    val_findings = _load_validation_key_findings()

    header = _render_header()
    train = _render_training_panel(prog, cand)
    execp = _render_execution_panel(reports, harness)
    pipe = _render_pipeline_events(events)
    swarm_p = _render_swarm_panel(swarm)
    val_p = _render_validation_panel(val_status)
    evol_p = _render_self_evolution_panel(meta_over or meta_detailed, full_cycle)
    foot = _render_footer()

    # Reduced panel count for less visual jumping.
    # Keep the most important self-evolution summary in evol_p only for the dense mini view.
    # (Detailed EM / Supervisor / Validation panels are still available in the richer monitor_tui.py --mini)
    return Group(header, train, execp, pipe, swarm_p, val_p, evol_p, foot)


def main(once: bool = False):
    if once:
        console.print(build_layout())
        return

    # screen=True can produce blank screen on stock Windows cmd.exe.
    # We default to screen=False for maximum compatibility. User can force with env var.
    use_screen = os.environ.get("MINI_TUI_SCREEN", "0") == "1"
    # Lower refresh rate significantly to reduce jumping/flickering.
    # User can control with env var: $env:MINI_TUI_FPS=2  (or 1 for very calm)
    fps = float(os.environ.get("MINI_TUI_FPS", "0.5"))
    live = Live(build_layout(), console=console, refresh_per_second=fps, screen=use_screen, vertical_overflow="crop")
    live.start()
    try:
        while True:
            time.sleep(REFRESH_SEC)
            live.update(build_layout())
    except KeyboardInterrupt:
        live.stop()
        console.print("\n[cyan]Mini pipeline watcher stopped.[/cyan]")


if __name__ == "__main__":
    once = "--once" in sys.argv or "-1" in sys.argv
    main(once=once)
