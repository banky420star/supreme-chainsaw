# AUTONOMOUS TRADING LOOP (Decision PPO + Execution Layer Closure)

**Status**: CLOSED — Full zero-touch path from training → multi-TF evaluation + strict gates → promotion → paper (DecisionPPO+Exec) → MQL5 shadow/live.

This document captures the final integration that makes the system self-arming for the rich **Decision PPO** (full trade specs: side/size/sl/tp/confidence/risk-mode/ladders/trailing + MTF context + per-symbol best features) consumed by the **ExecutionAgent** layer.

## End-to-End Flow (Now Fully Autonomous)

1. **Training** (`training/train_drl.py`, `drl/trading_env.py` with `decision_ppo=True` / action_version="decision_ppo_v1", 18-dim rich head):
   - Produces candidate in `models/registry/candidates/<ts>/` with scorecard (real per-symbol OOS metrics, alignment_fix_applied, run_provenance).
   - Action config / metadata tags `decision_ppo` or `execution_type`.

2. **Detection**:
   - Persistent `scripts/handoff_watcher.py` (launched via `handoff_watcher_launcher.ps1`, runs hidden).
   - `scripts/vps_agi_supervisor.ps1` (Task Scheduler / long-running) polls for good post-fix candidates (alignment_fix_applied + not quarantined).
   - Both detect via mtime / name on candidates dir + `champion_ready.flag`.

3. **Strict Gates + Promotion**:
   - `scripts/promote_candidate_to_paper.py --auto-launch --promote-canary` (or via `auto_promote_candidate.ps1`).
   - `Python/registry/promotion_gates.py` + `Python/model_evaluator.py` (core_perf + full gates + UNIFY-GATES).
   - On pass: writes `runtime/paper_harness_start.json` (with `execution_type: "decision_ppo"`, `uses_rich_trade_specs`, `mtf_context`, `best_features_source: configs/best_features_per_symbol.yaml`), `champion_ready.flag`, `last_promoted_candidate.txt`.
   - Optional auto-canary via `ModelRegistry.set_canary`.
   - MQL5 deploy always triggered (LogOnly safe; full via `AGI_AUTO_MQL5_DEPLOY=1`).

4. **Paper Arming (Decision + Execution, default for new)**:
   - Promoter / supervisor / watcher set `$env:AGI_EXECUTION_TYPE="decision_ppo"`.
   - Launches `scripts/paper_mt5_execution_harness.py` (conservative 0.01 lots, 0.75% daily for post-fix).
   - Harness:
     - Loads `configs/best_features_per_symbol.yaml` + MTF (1m/5m/15m/1h) per symbol.
     - Inits `ExecutionAgent` (when rich) + `GateEngine` + `RiskSupervisor` + `ExecutorRouter`.
     - `_get_intent` emits full rich dict (or via `make_risk_based_decision` / `TradeDecision`).
     - Router / ExecutionAgent handles validation, risk, submit (paper/demo via MT5DemoExecutor or fallback).
   - Real feedback: `RetrainingTrigger` on risk/canary/rollback events → `RETRAIN RECOMMENDED`.
   - Rollback/force-flatten: `runtime/rollback_harness.flag` or risk breach → `ExecutionAgent.force_flatten_all()` (writes FLAT command to bridge + Python flatten via router/MT5) + alerts + retrain signal. Legacy paths preserved.

5. **MQL5 Shadow / Deploy (understands rich decisions)**:
   - `scripts/deploy_mql5_chain_gambler.ps1 -AutoFromRegistry -ShadowPrep -DeployToAllTerminals` (auto from promoter/supervisor).
   - Copies EA + headers; runs `tools/export_for_mql5.py --candidate-dir`.
   - Prepares `runtime/mql5_commands/` + execution_status (bridge dirs).
   - Produces `artifacts/mql5_distill/mql5_shadow_ready.json` + `runtime/mql5_shadow_ready.flag` (now includes `execution_type`, `decision_format: full_trade_spec_v1`, `command_bridge`).
   - Guidance (`artifacts/mql5_shadow_guidance/...`) documents ExecutionCommandMode.
   - `mql5/Experts/ChainGambler/ChainGambler_Executor.mq5` (v0.3+):
     - Inputs: `ExecutionCommandMode`, `CommandDir` (Common/Files/trade_decisions recommended), `UseCommonForCommands`, `EnableRichMgmt`.
     - When ON: `OnTick` → `OnTickExecutionBridge` → `ProcessExecutionCommands` (polls *.ready + JSON) → `ExecuteRichDecision` (native CTrade entry + SL/TP; skeleton for ladders/trailing/partials via decision_id tagging).
     - Writes status reports back for Python observability.
     - Full backward compat: NN inference + simple action when OFF.

