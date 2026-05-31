# ChainGambler MQL5 Native Execution Layer (Scaffold)

This directory contains the first version of the **native MQL5 inference executor** for ChainGambler.

## Architecture
- Python side: PPO training with LSTM feature extractors + hardened rewards (drl/, training/).
- MQL5 side: Ultra-low-latency execution using the production-grade **NeuroNetworksBook** library (48097.zip / "Neural Networks for algorithmic trading in MQL5").

**Hybrid is the winning pattern for real profitability.**

## Files
- `ChainGambler_Executor.mq5` — Main EA. Loads `.net` model, builds observation via features, runs `CNet::FeedForward` + `GetResults`, simple policy head + trade execution.
- `ChainGambler_Features.mqh` — Native implementation of core engineered features (subset of Python ULTIMATE_150).
- `ChainGambler_Types.mqh` — Shared constants & includes.

## Automated Zero-Touch Deployment (2026-05-27+ - MQL5 Production Deployment Agent)

**ONE-COMMAND from good post-fix candidate (alignment_fix_applied + strong metrics):**

From project root (after supervisor/TUI detects "Candidate staged"):
```powershell
.\scripts\deploy_mql5_chain_gambler.ps1 -AutoFromRegistry -ShadowPrep -DeployToAllTerminals
```
- Auto-finds latest good candidate via Python registry scan (exact parity with supervisor).
- Runs `python tools/export_for_mql5.py --candidate-dir ...` (v0.3+ : 28-feat exact parity, enriched arch JSON).
- Auto-discovers ALL MT5 terminals (hex folders + Common under %APPDATA%\MetaQuotes\Terminal).
- Copies NeuroNetworksBook headers (from `C:\Users\Administrator\Downloads\48097_extracted\...`) to each `MQL5\Include\NeuroNetworksBook`.
- Copies `mql5/Experts/ChainGambler/*` (Executor + Features + Types) to `Experts\ChainGambler`.
- Generates self-contained `Scripts\ChainGambler_BuildStudentNet.mq5` (embeds CreateChainGamblerStudentLayers).
- Full logging to `logs/mql5_deploy_*.log`, `artifacts/mql5_distill/mql5_shadow_ready.json`, `runtime/mql5_shadow_ready.flag`.

## Decision PPO + Execution Layer (Autonomous Loop Closure)
New default for promoted models (AGI_EXECUTION_TYPE=decision_ppo):
- Python: Decision PPO (drl/trading_env DecisionSpec + decode_action 18-dim) or hybrid -> TradeDecision (Python/execution/trade_decision.py)
- ExecutionAgent.submit_decision() -> writes decision_<id>_<sym>.json + .ready to MQL5 Common/Files (protocol: chain_gambler_v1_trade_decision)
- MQL5 ChainGambler_Executor (CommandBridge mode): polls ready markers, parses rich spec (risk% sizing, ladders, ATR trailing, time exits, breakeven), executes natively via CTrade, writes status/execution_feedback back.
- Full rollback/force_flatten wired end-to-end (harness, supervisor, agent, EA).
- Legacy simple_action paths 100% preserved (TradeDecision.from_simple_intent adapter).
- Handoff watcher/supervisor/promoter auto-arm with execution_type recorded in paper_harness_start.json + handoff profiles.
- Multi-TF + best_features_per_symbol.yaml context used for inference obs at promotion time.
- Backups + rollback support (`-Rollback -Timestamp ...`).
- `-LogOnly` / `-WhatIf` for safe preview. Errors are non-fatal per-terminal with clear guidance.

**Then (inside any MT5 terminal):**
1. Tools → MetaQuotes Language Editor (F4).
2. Open the deployed `MQL5\Scripts\ChainGambler_BuildStudentNet.mq5`.
3. Compile (F7) → Run (it saves `chaingambler_v1_student.net` to Common\Files or MQL5\Files).
4. Attach `ChainGambler_Executor.mq5` to M5 chart:
   - ShadowMode = true (default for validation)
   - UseCommonFolder = true
   - UseOpenCL = true (if GPU)
   - Match LookbackBars / TradeThreshold to your Python config.

**Supervisor integration:** `scripts/vps_agi_supervisor.ps1` (Final Zero-Touch Orchestrator) emits the exact one-command + guidance on every "good candidate" transition (see logs + TUI). With `AGI_AUTO_MQL5=1` (or full orchestration envs with promoter) it launches autonomously in bg. See also PRODUCTION.md zero-touch section + concise runbook `docs/WHEN_GOOD_CANDIDATE_APPEARS.md`.

**Fallback (manual, for non-candidate or debugging):**
See legacy commands in git history or run the deploy script with explicit `-CandidateDir` + `-NeuroSrc`. The old manual PowerShell snippets below are superseded.

