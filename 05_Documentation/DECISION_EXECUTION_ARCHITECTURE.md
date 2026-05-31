# Decision + Execution Architecture (Clean Separation for Autonomous Trading)

**Status:** Production-grade implementation complete (2026-05-28)  
**Owner:** Execution Layer & Integration Agent  
**Related:** `docs/MQL5_EXECUTION_LAYER_DESIGN.md`, `HANDOFF_WATCHER_ARMED.md`, `PRODUCTION.md`, `docs/AUTONOMOUS_WORKFLOW_PIPELINE.md`

**EXECUTION PATH FINALIZATION (2026-05-28):** On Windows + running MT5 terminal, **pure Python (OrderManager + MT5Executor via ExecutionAgent with mql5_bridge_enabled=False)** is the RECOMMENDED PRIMARY path for full stack 100%. 
- Direct python-metatrader5 interaction is viable, simpler, and more reliable (no file polling, immediate telemetry, single-process control).
- MQL5 command bridge (rich JSON to ChainGambler EA) remains fully supported as OPTIONAL high-performance native path (set MQL5_BRIDGE_ENABLED=1).
- One-command force: `$env:MQL5_BRIDGE_ENABLED="0"` (pure primary, default for paper harness / supervisor / Windows) or `"1"` (MQL5 bridge).
- All rich TradeDecision features (risk-% sizing, ladders, advanced trailing incl. STEP_TRAIL/BREAKEVEN, partials, full FLAT close) hardened in pure path + OrderManager registration + telemetry to Decision PPO via execution_reports + execution_feedback.jsonl + runtime/agent_status/decision_ppo_execution_live.json .
- Paper harness, handoff_watcher, vps_agi_supervisor default to pure primary. End-to-end tested clean. Ambiguity removed.

---

## 1. Motivation & Goals

Previous state mixed high-level policy decisions (PPO action vectors or simple intents) directly with low-level order management. This created:

- Fragile coupling (PPO changes broke execution, and vice-versa)
- Difficulty expressing professional execution logic (risk-% sizing, multi-rung TP ladders with partial closes, sophisticated trailing, time-based + event exits)
- Poor observability for the Decision PPO to learn from real fills, slippage, partials, and trailing adjustments
- Inconsistent behavior between Python paper paths and MQL5 native

**Target separation (achieved):**

```
Decision Layer (high-level policy)
    └── Decision PPO / Ensemble / Hybrid Brain
          outputs: TradeDecision (rich, structured, serializable)

Execution Layer (reliable, resilient order mgmt + backend abstraction)
    └── ExecutionAgent (mql5_bridge_enabled resolved via env MQL5_BRIDGE_ENABLED or explicit; default primary pure on Windows)
          ├── Pure Python PRIMARY (recommended on Windows direct MT5): OrderManager + MT5Executor (full rich TradeDecision: risk sizing, ladders, advanced trailing, telemetry to PPO)
          └── Optional MQL5 bridge (high-perf): writes JSON command + .ready for ChainGambler EA native CTrade mgmt (set MQL5_BRIDGE_ENABLED=1)

Bidirectional Telemetry (for PPO learning + audit)
    └── execution_feedback.jsonl + runtime/execution_reports/*.json
          (fills, partial closes %, trailing SL moves, realized PnL attribution keyed by decision_id)
```

Zero-touch arming via existing `handoff_watcher` + `vps_agi_supervisor` + `promote_candidate_to_paper.py` + `deploy_mql5_chain_gambler.ps1`.

**Invariants (never broken):**
- All legacy simple `intent` dict paths continue to work unchanged.
- ShadowMode + pure NN inference paths in MQL5 remain fully operational side-by-side.
- Paper harness, gates, risk supervisors, and router are untouched in behavior unless explicitly opted into the new path via `AGI_EXECUTION_TYPE=decision_ppo` (now the promoted default).

---

## 2. TradeDecision Spec (The Contract)

Defined in `Python/execution/trade_decision.py` (dataclass + full serialization + `from_simple_intent` adapter + light validator + JSON Schema).