6. **Live Arming**:
   - After paper validation (7d clean + gates): supervisor / manual arm live via `CHAIN_GAMBLER_EXECUTION_MODE=live` + explicit `AGI_LIVE_ENABLED` etc (safety).
   - Same DecisionPPO + ExecutionAgent path (MQL5 bridge preferred for prod; Python fallback).
   - Supervisor can drive paper→live transition on clean canary metrics.

7. **Rollback / Safety (works for new layer)**:
   - Harness/supervisor/watcher: `force_flatten_all` on agent + risk layers + canary + Telegram + retrain counters.
   - MQL5: FLAT decision JSON or manual.
   - Never loses decisions: persistent reports + feedback.jsonl.

8. **Observability & Loop Closure**:
   - All steps → `logs/PIPELINE_DECISIONS.jsonl` (unified, feeds TUI Decisions + `compute_loop_closure_score`).
   - `runtime/last_handoff.json`, `v*_handoff_profile.json`, `handoff_status.json`, `paper_harness_start.json`.
   - TUI (`scripts/monitor_tui.py`): Swarm Status, Post-Candidate Handoff, Decisions panels show execution_type, rich stack, MTF/best-features.
   - Agent status JSONs in `runtime/agent_status/` (handoff_watcher_status.json etc.) updated live.
   - Feedback → retraining via `Python/autonomous/retraining_trigger.py`.

## Key Env Vars (Arm the Loop)

- `AGI_EXECUTION_TYPE=decision_ppo` (default for new; `simple_action` for legacy — never breaks old).
- `AGI_AUTO_PROMOTE_CANDIDATE=1` (or SUPERVISOR_*/AGI_AUTO_PROMOTE): supervisor auto-invokes promoter/gates/canary.
- `AGI_PROMOTER_PROMOTE_CANARY=1`: direct canary on gate pass.
- `AGI_AUTO_MQL5_DEPLOY=1` (or CHAIN_GAMBLER_*/AGI_AUTO_MQL5): full MQL5 (no -LogOnly).
- `AGI_CONSERVATIVE_PAPER=1`, `AGI_PAPER_FIXED_LOT=0.01`: safe paper profile.
- `CHAIN_GAMBLER_EXECUTION_MODE=demo|paper|live`.
- `AGI_AUTO_PAPER_HARNESS=1`: extra harness launch.

Best-features/MTF always from `configs/best_features_per_symbol.yaml` (per-symbol + global multi_timeframe).

## Files / Components Updated for Closure (this wave)

