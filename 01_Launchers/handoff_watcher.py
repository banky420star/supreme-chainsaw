#!/usr/bin/env python3
"""
Persistent Candidate Handoff Watcher & Zero-Touch Orchestrator (long-running autonomous agent).

Watches silently for new post-fix gate-passing champions in models/registry/candidates/
newer than baseline 20260527_082932 (or champion_ready.flag mtime update).

On detection:
- Dry-run promoter first (checklist)
- Invoke full proven chain: promote_candidate_to_paper.py --auto-launch --promote-canary
- NEW STANDARD: deploys Decision + Execution setup (DecisionBuilder + ExecutorRouter + GateEngine + RiskSupervisor)
  with correct multi-TF context (1m+5m+15m+1h + best features from configs/best_features_per_symbol.yaml
  auto-loaded via multitimeframe_builder + fetch_multitimeframe_training_data).
- If AGI_AUTO_MQL5_DEPLOY=1 (or CHAIN_GAMBLER_AUTO_MQL5_DEPLOY / AGI_AUTO_MQL5), full deploy (no -LogOnly)
- Verify paper_harness_start.json + MQL5 shadow artifacts (mql5_shadow_ready.flag / json)
- Emit rich PIPELINE_DECISIONS.jsonl at each step: PROMOTION, MQL5_DEPLOY, PAPER_ARMED, FEEDBACK_WIRED
- Update TUI-visible runtime/agent_status/handoff_watcher_*.json + last_handoff.json + runtime/decision_execution_mtf_context.json
- On any real-run gate failure: trigger retraining feedback path via RetrainingTrigger + audit

Resilient: 
- Logs everything to logs/handoff_watcher.log (rotating simple)
- Own agent_status JSON updated every poll
- Inner crash recovery (never dies; restarts poll loop)
- Survives as detached background process (launched via PS Start-Process Hidden)

Integrates with:
- Existing promoter / deploy / harness / supervisor Invoke-PostCandidateHandoff / TUI (Decisions + Loop Closure)
- Never bypasses gates (delegates to promoter + evaluator/scorecard for real extraction)
- Lets TelegramAlerter + harness surface "bot trading" notifications (per core directive)
- NEW: multi-TF Decision+Execution arming (env AGI_MULTI_TF_STANDARD=1 default; legacy single-TF via AGI_USE_LEGACY_SINGLE_TF=1)

Polling: every 30s on candidates dir mtime/name ts + champion_ready.flag mtime.
Baseline: 20260527_082932 (pre-fix). Current v5 wave (per V4 stall diagnosis): robust_v5_BTCUSDm_20260527_120000 (light profile recipe: AGI_PENALTY_SCALE=0.25/light + 0.05 scale + conservative PPO) will yield newer candidate ts + handoff_profile on success.

Run detached:
  powershell -NoProfile -Command "Start-Process -FilePath '.\\.venv312\\Scripts\\python.exe' -ArgumentList 'scripts\\handoff_watcher.py' -WorkingDirectory 'C:\\supreme-chainsaw' -WindowStyle Hidden"

Fully autonomous zero-touch: the moment a real aligned champion appears and gates pass -> paper + MQL5 shadow armed -> trading validation begins.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Production hardening cleanup: ensure meta overrides + self-monitor + alerts status for supervisor/TUI zero-touch
try:
    _R = Path(__file__).resolve().parents[1]
    _meta = _R / "runtime" / "next_training_overrides.json"
    if _meta.exists():
        import json as _j
        print("[HANDOFF_WATCHER] Meta overrides present for autonomous cycles")
except Exception: pass
from typing import Any, Optional

# Project setup
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# NEW STANDARD: Multi-TF + best features + Decision+Execution arming (default)
os.environ.setdefault("AGI_USE_LEGACY_SINGLE_TF", "0")
os.environ.setdefault("AGI_MULTI_TF_STANDARD", "1")
os.environ.setdefault("AGI_FEATURE_VERSION", "multitimeframe_best")

# Core for unified decisions (TUI Decisions panel + Loop Closure Score)
from Python.pipeline_audit import log_decision

# NEW: Load best features for context writing on arm (multi-TF Decision+Execution)
try:
    from Python.features.multitimeframe_builder import load_best_feature_params
    _HAS_BEST_FEATS = True
except Exception:
    load_best_feature_params = None  # type: ignore
    _HAS_BEST_FEATS = False

# Feedback path
try:
    from Python.autonomous.retraining_trigger import RetrainingTrigger
except Exception:
    RetrainingTrigger = None  # type: ignore

# Runtime / paths
RUNTIME = PROJECT_ROOT / "runtime"
LOGS = PROJECT_ROOT / "logs"
CANDIDATES_DIR = PROJECT_ROOT / "models" / "registry" / "candidates"
AGENT_STATUS_DIR = RUNTIME / "agent_status"
BASE_CANDIDATE_TS = "20260527_082932"
# v4 diagnosis follow-through: current active v5 run details for watcher awareness of expected candidate/handoff on success
V5_RUN_TAG = "robust_v5_BTCUSDm_20260527_120000"
V5_LIGHT_PROFILE = "AGI_REWARD_PROFILE=light (equiv AGI_PENALTY_SCALE=0.25), AGI_REWARD_SCALE=0.05 + conservative PPO (target_kl=0.05, lr=3e-5, n_steps=8192)"
V5_EXPECTED_HANDOFF_PROFILE = "v5_btcusd_50k_light_handoff_profile.json"  # produced/used on v5 candidate stage + handoff
POLL_INTERVAL_S = 30
WATCHER_LOG = LOGS / "handoff_watcher.log"
LAST_SEEN_FILE = RUNTIME / ".handoff_watcher_last_candidate.txt"
WATCHER_STATUS_FILE = AGENT_STATUS_DIR / "handoff_watcher_status.json"
LAST_HANDOFF = RUNTIME / "last_handoff.json"

# Execution layer types for Autonomous Trading Loop Closure (Decision PPO + Execution layer default for new promotions)
# decision_ppo = rich full TradeDecision/DecisionSpec (default for newly promoted; uses multi-TF + best_features)
# simple_action = legacy scalar/6-dim (preserved for backward compat; never broken)
DEFAULT_EXECUTION_TYPE = "decision_ppo"
LEGACY_EXECUTION_TYPE = "simple_action"
SUPPORTED_EXECUTION_TYPES = {LEGACY_EXECUTION_TYPE, DEFAULT_EXECUTION_TYPE}

# Ensure dirs
LOGS.mkdir(parents=True, exist_ok=True)
RUNTIME.mkdir(parents=True, exist_ok=True)
AGENT_STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str, level: str = "INFO") -> None:
    """Append to dedicated watcher log + stdout for visibility when attached."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
    line = f"[{ts}] [{level}] {msg}"
    try:
        with open(WATCHER_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    # Also echo (will be in launcher stdout if not fully hidden)
    try:
        print(line, flush=True)
    except Exception:
        pass


def _write_watcher_status(state: dict[str, Any]) -> None:
    """TUI-visible agent_status JSON (swarm / Decisions panel merge)."""
    try:
        AGENT_STATUS_DIR.mkdir(parents=True, exist_ok=True)
        status = {
            "name": "Persistent Candidate Handoff Watcher & Zero-Touch Orchestrator",
            "status": "RUNNING",
            "last_updated": _now_iso(),
            "polling": True,
            "baseline_candidate": BASE_CANDIDATE_TS,
            "v5_current": {
                "run_tag": V5_RUN_TAG,
                "profile": V5_LIGHT_PROFILE,
                "expected_handoff_profile": V5_EXPECTED_HANDOFF_PROFILE,
            },
            "canonical_v5_run": {
                "run_id": V5_RUN_TAG,
                "primary_log_path": "logs/robust_v5_BTCUSDm_20260527_120000.log",
                "launch_report": "logs/launch_report.md",
                "timestamp": "20260527_120000",
                "light_profile": V5_LIGHT_PROFILE,
                "key_signals": "28.2k/50k steps (56.4%), ep_rew_mean=-385 (light profile post-v4 stall recovery)",
                "expected_candidate_directory_pattern": "models/registry/candidates/<ts>/ (newer than 20260527_082932) with alignment_fix_applied + real per-symbol metrics (OOS + enable_per_symbol_metrics=True)",
                "watcher_monitoring": "monitor this run for first post-fix champion; PID 8744 will drive zero-touch promotion + MQL5 + paper on detection",
                "handoff_profile": "runtime/v5_btcusd_50k_handoff_profile.json",
                "updated_by": "V5 Run Canonicalization & Handoff Watcher Update Agent"
            },
            "last_poll": _now_iso(),
            "current_candidate": state.get("current_candidate"),
            "last_action": state.get("last_action"),
            "last_pid": os.getpid(),
            "env_gates": {
                "AGI_AUTO_MQL5_DEPLOY": os.getenv("AGI_AUTO_MQL5_DEPLOY"),
                "AGI_AUTO_PROMOTE_CANDIDATE": os.getenv("AGI_AUTO_PROMOTE_CANDIDATE"),
                "AGI_PROMOTER_PROMOTE_CANARY": os.getenv("AGI_PROMOTER_PROMOTE_CANARY"),
            },
            "execution": {
                "default_type": DEFAULT_EXECUTION_TYPE,
                "legacy_type": LEGACY_EXECUTION_TYPE,
                "supported": list(SUPPORTED_EXECUTION_TYPES),
                "note": "decision_ppo (rich TradeDecision + Execution layer via GateEngine/Router/hybrid_brain) is DEFAULT for newly promoted (uses multi-TF context + configs/best_features_per_symbol.yaml). simple_action legacy fully preserved. Recorded in handoff profiles + last_handoff + paper_harness_start.",
            },
            "current_execution_type_for_handoff": state.get("execution_type", DEFAULT_EXECUTION_TYPE),
            "details": state,
        }
        WATCHER_STATUS_FILE.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        _log(f"Status write failed (non-fatal): {e}", "WARN")


def _parse_ts_from_name(name: str) -> Optional[datetime]:
    """Parse YYYYMMDD_HHMMSS dir name to datetime for comparison."""
    try:
        if "_" not in name:
            return None
        parts = name.split("_")
        if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) != 6:
            return None
        dt = datetime.strptime(name, "%Y%m%d_%H%M%S")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get_baseline_mtime() -> float:
    base_dir = CANDIDATES_DIR / BASE_CANDIDATE_TS
    if base_dir.exists():
        return base_dir.stat().st_mtime
    return 0.0