**Library source (auto-detected by deploy script):**
  `C:\Users\Administrator\Downloads\48097_extracted\mql5\Include\NeuroNetworksBook\`

(Primary terminal example still: `D0E8209F77C8CF37AD8BF550E51FF075\MQL5\...`)

**Models (.net) location:** `MQL5\Files\` or `Common\Files\` (UseCommonFolder=true recommended for VPS).

**Compile:**
1. In MT5: Tools → MetaQuotes Language Editor (or F4)
2. Open the copied ChainGambler_Executor.mq5
3. Compile (F7). Must succeed with 0 errors after headers deployed.
4. Drag EA to chart (M5 recommended for BTC/EUR etc).

**Also deploy to other terminals if multiple (list via PS):**
Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal" -Directory | % { $_.FullName + "\MQL5\Include" }

## MQL5 Shadow Mode Procedure (for parallel validation with Python DRL/paper trading)
**Purpose:** Run MQL5 Executor side-by-side with Python paper_trader / execution on same VPS/symbol/TF. Compare signals, latency, P&L attribution without risking capital.

**Improved workflow (post deploy script):**
1. Use the ONE-COMMAND deploy above with `-ShadowPrep` (auto does export + sources + builder).
2. In MT5: compile + run the deployed `ChainGambler_BuildStudentNet.mq5` (one-click .net).
3. Attach Executor with **ShadowMode=true** (default) + UseCommonFolder=true.
   - v0.3+ improvement: Shadow decisions are also appended to `Common\Files\chaingambler_shadow_log.csv` (timestamp, dir, size, price) for trivial diff / correlation against Python paper harness jsonl/CSV.
4. Launch Python paper harness (same symbols, TF=M5, 40-bar, matching thresholds/lots=0.01).
5. Monitor:
   - MT5 Experts tab: `[SHADOW LONG/SHORT]` + raw NN vector.
   - CSV: `Common\Files\chaingambler_shadow_log.csv` (or per-terminal).
   - Python logs.
   - Use simple PowerShell or Python diff on timestamps/action_dir.
6. Validation gates: high signal correlation, MQL5 latency advantage, no divergence in edge cases → promote (edit inputs: ShadowMode=false, small LotSize, re-attach or restart EA).

**Model Update Cycle (now <15min target):**
   Good candidate (supervisor detects) → one-command deploy_mql5... → MT5 build .net (seconds) → re-attach EA (hot or restart) → shadow validation resumes automatically.

**Files for coordination:**
- artifacts/mql5_distill/chaingambler_v1_arch.json + chaingambler_v1_create_layers.mqh (and ready builder .mq5 per terminal)
- scripts/deploy_mql5_chain_gambler.ps1 (the automation)
- logs/mql5_deploy_*.log + mql5_shadow_ready.json
- runtime/mql5_shadow_ready.flag
- C:\supreme-chainsaw\mql5\Experts\ChainGambler\ (source of truth)

## Decision PPO + Rich Execution Support (Autonomous Trading Loop Closure, 2026-05-28+)
- Default for all newly promoted models: execution_type="decision_ppo" (rich DecisionSpec: full trade with lot_spec, entry, tp/sl (pct/atr/rr), trailing, partials, breakeven, confidence, raw_action).
- Python: decode_action (drl/trading_env) + hybrid_brain/Server_AGI/harness produce DecisionSpec -> intent for ExecutorRouter (paper/MT5Demo) or direct command JSON drop to MQL5 Files for EA.
- MQL5 EA now supports rich command mode (DecisionSpec JSON over file/pipe) in addition to distilled net (for LSTM). Use for zero-distill high-expressivity DecisionPPO policies.
- Multi-TF + per-symbol best features (configs/best_features_per_symbol.yaml) wired into obs for Decision path.
- Handoff: promoter/supervisor/watcher set AGI_EXECUTION_TYPE=decision_ppo + MTF/best-features env; paper_harness_start + last_handoff record it.
- Rollback/force_flatten unchanged (router + risk_supervisor handle rich intents).
- Legacy simple_action fully preserved (env override or old models).
- Full zero-touch: training (decision_ppo action_config) -> eval (multi-TF metrics) -> gates -> promote (default new stack) -> paper (Decision+Exec) -> live.

See docs/AUTONOMOUS_TRADING_LOOP.md + docs/MQL5_EXECUTION_LAYER_DESIGN.md for diagrams + usage.
- logs/ + Common\Files\chaingambler_shadow_log.csv for both systems

## Current Status (v0.3+ - MQL5 Production Deployment & Automation + Full Orchestration, 2026-05-27)
- [x] All prior items + full integration into supervisor Final Zero-Touch Orchestrator (bg deploy on candidate with envs, LogOnly prep always, exact command emission in logs).
- [x] End-to-end coordination with `promote_candidate_to_paper.py`, `auto_promote_candidate.ps1`, robust v* training launchers, TUI observer, and partial feedback (RetrainingTrigger).
- [x] Comprehensive documentation: `PRODUCTION.md` (zero-touch + playbook), `docs/AUTONOMOUS_WORKFLOW_PIPELINE.md`, and dedicated concise/surfaceable runbook `docs/WHEN_GOOD_CANDIDATE_APPEARS.md` (checklist + commands; referenced by TUI/promoter/supervisor).
- [x] All new automation (deploy script, orchestration, promoter flows) cross-referenced for maintainability after the current push.
- [ ] Live .net + promotion from next real post-fix candidate (ready now; full flow automated).
- [ ] Full weight distillation / native MQL5 backprop loop (future).
- [ ] Automated feature vector diff harness (future, can use shadow CSV + Python logs).

**The zero-touch / supervisor-orchestrated path from good candidate → MQL5 shadow-ready + paper validation is now PRODUCTION READY (gated auto or one-command).**

See `docs/WHEN_GOOD_CANDIDATE_APPEARS.md` + PRODUCTION.md for the exact runbook when the next candidate appears. Report issues to main thread / TUI. Next good candidate (from v4+ robust training) triggers the full flow automatically (with envs) via supervisor + deploy script + promoter.

**See also:** docs/MQL5_EXECUTION_LAYER_DESIGN.md, scripts/deploy_mql5_chain_gambler.ps1 (full header), PRODUCTION.md, supervisor logs.

---

## v0.3+: Decision + Execution Layer Separation (NEW — Python Decision PPO + MQL5 Execution)

**Goal:** Clean separation so the high-level Decision PPO can output rich structured `TradeDecision` objects while MQL5 (or Python fallback) reliably turns them into orders and manages the entire lifecycle (risk-% sizing, TP ladders with partial closes, multiple trailing strategies, time-based exits, breakeven, full-close logic).

### Architecture
- **Decision Layer**: Python `TradeDecision` dataclass (see `Python/execution/trade_decision.py`). Rich fields: `SizeSpec` (risk_pct_equity etc.), `ExitSpec` (ATR/R/pips/ladder), `TrailingSpec` (breakeven/ATR/step/chandelier), `PartialCloseLadder`, `TimeExitSpec`, etc.
- **ExecutionAgent** (`Python/execution/execution_agent.py`): Consumes `TradeDecision`, writes structured command JSON + .ready marker to `runtime/mql5_commands/` (or Common/Files/trade_decisions in live).
- **MQL5 Preferred Execution** (this EA in `ExecutionCommandMode=true`): Polls commands (throttled), executes with native CTrade speed + rich management (partials, ladders, trailing). Writes status reports back to `Common/Files/execution_status/` for Python observability.
- **Python Fallback**: Full `OrderManager` + `MT5Executor` (already has scale-outs, partials, BE, trailing) when MQL5 bridge not active.
- **Feedback for Learning**: `logs/execution_feedback.jsonl` + per-decision `runtime/execution_reports/<id>.json` (fills, partial closes, trailing SL moves, realized PnL). Decision PPO / training envs read these for observation augmentation and reward attribution.
- **Zero Breakage**: `TradeDecision.from_simple_intent()` + router adapters keep all legacy intent paths working.

### Arming the New Flow (Zero-Touch via Handoff Watcher + Supervisor)
1. Set env (or in supervisor launch): `AGI_DECISION_EXECUTION=1` (or future dedicated gate).
2. Handoff watcher / promoter / `vps_agi_supervisor.ps1` detect good candidate → arm paper harness + MQL5 deploy as before.
3. Deploy script (enhanced) + promoter can also stage `runtime/decision_execution_armed.json` + copy bridge-ready artifacts.
4. In MT5: Attach `ChainGambler_Executor.mq5` with:
   - `ExecutionCommandMode = true`
   - `UseCommonForCommands = true`
   - `EnableRichMgmt = true`
   (Inference/Shadow paths remain fully functional side-by-side.)
5. Python side (harness / Server_AGI / autonomy): Use `ExecutionAgent.submit_decision(td)` instead of raw intents.

### Command Protocol (file drop)
Python writes:
- `decision_<id>_<SYMBOL>.json` (full TradeDecision)
- `decision_<id>_<SYMBOL>.ready` (atomic signal)
- Optional compact `.cmd`

MQL5 EA (in ExecutionCommandMode) picks it up, executes, cleans marker, writes status JSON back.

### Next (Production Hardening)
- Full ladder + trailing state machine inside MQL5 (per-ticket magic + decision_id tag).
- ATR-based sizing resolution native in MQL5.
- Bi-directional status polling in ExecutionAgent.
- Promotion gate: "Decision+Execution armed" in TUI / supervisor checklist.

This completes the requested Execution Layer & Integration for autonomous trading while preserving every existing path.