**Core fields (rich but practical):**

- **Identity**: `decision_id`, `timestamp`, `source`, `model_version`, `confidence`
- **Intent**: `symbol`, `side` (LONG/SHORT/FLAT), `size: SizeSpec`
  - `SizeSpec`: `mode` (fixed_lots | risk_pct_equity | risk_pct_balance | kelly_fraction) + `value`
- **Entry**: `EntrySpec` (market/limit/stop + slippage tolerance)
- **Exits**:
  - `sl: ExitSpec`, `tp: ExitSpec` (type: fixed_pips | atr_mult | r_multiple | price_absolute | ladder)
  - `tp_ladder: PartialCloseLadder` (list of `TPLadderLevel` {level, close_pct, type} + of_original_size + runner_after_last)
- **Management**:
  - `trailing: TrailingSpec` (type: none | breakeven_only | fixed_pips | atr | step_trail | chandelier + trigger/distance/step/atr_period)
  - `breakeven_after_r`
  - `time_exit: TimeExitSpec` (max_hold_* , session/eod/news close flags, force_close_before) — now surfaced live in TUI (monitor_tui.py) + React DecisionExecutionPanel; analyzer insights also visible.
- **Policy hints**: `full_close_on_opposite`, `max_concurrent_positions`, `tags`, `risk_overrides`

**Production Safety Hardening for Timing-Aware Rich Decisions (v2026-05-28+):**
- Position sizing caps: ExecutionAgent._compute_lots_from_size_spec respects SizeSpec.max_lots_cap + RiskSupervisor.max_lots (global + per-decision).
- Daily loss limits: RiskEngine/Supervisor + harness now timing-aware via is_high_impact_news_window + should_respect_time_exit_for_loss_limit; defers non-critical emergency if active TradeDecision TimeExitSpec.close_before_high_impact_news and in window (lets managed close handle to avoid slippage).
- Emergency flatten: force_flatten_all (and harness rollback) honors open/news windows — defers non-critical (rollback/loss/kill always force); writes awareness command to MQL5 bridge; integrates EventGuard heuristics + fallback.
- Canary/supervisor extensions: DemoCanary + CanaryMonitor track open-window vs news-avoidance PnL/metrics; rollback triggers on degradation (high news-prox ratio or negative avoidance score).
- Regression + tests: Added in test_risk_supervisor.py, test_order_manager.py; rollback wired end-to-end.
- Runbook: Always prefer rich path for Decision PPO. Monitor runtime/agent_status/decision_ppo_execution_live.json + canary artifacts for timing fields. See production_hardening_timing_agent.json for status. Supervisor (vps_agi_supervisor.ps1) and harness have inline runbook comments. Goal: 100% unsupervised live safe with timing-aware Execution.
- **Execution metadata**: `magic`, `comment`

**Serialization**:
- `to_dict()` / `to_json()` / `from_dict()` / `from_json()` — clean enums as strings, perfect for file bridge to MQL5.
- `TRADE_DECISION_JSON_SCHEMA` (documented in the module).

**Legacy adapter** (the key to zero-breakage):
```python
td = TradeDecision.from_simple_intent({"symbol": "BTCUSDm", "side": "BUY", "size": 0.01, "sl": 123.4, ...})
```

Convenience: `make_risk_based_decision(...)`.

---

## 3. ExecutionAgent (Python Side)

`Python/execution/execution_agent.py`

**Responsibilities**:
- Accept `TradeDecision` (or legacy dict via adapter).
- Run through existing `GateEngine` + risk layers (normalized intent).
- **Preferred dispatch**: Write structured command JSON + `.ready` marker to `runtime/mql5_commands/` (or Common/Files/trade_decisions in live).
- **Rich Python fallback**: Translate to `OrderManager` (partials, scale-outs already implemented) + `MT5Executor` or `ExecutorRouter`.
- Maintain active decision registry.
- `update_from_execution_telemetry(decision_id, telemetry)` — the observation hook for PPO.
- Persistent reports:
  - `logs/execution_feedback.jsonl` (event stream: submitted, dispatched_mql5, filled, partial, trailing_update, forced_close, ...)
  - `runtime/execution_reports/<decision_id>.json` (latest state snapshot)