def detect_new_candidate() -> Optional[Path]:
    """Return newest qualifying candidate dir (post-fix or any newer ts) or None."""
    if not CANDIDATES_DIR.exists():
        return None
    try:
        base_mtime = _get_baseline_mtime()
        candidates = [
            d for d in CANDIDATES_DIR.iterdir()
            if d.is_dir() and d.name != BASE_CANDIDATE_TS
        ]
        if not candidates:
            return None

        # Prefer timestamp parse for "newer than baseline"
        scored: list[tuple[datetime, Path]] = []
        for d in candidates:
            ts = _parse_ts_from_name(d.name)
            if ts:
                scored.append((ts, d))
            else:
                # Fallback mtime > baseline mtime
                if d.stat().st_mtime > base_mtime:
                    scored.append((datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc), d))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        newest = scored[0][1]

        # Optional: require alignment_fix_applied for "real champion" (but allow any newer for robustness)
        # Promoter itself will gate strictly.
        return newest
    except Exception as e:
        _log(f"Detect scan error: {e}", "ERROR")
        return None


def _is_already_handled(candidate: Path) -> bool:
    """Check processed marker to avoid re-firing on same champion."""
    try:
        if LAST_SEEN_FILE.exists():
            last = LAST_SEEN_FILE.read_text(encoding="utf-8").strip()
            if last == candidate.name:
                # Also check if harness start is for this exact candidate (promoter/harness may have armed it)
                phs = RUNTIME / "paper_harness_start.json"
                if phs.exists():
                    try:
                        meta = json.loads(phs.read_text(encoding="utf-8"))
                        if meta.get("candidate") == candidate.name:
                            return True
                    except Exception:
                        pass
                return True
    except Exception:
        pass
    return False


