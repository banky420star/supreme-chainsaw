# TUI Feature Parity Plan — React UI ↔ monitor_tui.py
**Date**: 2026-05-28  
**Agent**: TUI Feature Parity Agent (this workstream)  
**Goal**: Make `scripts/monitor_tui.py` (Rich + stdlib) a first-class terminal counterpart to the comprehensive React production UI in `frontend/src/` for monitoring the live v5 (and future champion) runs. Prioritize production usefulness for VPS supervision alongside vps_agi_supervisor.

## 1. React UI Feature Inventory (from deep source read of App.tsx, types.ts, api.ts, panels)
**Navigation (App.tsx tabs)**: trades, model_brains, pipeline, training, registry, promotion_gates, demo_canary, trade_coroner, patterns, perpetual, agents, evidence, settings, overview (System Truth), safety (Safety Lock), legacy_dashboard.

**Core Data Layer (api.ts + types.ts)**:
- `/api/status` (WS + poll): full StatusPayload (account equity/balance, training visual/queues/lanes/pipeline_summary/cycle_heartbeat/pattern_library, risk/halt, system, tests, registry_summary, etc.).
- Dedicated: `/api/pipeline/stages` (20-stage ordered cards: mt5_data...retraining_trigger w/ status/last_run/artifact/blockers/metrics), `/api/model_brains` (LSTM/Rainforest/Dreamer/PPO detailed cards w/ probs, regimes, feature_importance, ruin prob, timesteps, promotion), `/api/training/lanes`, `/api/registry` (ModelBundle[] table: bundle_id, symbol, status, components, backtest/wf/canary, promotion_decision), `/api/promotion_gates` (PromotionGateItem[] w/ gate/required/actual/passed/pending), `/api/demo_canary`, `/api/trades/coroner` (TradeCoronerCluster[] + totals), `/api/agents/status` (AgentOperationalStatus: id/name/status/heartbeat/current_task/last_artifact/error_count), `/api/safety` (SafetyState: real_money_locked + gates[]), `/api/evidence` (EvidenceArtifact[] table), `/api/equity_curve?window=...` (EquityPoint[] + summary: start/current/peak/maxDD), `/api/trades` + summary (Trade[] w/ ticket/symbol/side/PnL/outcome/model + KPIs), `/api/economic_calendar`, fetchPPODiagnostics, LSTMExplanations, etc.
- Client-side: EquityChart.tsx (full SVG: smoothed equity line + area, dashed balance, red drawdown fills, hover tooltip/crosshair, window toggles 30d/90d/all, summary stats, ResizeObserver). TradesPanel embeds simpler SVG equity + calendar badges + paginated table.

**Key Panels (detailed behaviors)**:
- **TradesPanel**: KPI grid (Total/Wins/Losses/WR/PnL/PF), EquityCurve embed (summary + chart), Economic Calendar (importance color badges), trades table (cols: Ticket/Symbol/Side/Vol/Open/Close/PnL/Outcome/Model), pagination.
- **ModelBrainsPanel**: 4 cards (LSTM: model_id/lookback/features/p_up/p_down/p_flat/expected_return/conf/calib/influence badge; Rainforest: regime/conf/lift/allowed(blocked) chips + sorted top feature_importance list; Dreamer: stub warning + rollouts/horizon/reward/DD/ruin/used_for_decisions; PPO: training_status/timesteps/reward_ver/action_bias/promotion_status). Status badges via brainTone.
- **PipelinePanel**: Responsive grid of 19 STAGE_ORDER cards (left border color by tone, name, last, artifact, blockers list, metrics chips). Polls /api/pipeline/stages q15s. TruthBadge.
- **TrainingPanel**: Parallel lanes (badges + TrainingLaneCard grid), 3 PipelineCard (LSTM/PPO/Dreamer: state dot/progress bar/symbol/fail), Queue Snapshot (StageQueueCard tables), Symbol Queue table (symbol + lstm/ppo/dreamer states), Controls (buttons via /api/control), Cycle Heartbeat. Uses status.training.* + visual.*.
- **RegistryPanel**: Full-width table (Bundle ID truncated / Symbol / TF / Status badge / Data / LSTM/RF/Dreamer/PPO / Backtest/WF/Canary nums / Decision badge). Polls q15s.
- **PromotionGatesPanel**: Summary badge (X/Y PASSED + text), vertical list of gate rows (checkmark/× circle, gate name, PENDING chip, monospace required|actual). Color by passed.
- **TradeCoronerPanel**: KPI row (Mistakes/Reviewed/Clusters nums), cluster cards (border color by retrain_eligible, cluster_id, count, root_cause, affected_symbols, recommended_experiment, TruthBadge).
- **SafetyPanel**: Locked badge (pulse if locked + reasons), Safety Gates list (✓/×, name, required|actual monospace).
- **EvidenceLockerPanel**: Table (Name / Created / Status badge / Linked Model / Path). artifactTone for status.
- **AgentsPanel**: Summary badges (N ONLINE / M ERROR), responsive grid of agent cards (name + id, status badge, Task/Heartbeat/Last Artifact/Errors w/ color).
- **OverviewPanel**: Multi "truth" cards (Mode/Safety/Account/Data/Models/Validation/Tests + incidents/logs) using header + status fields + truthTone.
- Others: PPODiagPanel (PPO details), Patterns/Perpetual/DemoCanary/Settings use status + side fetches.