- `manage_active_positions()` hook (periodic call from harness/autonomy).
- `close_decision(...)` for policy-driven full exits.

**Singleton helper**: `get_default_execution_agent()`.

**Exported** via `Python/execution/__init__.py`.

The `ExecutorRouter.submit()` was also lightly extended to accept `TradeDecision` (normalizes for old executors).

---

## 4. MQL5 ChainGambler Command Bridge (Preferred Live Path)

Enhanced `mql5/Experts/ChainGambler/ChainGambler_Executor.mq5` (v0.30+).

**New inputs (additive)**:
- `ExecutionCommandMode` (default false — pure inference/Shadow unchanged)
- `CommandDir`, `UseCommonForCommands`, `CommandPollSeconds`
- `EnableRichMgmt`, `MaxRichMgmtPositions`

**Behavior when armed**:
- `OnTickExecutionBridge()` (called from `OnTick`) throttled-polls for `*.ready` + matching `.json`.
- Lightweight JSON field extractors (no external deps).
- `ExecuteRichDecision()` — entry with SL/TP + skeleton for ladder partials + status write-back to `Common/Files/execution_status/<decision_id>.json`.
- Future expansion point clearly marked for full per-ticket state machine (cached decision JSON + position comment tagging with `decision_id`).

**Status back-channel**:
MQL5 writes machine-readable JSON that Python `ExecutionAgent.update_from...` (or dedicated monitor) can consume for perfect observability.

**Deployment**:
- Existing `scripts/deploy_mql5_chain_gambler.ps1` + supervisor/handoff already copy the EA.
- After deploy: in MT5 MetaEditor, set the new inputs on the EA and attach (can run in parallel with ShadowMode=true on another chart for validation).

---

## 5. Paper Harness & Fallback Integration

`scripts/paper_mt5_execution_harness.py` is pre-wired (and further reinforced):
- `execution_type=decision_ppo` (default for promoted candidates via `paper_harness_start.json`)
- Instantiates `ExecutionAgent` (MQL5 bridge disabled for paper safety)
- Uses `TradeDecision.from_simple_intent(...)` + `submit_decision()`
- Calls `update_from_execution_telemetry()`
- Rollback path also prefers the agent
- `AGI_DECISION_EXECUTION=0` forces pure legacy router for regression testing.

All existing `AGI_PAPER_FIXED_LOT`, daily loss caps, canary, retrain triggers continue to function identically.

---

## 6. Zero-Touch Arming Flow (Handoff Watcher + Supervisor)

1. Good post-fix candidate appears (alignment_fix_applied + scorecard gates).
2. `handoff_watcher.py` (persistent) or `vps_agi_supervisor.ps1` (env `AGI_AUTO_PROMOTE_CANDIDATE=1`) invokes promoter.
3. Promoter runs gates + `--auto-launch` + canary → starts `paper_mt5_execution_harness.py` (decision_ppo mode) + triggers MQL5 deploy.
4. Watcher emits `runtime/decision_execution_armed.json` (TUI-visible) + `PIPELINE_DECISIONS.jsonl` entries.
5. `last_handoff.json` enriched with execution layer details.
6. In live: deploy script + EA attach with `ExecutionCommandMode=true` gives native MQL5 execution of the exact same `TradeDecision` objects.

Env gates keep everything opt-in and safe (`AGI_AUTO_MQL5_DEPLOY`, `AGI_DECISION_EXECUTION`, etc.).

---

## 7. Observability & Learning Loop Closure

Primary signals for the Decision PPO:
- `logs/execution_feedback.jsonl`
- `runtime/execution_reports/`
- `logs/trade_journal.jsonl` (still written by paper executor)
- Per-decision `decision_id` correlation in all artifacts

Higher layers (RetrainingTrigger, model_evaluator, champion_cycle) can now attribute outcomes to specific structured decisions (e.g., "ladder with 50% at 1R + ATR trailing outperformed fixed TP").