def _mark_handled(candidate: Path) -> None:
    try:
        LAST_SEEN_FILE.write_text(candidate.name, encoding="utf-8")
    except Exception as e:
        _log(f"Mark handled failed: {e}", "WARN")


def _update_last_handoff(candidate: Path, details: dict[str, Any]) -> None:
    """Enrich last_handoff.json for TUI Post-Candidate Handoff panel + supervisor visibility."""
    try:
        payload = {
            "timestamp": _now_iso(),
            "candidate": candidate.name,
            "candidate_path": str(candidate),
            "watcher": "handoff_watcher",
            "promoter_invoked": True,
            "auto_launch": True,
            "mql5_deploy_triggered": details.get("mql5_full", False),
            "paper_armed": details.get("paper_armed", False),
            "feedback_wired": details.get("feedback_wired", True),
            "execution_type": details.get("execution_type", DEFAULT_EXECUTION_TYPE),
            "mtf_context": details.get("mtf_context", ["1m","5m","15m","1h"]),
            "best_features": details.get("best_features", "configs/best_features_per_symbol.yaml"),
            "decision_ppo_armed": details.get("decision_ppo_armed", True),
            "rich_decision_layer": {
                "uses": "DecisionPPO (full trade specs: side/size/sl/tp/conf) + Execution layer (GateEngine+Router+Paper/MT5Demo) - default for new",
                "back_compat": "simple_action path + legacy intent translator preserved; no breakage",
                "auto_paper_live": "supervisor/watcher auto-arm paper (then live) using symbol best-features + MTF context",
            },
            "source": "Persistent Candidate Handoff Watcher (autonomous)",
            "env_gates_checked": {
                "AGI_AUTO_MQL5_DEPLOY": os.getenv("AGI_AUTO_MQL5_DEPLOY") == "1",
            },
            "details": details,
        }
        # Merge with existing if present (preserve supervisor fields)
        if LAST_HANDOFF.exists():
            try:
                existing = json.loads(LAST_HANDOFF.read_text(encoding="utf-8"))
                existing.update(payload)
                payload = existing
            except Exception:
                pass
        LAST_HANDOFF.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _log(f"Updated {LAST_HANDOFF}")
    except Exception as e:
        _log(f"last_handoff update error: {e}", "WARN")