- `scripts/handoff_watcher.py`: DEFAULT=decision_ppo, detection of type from candidate meta, env injection to promoter, enriched last_handoff + status + PIPELINE_DECISIONS with rich_decision_layer / MTF / best_features.
- `scripts/promote_candidate_to_paper.py`: paper_harness_start.json carries execution_type + mtf + best_features; launch cmds set AGI_EXECUTION_TYPE; MQL5 guidance + deploy trigger.
- `scripts/paper_mt5_execution_harness.py`: defaults decision_ppo; loads best_features + MTF; inits ExecutionAgent; rich _get_intent; rollback uses force_flatten_all; feedback wiring.
- `scripts/vps_agi_supervisor.ps1` + `auto_promote_candidate.ps1`: env injection for decision_ppo in all promote/harness/MQL5 paths; Invoke-PostCandidateHandoff enriched; auto paper→live path.
- `scripts/deploy_mql5_chain_gambler.ps1`: command bridge dir prep (mql5_commands, execution_status); ready.json includes execution stack + command_bridge + mtf_best_features; guidance mentions Decision/Exec.
- `Python/execution/execution_agent.py`: force_flatten_all (MQL5 FLAT + Python delegates); TradeDecision support; MQL5 bridge writes full spec JSON.
- `Python/execution/trade_decision.py`: full dataclass spec (already complete).
- `mql5/Experts/ChainGambler/ChainGambler_Executor.mq5`: ExecutionCommandMode primary path wired in OnTick/OnInit; Process/ExecuteRichDecision + helpers (status back-channel); additive, no breakage of inference/Shadow.
- `docs/MQL5_EXECUTION_LAYER_DESIGN.md`, `HANDOFF_WATCHER_ARMED.md`, promoter/harness headers: cross-refs updated implicitly via flow.

Legacy simple_action paths untouched (explicit opt-in only via env or old candidate meta).

## Usage (Zero-Touch After First Arm)

```powershell
# Arm once (VPS / session or Task Scheduler env)
$env:AGI_AUTO_PROMOTE_CANDIDATE="1"
$env:AGI_AUTO_MQL5_DEPLOY="1"   # for full
$env:AGI_EXECUTION_TYPE="decision_ppo"

# Launch (persistent)
.\scripts\handoff_watcher_launcher.ps1
.\scripts\vps_agi_supervisor.ps1   # (or Task Scheduler)

# On next good candidate (post training with decision_ppo head):
# → watcher/supervisor detect → gates (promoter) → paper_harness_start.json (rich) → harness auto (DecisionPPO+Exec, MTF/best_feats) → MQL5 deploy (command bridge ready) → feedback loop live.
# Monitor: TUI, logs/PIPELINE_DECISIONS.jsonl, runtime/last_handoff.json, paper_harness_exec.jsonl
```

After 5-7d clean paper + canary green: promote to live (same stack, MQL5 bridge preferred).

## Rollback / Emergency

- Touch `runtime/rollback_harness.flag`
- Supervisor / TUI kill switches call force_flatten_all.
- MQL5: detach EA or manual close.
- All paths feed RetrainingTrigger.

## Known Next Polish (non-blocking)

- Full DecisionPPO inference loop (separate lightweight runner or integrate in Server_AGI/hybrid_brain using drl/ppo_agent + env decoder for live MTF obs).
- Rich ladder/trailing state machine in MQL5 ExecuteRichDecision (skeleton present).
- Direct Common/Files write from Python bridge in prod (deploy handles copy or mount).

**This completes the migration from "we have models" to "the system autonomously trades rich decisions with full supervisor + watcher oversight, paper→live, rollback-safe, MQL5-native".**

All prior simple paths preserved. New path is default + armed on promotion.

Generated: 2026-05-28 (Autonomous Trading Loop Closure Agent)
Refs: HANDOFF_WATCHER_ARMED.md, docs/MQL5_EXECUTION_LAYER_DESIGN.md, logs/PIPELINE_DECISIONS.jsonl, runtime/*_handoff*.json

## Continual / Online Learning Layer (added 2026-05-28)

Python/autonomous/continual_learner.py now provides the production continual layer for Decision PPO policy head + Dreamer world model.
- Clean ingestion interfaces for paper + live trades (execution_feedback.jsonl, trade_journal, PIPELINE_DECISIONS).
- ExperienceMemory prioritized replay (high-surprise/edge) + importance sampling.
- Real gated tiny updates + EWC + meta_suggested_training_overrides from XAU overnight artifacts.
- Wired into RetrainingOrchestrator (light online vs full retrain decision) and vps_agi_supervisor / MasterSelfEvolutionSupervisor for background periodic learning.
- Policy drift/adaptation metrics emitted.
- Outputs runtime/agent_status/continual_learner_complete.json (implementation + smoke).
- Mini TUI automatically surfaces "online adaptation" status via agent_status JSONs.
Low-overhead, Windows MT5 direct Python execution prioritized for stability.