---

## 8. File Inventory (Key Deliverables)

**Python (new / enhanced)**
- `Python/execution/trade_decision.py` — full spec + adapters + schema
- `Python/execution/execution_agent.py` — the execution layer core
- `Python/execution/__init__.py`, `executor_router.py` — exports + compat

**MQL5**
- `mql5/Experts/ChainGambler/ChainGambler_Executor.mq5` — v0.30 command bridge + rich skeleton
- `mql5/Experts/ChainGambler/README.md` — updated with v0.3+ section

**Scripts / Harness**
- `scripts/handoff_watcher.py` — arming marker + decision_ppo awareness
- `scripts/paper_mt5_execution_harness.py` — fully wired (pre-existing + reinforced)
- `scripts/deploy_mql5_chain_gambler.ps1`, promoter, supervisor — inherit via existing flows + README updates

**Docs**
- `docs/DECISION_EXECUTION_ARCHITECTURE.md` (this file)
- Runtime markers: `runtime/decision_execution_armed.json`, `runtime/execution_reports/`

**Logs / Telemetry**
- `logs/execution_feedback.jsonl`
- `runtime/agent_status/` (new entries created on first arming)
- `logs/*_timing_insights.json` (from Decision PPO post-training analyzer runs)

**Observability & Multi-Model Timing Integration (2026-05-28, Observability Timing Agent)**
- TUI (scripts/monitor_tui.py) + React DecisionExecutionPanel now show live TimeExitSpec (news/opens/session flags) + ExecutionAgent telemetry + analyzer insights (/api/timing/insights).
- Dreamer world model training (via feature_pipeline.py build_env_feature_matrix) now includes session_london/ny, major_open_window, news_proximity etc in obs → world model learns timing dynamics.
- Rainforest regime detector (extract_features) now conditions regimes on the same timing features → full ensemble (Decision PPO + Dreamer + Rainforest) market-structure aware around opens/news.
- Timing analyzer (Python/analysis/trade_timing_analyzer.py) outputs visible in UIs for profitable timing feedback loops.
- Updated: feature counts, panels, docs, agent_status.

---

## 9. Usage Examples

**From a Decision PPO head (future)**
```python
from Python.execution import ExecutionAgent, TradeDecision, make_risk_based_decision, Side

agent = ExecutionAgent(...)
td = make_risk_based_decision("XAUUSDm", Side.LONG, risk_pct=1.2, atr_sl_mult=2.0, tp_r=3.0,
                              trailing_type=TrailingType.ATR)
td.tp_ladder = ...  # rich ladder
report = agent.submit_decision(td)
# Later: agent.update_from_execution_telemetry(report.decision_id, telemetry_from_journal_or_mql5)
```

**Legacy path (unchanged)**
```python
router.submit({"symbol": "...", "side": "BUY", "size": 0.01, "sl": ..., "tp": ...})
# or harness with AGI_EXECUTION_TYPE=simple_action
```

**MQL5 (after deploy)**
Attach EA with `ExecutionCommandMode=true`, `EnableRichMgmt=true`. Python ExecutionAgent writes commands → native execution + status back.

---

## 10. Safety, Rollback, & Compatibility Matrix

- **Gates & Risk**: Never bypassed.
- **Flatten/Rollback**: ExecutionAgent + harness have explicit paths; MQL5 EA can be removed from chart instantly.
- **Paper vs Live**: Bridge disabled by default in harness; explicit in live.
- **Regression**: `AGI_DECISION_EXECUTION=0` or `execution_type=simple_action` restores 100% old behavior.
- **MQL5**: New mode off by default (`ExecutionCommandMode=false`).

All changes are **strictly additive**.

---

## 11. Future Hardening (Roadmap Notes)