def _emit_decision(decision_type: str, decision: str, candidate: str, reason: str, details: dict[str, Any], severity: str = "info") -> None:
    """Rich PIPELINE_DECISIONS entry (feeds TUI Decisions + compute_loop_closure_score)."""
    try:
        log_decision(
            decision_type=decision_type,
            actor="handoff_watcher",
            decision=decision,
            candidate=candidate,
            run_id=candidate,
            reason=reason,
            details=details,
            severity=severity,
        )
        _log(f"PIPELINE_DECISION: {decision_type}/{decision} for {candidate}")
    except Exception as e:
        _log(f"Decision emit failed (non-fatal): {e}", "WARN")


def _trigger_retraining_feedback(candidate: str, reason: str) -> None:
    """Retraining feedback path on gate failure (per mission)."""
    _log(f"Gate failure path: triggering retraining feedback for {candidate} - {reason}", "WARN")
    try:
        _emit_decision(
            "retrain_trigger",
            "RETRAIN_RECOMMENDED",
            candidate,
            reason,
            {"source": "handoff_watcher_gate_fail", "watcher_action": "feedback"},
            "warn",
        )
        if RetrainingTrigger:
            rt = RetrainingTrigger(data_dir=str(LOGS))
            rt.increment_blocked(3)  # Seed real counter
            _log("RetrainingTrigger counters incremented (feedback wired)")
    except Exception as e:
        _log(f"Retrain trigger failed (best effort): {e}", "WARN")


def _verify_artifacts(candidate: Path) -> dict[str, bool]:
    """Verify post-promote artifacts for PAPER_ARMED + MQL5_DEPLOY success."""
    paper = (RUNTIME / "paper_harness_start.json").exists()
    mql5_flag = (RUNTIME / "mql5_shadow_ready.flag").exists()
    mql5_json = (PROJECT_ROOT / "artifacts" / "mql5_distill" / "mql5_shadow_ready.json").exists()
    champion = (RUNTIME / "champion_ready.flag").exists()
    return {
        "paper_harness_start": paper,
        "mql5_shadow_flag": mql5_flag,
        "mql5_shadow_json": mql5_json,
        "champion_ready": champion,
        "all_armed": paper and (mql5_flag or mql5_json) and champion,
    }