**Live Behavior**: WS on /ws/status for status; 10s poll fallback + 15s side data (patterns/perf/ppo/lanes/scenarios/calendar/header). Loading spinners, TruthBadge, color coding (green=good, red=halt/fail, cyan=active, amber=warning).

**Production Focus**: v5 run monitoring (training progress, handoff, promotion readiness, safety/lock, evidence, coroner for failures, equity/PnL from execution, swarm of agents).

## 2. Current TUI Strengths (monitor_tui.py + swarm_status.py)
- **Autonomous Pipeline Observer** (get_autonomous_pipeline_status): Rich cards/columns/progress for data/training/execution stages, v5+ live KL/loss/rew/approx_kl/trend from _parse_live_training_signals (robust logs + training_health.json).
- **Training Deep Dive** (get_training_deep_dive + live overlay): Last candidate, alignment/post-fix status, 50k attempts, KL explosions, recent steps/symbol, recommendation (promotion/harness), live_training block.
- **Swarm Status** (render_swarm_panel + get_swarm_agents via swarm_status): Table of name/workstream/phase/focus/blockers/status/progress/updated. Sources: runtime/agent_status/*.json (direct drop or report_status) + Grok bridge (--sync-grok pulls ~/.grok sessions/subagents for 30+ specialized agents). High visibility for parallel work.
- **Decisions + Audit**: get_recent_pipeline_decisions_panel (PIPELINE_DECISIONS.jsonl table: Time/Type/Actor/Decision/Candidate/Reason), get_loop_closure_panel (score from Python/pipeline_audit).
- **Handoff/Post-Candidate**: get_post_candidate_handoff_status (last_handoff.json + flags + promoter audit + mql5_shadow + harness), promotion_checklist (gates proxy + OOS/per-sym + paper/MQL5/rollback/RETRAIN).
- **Health/Infra**: MT5/ps/supervisor/disk/python processes, supervisor logs tail, top_bar with rich signals.
- **Live**: rich.Live (or --once snapshot). Pure stdlib+rich. Defensive (never crashes).
- **Data Layer**: Direct FS (logs/training_health.json, robust_v5_*.log tails for PPO, agent_status, PIPELINE_DECISIONS, handoff_profile, flags); imports from Python/pipeline_audit.

**Gaps vs React (for parity)**:
- No equity curve viz (text only in top; no ASCII/spark/summary from account_history).
- No trades table/KPIs/outcomes/models + calendar.
- Pipeline observer high-level only (no exact 19-20 stage grid w/ artifact/last/blockers/metrics like /api/pipeline/stages).
- No Model Brains 4-card detailed telemetry (LSTM probs/feat, RF importance chips/list, Dreamer ruin, PPO promotion).
- Promotion: text checklist only (no exact gate list w/ required/actual/passed like /api/promotion_gates).
- No Safety gates list + lock state mirroring /api/safety.
- No Evidence table.
- No Trade Coroner clusters (only indirect decisions/incidents).
- No Registry bundles table.
- Agents swarm excellent but fields not fully aligned to AgentOperationalStatus (add error_count, explicit current_task/heartbeat/last_artifact support).
- Training: strong v5 signals but missing parallel lanes/queues/symbol rows from status.training.*.
- No direct Overview/System Truth cards (mode/safety/account/tests/models/validation).
- Equity windows/hover not replicable exactly but ASCII + recent table sufficient.
- Some panels poll dedicated FS endpoints; TUI must stay file-centric for standalone robustness (no server dep).

## 3. Parity Design (Rich Equivalents)
**Principles**:
- Pure Rich (Table, Panel, Group, Columns, Progress/BarColumn, Text, console, Live) + stdlib (json, pathlib, datetime, re, os, subprocess for health).
- Live-updating: Existing rich.Live refresh (target 4-7s). File mtimes + in-memory cache for cheap polls.
- Standalone first: Direct FS reads (account_history.jsonl, training_health, logs/*.json, models/*, artifacts/*, runtime/*). Optional graceful fallback to local /api/* if server up (requests? avoid new dep; use urllib stdlib or skip).
- v5 focus: Surface handoff_profile, live PPO signals, current BTCUSDm run, coroner from live_incidents, promotion readiness.
- Production usefulness: Quick "at-a-glance" for supervisor (halt? training stuck? candidate ready? equity curve healthy? coroner clusters? gates blocking? swarm blockers? evidence fresh?).
- Layout: Vertical Group stack in build_dashboard (hero Pipeline + Training Deep + new sections + Swarm + Decisions + Handoff + Health). Use Columns for card grids inside panels. Keep --once working.
- Unicode-safe: Extend _safe_text for any new chars; ASCII fallbacks for curves (block chars ▁▂▃▄▅▆▇█ or simple |-/).
- Error resilience: Every new renderer wrapped try/except, returns safe Panel on failure.
- No new deps.

**New/Enhanced Panels (add to build_dashboard Group + dedicated fns)**:
1. **Equity & Trades Summary** (new, high priority for v5 exec visibility):
   - Parse last N points from logs/account_history.jsonl (ts, equity, balance, drawdown~profit calc).
   - Summary KPIs row (start/peak/current equity, max DD, total points) — match React.
   - ASCII sparkline: unicode blocks or Rich bar chars for equity trend (last 30-60 pts, scaled).
   - Recent points mini-table (ts | equity | bal | Δ).
   - Recent trades/KPIs: Scan profitability.jsonl or incidents or account for PnL outcomes; or simple from history (open_positions changes). Table: time/symbol/side/pnl/outcome if data available. Fallback to "use /trades when server live".
   - Calendar summary: badges from status or hardcode recent high-impact.
   - Rich: Table + Text spark + Panel.

2. **Model Brains** (new):
   - 4 sub-Panels or Columns cards.
   - Data: Direct scan models/per_symbol/*meta.json (LSTM), models/rainforest/*.pkl mtime + rf_detector equiv (or parse logs), models/ppo/*, handoff_profile for PPO reward ver.
   - Content: Status badge (tone fn), key fields exactly as types (p_up etc, feature_importance top-6 sorted list as table rows or chips, allowed/blocked, ruin prob, timesteps, promotion). Mirror brainTone.
   - Source equiv to _get_model_registry_status + api_model_brains.

3. **Enhanced Pipeline Stages** (enhance get_autonomous... or new fn):
   - Full grid/Columns of 19-20 cards (copy STAGE_ORDER + names from React or api_server).
   - For each: compute status (from progress files, mtimes of artifacts, tests, validation, data provenance, active registry, mt5).
   - Show: name, last_run (mtime or progress ts), artifact (basename), blockers (list), metrics (chips).
   - Tone borders/colors via Rich style. Use same logic as api_pipeline_stages (inline or import if safe).
   - Hero in observer.

4. **Training Lanes & Queues** (enhance Deep Dive + new sub):
   - Parallel lanes badges + simple table (from training_health or log parse + handoff_profile).
   - Symbol stage rows table.
   - Queue cards (LSTM/PPO/Dreamer state/progress).
   - Keep rich live PPO (KL etc) + add cycle_heartbeat.

5. **Registry — Model Bundles** (new table):
   - Scan models/registry/active.json + candidates/* / per_symbol + champion dir.
   - Table cols: ID (trunc), Symbol, TF, Status (badge), Data, LSTM/RF/Dreamer/PPO, Backtest/WF/Canary, Decision (badge).
   - Match bundleTone + fmtNum.

6. **Promotion Gates** (new/enhanced):
   - Summary passed/total badge + explanatory text.
   - Vertical list or table: ✓/✕, gate, pending chip, required | actual (monospace).
   - Extend get_promotion_checklist to return full gate items (or direct compute matching api_promotion_gates using tests/validation/progress/mt5/rf).
   - Integrate handoff_profile gates.

7. **Trade Coroner** (new):
   - KPI row (mistakes/reviewed/clusters).
   - Cluster cards (from live_incidents.json filter severity + artifacts/trade_coroner/*.json).
   - Fields: id, count, root_cause, symbols (csv), experiment, retrain badge.
   - Tone by retraining_eligible.

8. **Safety Lock** (new):
   - Big badge (REAL MONEY LOCKED + pulse style via color + reasons list).
   - Gates list: ✓/✕ name + required|actual.
   - Pull from status equiv (risk in training_health or handoff or direct _resolve_system_mode logic), tests, rf trained, ppo progress. Or parse runtime flags.

9. **Evidence Locker** (new table):
   - Scan artifacts/* (model dirs + dated jsons), models/* subdirs (lstm/ppo/rainforest/dreamer/registry), logs/*.json recent.
   - Table: Name, Created (mtime), Status (tone: valid/pending/stale/failed via size/children check), Linked (from filename or json), Path (rel).
   - Match artifactTone + _validate_artifact logic from api_evidence.

10. **Agents / Swarm** (enhance existing):
    - Keep render_swarm_panel as-is (already best-in-class).
    - Extend swarm_status.py report/get to support optional fields (error_count=0, current_task=focus, heartbeat=last_updated, last_artifact="").
    - Add summary counts (online/error) like React.
    - Bridge more operational data from handoff_watcher_status.json etc.

**Other**:
- System Truth / Overview: Add compact cards row (Mode | Safety | Account | Models | Tests | Validation) using existing handoff + status parses.
- DemoCanary: Surface in Promotion/Handoff (metrics from harness logs).
- PPODiag: Already covered in Deep Dive + live signals.
- Patterns/Perpetual: Optional (low prio; mention in Training or new if time).

**ASCII Equity Viz** (no SVG):
- Simple sparkline fn: scale values, map to '▁▂▃▄▅▆▇█' blocks (8 levels), color last segment green/red by delta.
- Or Rich BarColumn mini for trend + last 5 values table.
- Full summary + maxDD color.
- Fallback table if no points.

**Implementation Order (in code edits)**:
1. Add parsers (get_equity_from_history, get_model_brain_data, get_registry_bundles, compute_promotion_gates, get_coroner_clusters, get_safety_state, get_evidence_artifacts, get_pipeline_stages_from_fs).
2. Add tone/badge helpers (_safe_text extended).
3. Add render_*_panel() fns (defensive, return Panel).
4. Integrate into build_dashboard (logical order: top status, Pipeline hero, Equity/Trades, ModelBrains, Training enhanced, Registry, Promotion, Coroner, Safety, Evidence, Swarm (existing), Decisions, Handoff, Health).
5. Minor swarm_status.py update for field parity (add keys, backward compat).
6. Update docstring + usage notes.
7. Write agent_status JSON for this agent.
8. Test (python -c "from scripts.monitor_tui import build_dashboard; print(build_dashboard(once=True))" or run script).

**Data Sources Priority (TUI)**:
- Primary: Direct FS (account_history.jsonl for equity/trades proxy; training_health + v5 logs for PPO/Training; live_incidents + trade_coroner artifacts; models/registry/* + per_symbol meta; runtime/*.json + flags + handoff_profile; artifacts/*; logs/PIPELINE_*.jsonl + pytest etc).
- Secondary: Replicate small logic from Python/api_server.py (e.g., _get_*, stage status) or import where safe (no side effects).
- Optional: urllib to http://localhost:PORT/api/* if server running (detect via health).
- v5 specific: runtime/v5_btcusd_50k_handoff_profile.json for profile, run_id, paper_profile, handoff_readiness.

**Risks/Mitigations**:
- File format drift: Defensive json loads + try/except everywhere.
- Perf (large jsonl): Tail only (last 200 lines or recent mtime filter).
- Windows console: _safe_text always.
- No rich: Already handled at top.
- Long render: Cache parsed data 3-5s.

**Deliverables**:
- logs/tui_parity_plan.md (this).
- Updated scripts/monitor_tui.py (clear # PARITY comments, new fns).
- (opt) scripts/swarm_status.py minor.
- runtime/agent_status/tui_feature_parity_agent_*.json (report via swarm_status.py or direct).
- logs/tui_parity_update_20260528.md (summary + snippets + how to run + parity achieved).

**Success Criteria**: TUI --once or live shows equivalent visibility to all major React tabs for v5 run (equity curve shape, trades summary, full pipeline stages, brains details, gates, coroner clusters, safety, evidence, registry, agents swarm, training rich). Operator can answer "is champion promotable?" / "why halted?" / "training health?" / "swarm status?" at a glance without browser.

## 4. Next Steps (this agent execution)
- Write this plan (done).
- Implement parsers + renders in monitor_tui (priority: equity/trades + pipeline stages + promotion/safety/coroners first for v5 exec loop).
- Agent status drop.
- Final md + verification run.
- Prioritize production: focus on v5 handoff/profile integration + coroner from live incidents (canary rollbacks visible in sample).

This plan ensures the TUI becomes the "terminal mission control" matching React's production truth dashboard.