- Full native MQL5 ladder/trailing/time-exit state machine with persistent per-decision JSON cache.
- ATR/risk-pct lot sizing resolution inside MQL5 using `OrderCalcMargin` + symbol profiles.
- Dedicated status poller thread in ExecutionAgent for MQL5 reports.
- Direct `TradeDecision` output head in PPO training (instead of raw Box(6,)).
- TUI / supervisor checklist item: "Decision+Execution armed".
- Promotion gate requiring clean execution telemetry volume.

## 12. Rich Execution Promotion Gates (Implemented by Rich Execution Gates Agent)

**Goal:** Candidates using Decision PPO (execution_type=decision_ppo) are now evaluated on the *actual quality of their rich TradeDecisions*, not merely aggregate P&L / drawdown / sharpe.

**Implementation locations:**
- `Python/registry/promotion_gates.py` — `RichExecutionAnalyzer` + `_run_rich_execution_gates()` called inside `evaluate()`. New thresholds in DEFAULT_GATES.
- `Python/model_evaluator.py` — Auto-enriches val_report + training_metrics with execution_type + rich_execution_metrics for decision_ppo candidates.
- `scripts/promote_candidate_to_paper.py` — Explicit passing + reinforcement of execution_type=decision_ppo in every audit, meta file (paper_harness_start.json, handoff_status), MQL5 guidance, and gates_result. Rich metrics attached to promotion records.

**Metrics produced by RichExecutionAnalyzer (from ExecutionAgent telemetry):**
- `execution_quality_score` (composite fidelity)
- `trailing_success_rate` (favorable moves from any TrailingSpec: breakeven_only / atr / step_trail etc.)
- `partials_utilization_rate` + `realized_r_improvement_avg` (ladder performance via PartialCloseLadder + TPLadderLevel)
- `risk_sizing_adherence_rate` (SizeSpec risk_pct_* vs actual fills)
- `avg_fill_latency_sec`, `error_blocked_rate`, `rich_decision_count` (auto-detects rich features in decision_summary)

**Gate behavior:**
- Rich gates ONLY apply when `execution_type=decision_ppo` (or detected rich TradeDecision usage via size_mode / trailing_type / ladders).
- Legacy `simple_action` candidates are untouched (no new failure modes).
- Thresholds (configurable via PromotionGates(config)): min_execution_quality=0.60, min_trailing_success_rate=0.35, min_risk_sizing_adherence=0.80, min_decision_success_rate=0.85.
- When telemetry is sparse (early paper runs), conservative defaults + notes prevent false failures; volume from real harness runs feeds subsequent gate evaluations (re-promote, champion_cycle, TUI review).

**Telemetry sources (primary contract):**
- `logs/execution_feedback.jsonl` (event stream: decision_executed_python, decision_dispatched_mql5, execution_update, trailing_updates, partials, realized_pnl...)
- `runtime/execution_reports/<decision_id>.json` (per-decision snapshots with fills, current_sl/tp, backend)

**End-to-end flow for rich scoring:**
1. Promoter detects post-fix candidate → runs gates (now rich-aware) → writes paper_harness_start.json with execution_type=decision_ppo + rich_gates=true.
2. Harness (paper or demo) uses ExecutionAgent.submit_decision(TradeDecision...) → populates telemetry.
3. After sufficient paper runtime: re-evaluate gates (promoter, TUI, or champion_cycle) → rich metrics now populated → rich gates can pass/fail based on execution fidelity of the *structured decisions*.
4. Full audit trail in post_training_promotion_decisions.jsonl + PIPELINE_DECISIONS.jsonl + candidate scorecard enrichment.

**Status marker:** `runtime/agent_status/rich_gates_agent.json` (written by this agent; visible to swarm/TUI).

This closes the loop so Decision PPO is promoted on the merit of its sophisticated execution plans (lot sizing discipline, smart exits, partial scaling, trailing intelligence), exactly as intended by the rich Decision + Execution architecture.

---

**This architecture delivers the requested clean separation, rich decision support, MQL5-preferred execution, full reporting for learning, and seamless zero-touch integration with the existing autonomous handoff + supervisor machinery — without any breakage to prior paths.**

All files are in the repo at the paths listed. The system is ready for the next champion candidate.