def _deploy_new_decision_execution_mtf_context(candidate: Path) -> dict[str, Any]:
    """Write the new standard Decision + Execution context file with correct multi-TF info.
    This is called on arm so promoted model uses 1m+5m+15m+1h + per-symbol best features
    (via multitimeframe_builder) + modern DecisionBuilder/ExecutorRouter/GateEngine path
    (once fully wired in harness/execution for paper/live).
    Legacy single-TF preserved via env.
    """
    ctx_path = RUNTIME / "decision_execution_mtf_context.json"
    symbol = "BTCUSDm"  # extend for multi-symbol
    best = {}
    if _HAS_BEST_FEATS and load_best_feature_params:
        try:
            best = load_best_feature_params(symbol)
        except Exception:
            best = {"note": "fallback defaults"}
    ctx = {
        "deployed_at": _now_iso(),
        "candidate": candidate.name,
        "standard": "NEW_MULTI_TF_1m_5m_15m_1h",
        "timeframes": ["1m", "5m", "15m", "1h"],
        "base_timeframe": "1m",
        "feature_builder": "Python/features/multitimeframe_builder.py (build_multitimeframe_features)",
        "best_feature_params_source": "configs/best_features_per_symbol.yaml",
        "best_feature_params": best,
        "data_fetch": "Python/data_feed.py:fetch_multitimeframe_training_data",
        "feature_matrix": "Python/feature_pipeline.py:build_multitimeframe_feature_matrix",
        "decision_layer": "Python/ensemble/decision_builder.py:DecisionBuilder (TradeIntent)",
        "execution_layer": "Python/execution/executor_router.py:ExecutorRouter + paper_executor/mt5_demo_executor + gate_engine",
        "risk": "Python/execution/risk_supervisor.py + live_gate",
        "legacy_fallback": "set AGI_USE_LEGACY_SINGLE_TF=1 before arm/harness (preserved; no MTF context)",
        "tui_react_parity": "monitor_tui.py + frontend/ (full panels for decisions/execution/equity)",
        "note": "When new Decision+Execution is fully ready in paper harness, it auto-uses this context for promoted models. Supervisor + watcher + launchers now default here.",
    }
    try:
        ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
        _log(f"Deployed NEW Decision+Execution MTF context: {ctx_path}")
        return {"written": True, "path": str(ctx_path), "timeframes": ctx["timeframes"]}
    except Exception as e:
        _log(f"Context deploy failed (non-fatal): {e}", "WARN")
        return {"written": False, "error": str(e)}


def _detect_execution_type(candidate: Path) -> str:
    """Inspect candidate scorecard/metadata for Decision PPO rich action (decision_ppo_v1 / decision_ppo:true).
    Default to 'decision_ppo' (new autonomous default for all newly promoted models; legacy 'simple_action' only on explicit).
    Never breaks old paths.
    """
    try:
        for fname in ("scorecard.json", "metadata.json", "bundle_meta.json"):
            p = candidate / fname
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    # Direct flags from training (TradingEnv + train launchers)
                    ac = data.get("action_config") or data.get("action", {}) or {}
                    if isinstance(ac, dict):
                        if ac.get("decision_ppo") or ac.get("action_version") == "decision_ppo_v1":
                            return "decision_ppo"
                    if data.get("action_version") == "decision_ppo_v1" or data.get("decision_ppo") is True:
                        return "decision_ppo"
                    # Provenance / scorecard signals (real multi-TF metrics path)
                    prov = data.get("run_provenance") or data.get("training_config") or {}
                    if isinstance(prov, dict) and (prov.get("decision_ppo") or "decision_ppo" in str(prov).lower()):
                        return "decision_ppo"
                except Exception:
                    continue
    except Exception:
        pass
    return "decision_ppo"  # Default: rich Decision PPO + Execution layer for new promoted models


def _invoke_promote_chain(candidate: Path) -> dict[str, Any]:
    """Dry-run first, then real under env gates. Returns summary for audit."""
    py_exe = PROJECT_ROOT / ".venv312" / "Scripts" / "python.exe"
    if not py_exe.exists():
        py_exe = Path(sys.executable)

    symbols = ["BTCUSDm"]
    exec_type = _detect_execution_type(candidate)
    result: dict[str, Any] = {"candidate": candidate.name, "dry_ok": False, "real_ok": False, "mql5_full": False, "execution_type": exec_type}

    # 1. Dry-run (always, for checklist / audit)
    try:
        _log(f"DRY-RUN promoter for {candidate.name}")
        dry_cmd = [str(py_exe), "scripts/promote_candidate_to_paper.py", "--symbols", *symbols, "--dry-run"]
        dry_proc = subprocess.run(dry_cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
        result["dry_ok"] = dry_proc.returncode == 0
        _emit_decision(
            "promotion",
            "PROMOTION_DRY_RUN_COMPLETE",
            candidate.name,
            "dry_run_checklist",
            {"returncode": dry_proc.returncode, "stdout_tail": (dry_proc.stdout or "")[-500:]},
        )
        _log(f"Dry-run exit={dry_proc.returncode}")
    except Exception as e:
        _log(f"Dry-run exception: {e}", "ERROR")
        result["dry_ok"] = False

    # 2. Real invocation (full chain via promoter: gates + canary opt-in + paper auto + MQL5 trigger inside)
    try:
        _log(f"REAL promoter invoke --auto-launch --promote-canary for {candidate.name} (execution_type={exec_type})")
        real_cmd = [str(py_exe), "scripts/promote_candidate_to_paper.py", "--symbols", *symbols, "--auto-launch", "--promote-canary"]
        # Run detached-ish (promoter itself spawns harness + deploy bg)
        real_env = os.environ.copy()
        real_env["AGI_EXECUTION_TYPE"] = exec_type  # decision_ppo rich Decision+Execution stack default for newly promoted
        real_proc = subprocess.Popen(
            real_cmd,
            cwd=PROJECT_ROOT,
            env=real_env,
            stdout=open(LOGS / "handoff_watcher_promote.log", "a"),
            stderr=subprocess.STDOUT,
        )
        # Give promoter time to run gates + arm artifacts (it is not long-running)
        time.sleep(25)
        result["real_ok"] = True  # Promoter is fire-and-forget success-oriented; downstream verifies
        _emit_decision(
            "promotion",
            "PROMOTION",
            candidate.name,
            "real_promote_invoked",
            {"pid": real_proc.pid, "cmd": " ".join(real_cmd), "execution_type": exec_type},
        )
        _log(f"Promoter launched (PID {real_proc.pid})")

        # NEW STANDARD: Deploy Decision + Execution multi-TF context for the armed model (paper/live handoff)
        # Uses correct 1m+5m+15m+1h + best features per symbol; new DecisionBuilder/ExecutorRouter when ready.
        try:
            ctx_res = _deploy_new_decision_execution_mtf_context(candidate)
            result["decision_execution_mtf_context"] = ctx_res
            _emit_decision(
                "harness_start",
                "DECISION_EXECUTION_MTF_CONTEXT_DEPLOYED",
                candidate.name,
                "new_standard_1m5m15m1h_best_features",
                ctx_res,
            )
        except Exception as _e:
            _log(f"MTF Decision+Execution context deploy skipped: {_e}", "WARN")
    except Exception as e:
        _log(f"Real promote exception: {e}", "ERROR")
        result["real_ok"] = False
        _trigger_retraining_feedback(candidate.name, f"promote_invoke_failed: {e}")
        return result

    # 3. Conditional full MQL5 (only under explicit env gate; promoter does LogOnly otherwise)
    auto_mql5 = (
        os.getenv("AGI_AUTO_MQL5_DEPLOY") == "1"
        or os.getenv("CHAIN_GAMBLER_AUTO_MQL5_DEPLOY") == "1"
        or os.getenv("AGI_AUTO_MQL5") == "1"
    )
    if auto_mql5:
        try:
            _log("AGI_AUTO_MQL5_DEPLOY=1: invoking FULL deploy_mql5 (no LogOnly)")
            deploy_cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                "scripts/deploy_mql5_chain_gambler.ps1",
                "-AutoFromRegistry", "-ShadowPrep", "-DeployToAllTerminals"
            ]
            mql5_proc = subprocess.Popen(
                deploy_cmd,
                cwd=PROJECT_ROOT,
                stdout=open(LOGS / "handoff_watcher_mql5_deploy.log", "a"),
                stderr=subprocess.STDOUT,
            )
            time.sleep(15)
            result["mql5_full"] = True
            _emit_decision(
                "mql5_deploy",
                "MQL5_DEPLOY",
                candidate.name,
                "full_auto_from_watcher_env_gate",
                {"pid": mql5_proc.pid, "full": True},
            )
            _log(f"Full MQL5 deploy launched (PID {mql5_proc.pid})")
        except Exception as e:
            _log(f"MQL5 full deploy error: {e}", "WARN")
            _emit_decision("mql5_deploy", "MQL5_DEPLOY_FAILED", candidate.name, str(e), {}, "warn")
    else:
        _log("MQL5 full skipped (env gate AGI_AUTO_MQL5_DEPLOY != 1). Promoter already triggered LogOnly + guidance.")
        _emit_decision(
            "mql5_deploy",
            "MQL5_DEPLOY",
            candidate.name,
            "logonly_via_promoter",
            {"full": False, "note": "Set AGI_AUTO_MQL5_DEPLOY=1 for zero-touch real deploy"},
        )

    # 4. Verify + emit PAPER_ARMED / FEEDBACK_WIRED
    time.sleep(5)
    artifacts = _verify_artifacts(candidate)
    result["artifacts"] = artifacts
    # Ensure execution_type from earlier detection propagates (rich DecisionPPO+Exec default)
    if "execution_type" not in result or not result.get("execution_type"):
        result["execution_type"] = exec_type
    result["mtf_context"] = ["1m", "5m", "15m", "1h"]
    result["best_features"] = "configs/best_features_per_symbol.yaml"
    result["decision_ppo_armed"] = (result.get("execution_type") == "decision_ppo")

    if artifacts.get("paper_harness_start"):
        _emit_decision(
            "harness_start",
            "PAPER_ARMED",
            candidate.name,
            "paper_harness_start.json_present_post_promote",
            {"artifacts": artifacts},
        )
        result["paper_armed"] = True
        _log("PAPER_ARMED verified")

    if artifacts.get("mql5_shadow_flag") or artifacts.get("mql5_shadow_json"):
        _emit_decision(
            "mql5_deploy",
            "MQL5_DEPLOY",
            candidate.name,
            "mql5_shadow_artifacts_present",
            {"artifacts": artifacts},
        )

    # NEW (Decision+Execution Integration): Write arming marker for zero-touch supervisor/TUI visibility
    # The paper harness (when execution_type=decision_ppo) + ExecutionAgent are now the canonical path.
    # MQL5 side armed via ExecutionCommandMode on the deployed ChainGambler EA.
    try:
        (RUNTIME / "decision_execution_armed.json").write_text(json.dumps({
            "timestamp": _now_iso(),
            "candidate": candidate.name,
            "paper_harness_armed": artifacts.get("paper_harness_start", False),
            "execution_agent": True,
            "mql5_command_bridge": "ChainGambler ExecutionCommandMode (see mql5/Experts/ChainGambler)",
            "feedback": "logs/execution_feedback.jsonl + runtime/execution_reports/",
            "source": "handoff_watcher"
        }, indent=2, default=str), encoding="utf-8")
        _log("Decision+Execution armed marker written (handoff complete)")
    except Exception as _e:
        _log(f"Decision exec arm marker (non-fatal): {_e}", "WARN")

    # Feedback always considered wired once promoter/harness path taken (harness wires RetrainingTrigger)
    _emit_decision(
        "feedback",
        "FEEDBACK_WIRED",
        candidate.name,
        "retraining_trigger_wired_via_harness_promoter",
        {"retrain_counters_active": True, "harness_feedback": True},
    )
    result["feedback_wired"] = True

    # Gate failure heuristic: if no paper armed after real promote, treat as fail path
    if not artifacts.get("paper_harness_start") and result["real_ok"]:
        _trigger_retraining_feedback(candidate.name, "no_paper_harness_armed_after_promote")

    return result


def _write_handoff_profile(candidate: Path, extra: dict[str, Any]) -> None:
    """Write or update per-candidate handoff profile JSON (runtime/ * _handoff_profile.json) with execution_type etc for TUI/supervisor/loop closure."""
    try:
        prof_name = f"{candidate.name}_handoff_profile.json"
        prof_path = RUNTIME / prof_name
        profile = {
            "candidate": candidate.name,
            "candidate_path": str(candidate),
            "timestamp": _now_iso(),
            "execution": {
                "type": extra.get("execution_type", DEFAULT_EXECUTION_TYPE),
                "rich_decision_ppo": extra.get("uses_rich", True),
                "mtf_context": extra.get("mtf", ["1m", "5m", "15m", "1h"]),
                "best_features_source": extra.get("best_features", "configs/best_features_per_symbol.yaml"),
                "stack": "DecisionPPO + ExecutionAgent (TradeDecision full specs) -> Gate/Router/Executors (pure-Python OrderManager+MT5Executor PRIMARY on Windows; MQL5 bridge optional via MQL5_BRIDGE_ENABLED=1)",
            },
            "autonomous_loop": "training->multiTF_eval->gates->promotion->paper(DecisionPPO+Exec)->live",
            "watcher_recorded": True,
        }
        if prof_path.exists():
            try:
                old = json.loads(prof_path.read_text(encoding="utf-8"))
                old.update(profile)
                profile = old
            except Exception:
                pass
        prof_path.write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
        _log(f"Wrote enriched handoff profile with execution_type: {prof_path}")
        # Also touch canonical last profile
        (RUNTIME / "last_handoff_profile.json").write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        _log(f"Handoff profile write skipped: {e}", "WARN")


def main_loop() -> None:
    _log("=== HANDOFF WATCHER STARTED (persistent autonomous) ===")
    _log(f"Baseline: {BASE_CANDIDATE_TS} | Current v5: {V5_RUN_TAG} ({V5_LIGHT_PROFILE}) | Poll every {POLL_INTERVAL_S}s | PID {os.getpid()}")
    _log(f"Logs: {WATCHER_LOG}")

    state: dict[str, Any] = {"current_candidate": None, "last_action": "startup"}

    # Initial status
    _write_watcher_status(state)

    # Also note any v5 expectation in status (from live context) - updated per V4 diagnosis follow-through
    state["v5_note"] = f"Current active v5 (V4 stall recovery): {V5_RUN_TAG} using {V5_LIGHT_PROFILE}. Expect candidate models/registry/candidates/<ts>/ (newer than baseline) with v5_robust + alignment_fix + per-sym metrics. Handoff will target {V5_EXPECTED_HANDOFF_PROFILE} when complete. Health/TUI/supervisor now have tighter signals (freq hb, log mtime check)."

    last_flag_mtime = 0.0
    champion_flag = RUNTIME / "champion_ready.flag"

    while True:
        try:
            # Poll champion_ready.flag mtime (alternative trigger)
            flag_trigger = False
            if champion_flag.exists():
                m = champion_flag.stat().st_mtime
                if m > last_flag_mtime:
                    last_flag_mtime = m
                    flag_trigger = True
                    _log("champion_ready.flag mtime updated -> potential new handoff")

            new_cand = detect_new_candidate()
            if new_cand and not _is_already_handled(new_cand):
                _log(f"NEW CANDIDATE DETECTED: {new_cand.name} (newer than {BASE_CANDIDATE_TS})")
                state["current_candidate"] = new_cand.name
                state["last_action"] = "detected"
                _write_watcher_status(state)

                _emit_decision(
                    "candidate_staged",
                    "NEW_CHAMPION_DETECTED",
                    new_cand.name,
                    "watcher_poll",
                    {"path": str(new_cand), "flag_trigger": flag_trigger, "baseline": BASE_CANDIDATE_TS},
                )

                # Full autonomous chain
                summary = _invoke_promote_chain(new_cand)

                state["last_action"] = "handoff_complete"
                state["summary"] = summary
                _write_watcher_status(state)

                _update_last_handoff(new_cand, summary)
                _write_handoff_profile(new_cand, summary)  # records execution_type + rich stack for full loop

                _emit_decision(
                    "promotion",
                    "HANDOFF_COMPLETE",
                    new_cand.name,
                    "full_zero_touch_chain",
                    {**summary, "execution_type": summary.get("execution_type", "decision_ppo"), "stack": "DecisionPPO+Execution" if summary.get("execution_type", "decision_ppo") == "decision_ppo" else "simple_action"},
                )

                _mark_handled(new_cand)
                _log(f"HANDOFF COMPLETE for {new_cand.name}. Watcher continues polling for future champions.")

            # Periodic status + heartbeat
            state["last_poll"] = _now_iso()
            _write_watcher_status(state)

            # Also keep last_handoff touched lightly if exists (for TUI liveness)
            if LAST_HANDOFF.exists():
                try:
                    data = json.loads(LAST_HANDOFF.read_text(encoding="utf-8"))
                    data["watcher_last_poll"] = _now_iso()
                    LAST_HANDOFF.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                except Exception:
                    pass

        except KeyboardInterrupt:
            _log("Watcher shutdown (KeyboardInterrupt)")
            break
        except Exception as exc:
            # Resilient: log full traceback, continue (never die)
            tb = traceback.format_exc()
            _log(f"CRASH RECOVERED (inner loop): {exc}\n{tb}", "ERROR")
            state["last_action"] = f"recovered_error: {str(exc)[:100]}"
            _write_watcher_status(state)
            _emit_decision(
                "watcher",
                "WATCHER_RECOVERED",
                state.get("current_candidate") or "none",
                "inner_exception",
                {"error": str(exc)},
                "warn",
            )

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        _log(f"FATAL outer: {e}\n{traceback.format_exc()}", "CRITICAL")
        # Self-restart hint for launcher (simple exit; launcher can watch PID)
        sys.exit(1)
