# Chain Gambler — Parallel Agent Workstreams Plan

**Goal:** Break the full Windows Production Readiness program into small, well-scoped tasks that can be executed in parallel by specialized subagents until the system is production-ready on real MT5.

**Master Reference Documents:**
- `docs/WINDOWS_PRODUCTION_GO_NO_GO_ASSESSMENT.md`
- `docs/GO_LIVE_CHECKLIST.md`
- `PROJECT_ASSESSMENT.md` (non-security items only)
- `docs/TRAINING_IMPROVEMENT_REVIEW.md`
- `scripts/production_validator.py`

---

## Guiding Principles for Parallel Work

1. **One primary agent owns the environment + MT5 connectivity** (single source of truth for "is the machine ready?").
2. **Workstreams are independent until merge points** (training data, champion registry state, risk events, evidence logs).
3. **Every workstream produces evidence** that feeds the master Go/No-Go document.
4. **Loop until Green**: Agents continue iterating their area until the overall assessment moves from "In Progress" to "GO".
5. **Clear interfaces**: Training produces models in the registry. Paper trading consumes the registry. Hardening protects everything.

---

## Proposed Parallel Workstreams

### Workstream A: Environment & MT5 Foundation (Owner: Primary Agent)
**Scope:**
- Clean Python .venv312 with all requirements satisfied (staged installs, retries, pandas_ta + MetaTrader5 fixes)
- One-time MT5 terminal installation + configuration via user RDP
- `setup_mt5_vps.ps1` execution + validation
- Reliable Python ↔ MT5 connectivity (`mt5.initialize()`, account info, symbol data)
- Headless launch scripts + Task Scheduler / NSSM supervision for the terminal itself
- Dry-run vs real mode switching tested

**Success Criteria:**
- `python -c "import MetaTrader5 as mt5; mt5.initialize(); print(mt5.account_info())"` succeeds cleanly
- Terminal can be launched and controlled headlessly
- All heavy ML packages (torch, stable-baselines3, etc.) import successfully in the venv

**Dependencies:** None (foundational)
**Outputs to:** All other streams

---

### Workstream B: Real MT5 Data Ingestion & Training Pipeline
**Scope:**
- Use real MT5 historical + recent candles (via `Python/data_feed.py` + `ingest_mt5.py`)
- Run / enhance `start_enhanced_training.py` with `--timeframe-opt --per-symbol-metrics`
- Train / retrain LSTM, PPO (SB3), and Dreamer components on actual market data
- Feature pipeline validation on real data (`ultimate_150` preferred)
- Output trained models into the proper registry structure
- Address reviewer gaps: training tests, curriculum (if any), hyperparameter tuning surface

**Success Criteria:**
- At least one full training cycle completed on ≥6 months of real MT5 data for target symbols
- Models pass basic backtest gates in `scripts/production_validator.py --phase 1`
- Artifacts appear correctly in `models/registry/candidates/...`

**Dependencies:** Workstream A (needs live MT5 data access)
**Outputs to:** Workstream C, D, F

---

### Workstream C: Champion / Canary Lifecycle & Model Registry
**Scope:**
- Execute and harden `tools/champion_cycle.py` + autonomy loops
- Validate promotion gates against real backtest/paper results (not relaxed synthetic thresholds)
- Fix or mitigate race conditions on `active.json` (file locking)
- Canary shadowing with proper lot scaling (`CANARY_LOT_MULT`)
- Hot-swap / model loading reliability in `hybrid_brain.py` and `Server_AGI.py`
- Model integrity + rollback procedures

**Success Criteria:**
- At least one complete champion → canary → promotion cycle using real data
- Registry state is consistent under concurrent read/write
- `logs/champion_cycle_last_report.json` contains meaningful metrics

**Dependencies:** Workstream B (needs trained candidates)
**Outputs to:** Workstream D, E, F

---

### Workstream D: Multi-Day Paper Trading Validation with Real Execution
**Scope:**
- Controlled paper trading using the real MT5 terminal (not pure simulation)
- Minimum 5–7 trading days continuous runtime with production risk parameters
- Full exercise of RiskEngine + RiskSupervisor + Guardian + Kill switches on real market movements
- Signal quality, drawdown, trade distribution tracking
- Telegram alerting + daily/weekly report generation
- Comparison against backtest (within tolerance per GO_LIVE_CHECKLIST)

**Success Criteria:**
- `scripts/production_validator.py --phase 2` (or equivalent) passes
- Zero unhandled critical failures
- All Phase 3 paper trading checklist items in GO_LIVE_CHECKLIST.md are green with evidence

**Dependencies:** Workstream A + C (needs working MT5 + a promoted champion/canary pair)
**Outputs to:** Workstream E, F

---

### Workstream E: Operational Hardening (Non-Security)
**Scope:**
- Process supervision (Task Scheduler / NSSM for `Server_AGI.py`, training cycles, dashboard)
- Graceful shutdown + training thread reliability (fix daemon thread issues from assessment)
- Monitoring & health endpoints (`/api/health`, `/api/health/ready`, status)
- Drift detection (`tools/backtest_vs_live_drift.py` integration into daily ops)
- Logging, rotation, audit trail completeness
- Backup & recovery (`backup_manager.py` usage + registry snapshots)
- Memory leak fixes and error handling improvements from reviewer (bare excepts, unbounded collections)
- Performance work on feature pipeline where it impacts production

**Success Criteria:**
- System survives restarts, training thread crashes, and manual halts cleanly
- Daily operations can run with minimal human intervention
- All "High" and "Medium" operational items from PROJECT_ASSESSMENT.md + TRAINING_IMPROVEMENT_REVIEW.md are closed or explicitly mitigated with evidence

**Dependencies:** Can start early; strongest value after D
**Outputs to:** Workstream F

---

### Workstream F: Evidence, Go/No-Go Assessment & Iteration
**Scope:**
- Continuous updates to `docs/WINDOWS_PRODUCTION_GO_NO_GO_ASSESSMENT.md`
- Collection of logs, metrics, charts, registry snapshots, risk events
- Running `scripts/production_validator.py` at each phase gate
- Tracking every item in GO_LIVE_CHECKLIST.md with links to evidence
- Final sign-off matrix (Trader + Developer style, adapted for this setup)
- Loop coordination: when a stream finishes a cycle, trigger re-validation across dependent streams

**Success Criteria:**
- Master assessment document reaches "GO" with all minimum bars met and supporting artifacts
- Clear, reproducible instructions for future deployments

**Dependencies:** Consumes evidence from all streams
**Special Role:** This stream owns the final decision loop

---

## Coordination & Looping Rules

- **Daily / per-cycle sync points**: After any major training run, champion promotion, or 24h+ paper trading period.
- **Blocker propagation**: If A (environment) is red, B/C/D/E pause or work in dry-run mode.
- **Evidence standard**: Every agent must produce at least one artifact (log file, JSON report, screenshot description, or updated checklist line) that can be referenced in the master Go/No-Go doc.
- **Re-entrancy**: Workstreams are designed to be re-runnable. Training can be kicked off again, paper trading can be extended, etc.

---

## Current Status (2026-05-27 — Updated Live by Evidence Curator)

**Environment (A):** Substantially advanced. .venv312 operational, heavy deps resolved (pandas_ta wheel notes), real MT5 data successfully ingested for first training runs (see logs). Terminal connectivity demonstrated via training (some equity query edge cases remain). User RDP + full Algo Trading/DLL setup still recommended for production paper/live.

**Workstream B (Training):** 
- First real-MT5 training cycle completed (BTCUSDm 1h optimal + XAU partial, 100k timesteps). Pre-alignment candidate `20260527_082932` staged + explicitly quarantined (`ALIGNMENT_STATUS.txt`).
- Post-fix validation run launched (hardened reward + real per-sym backtests + slippage).
- Evidence: `logs/enhanced_drl_training.log` (and variants), candidate bundle.

**Workstream C (Champion/Canary):**
- `docs/CHAMPION_CANARY_HARDENING_PLAN.md` active. Registry core already robust (FileLock, integrity hashes on 4 artifacts, canary gates). Sprint targeting residual races + observability for first real cycle.

**Workstream E (Operational Hardening):**
- `docs/OPERATIONAL_HARDENING_SPRINT.md` kicked off with high-impact Day 0-1 deliveries.
- ~18 bare `except` → structured logging in critical runtime paths (Server_AGI, mt5_executor, risk_supervisor).
- New production assets: `scripts/vps_agi_supervisor.ps1` (CIM-aware, health-polling, bounded restart, Task Scheduler recipe) + `scripts/healthcheck.ps1`.
- Health endpoints Windows-hardened.
- Directly closes major E1/E12 surface. See updated `REMAINING_NON_SECURITY_GAPS.md`.

**Workstream F (Evidence / Go-NoGo) + MQL5 Track:**
- Master `docs/WINDOWS_PRODUCTION_GO_NO_GO_ASSESSMENT.md` continuously updated with before/after, decision records, cross-stream evidence.
- New strategic MQL5 track: `docs/MQL5_EXECUTION_LAYER_DESIGN.md` (expanded live) + first artifact `tools/analyze_for_mql5_port.py` (PPO/adaptive-LSTM → CNeuronLSTM mapping) + full NeuroNetworksBook extraction (48097_extracted/).
- All streams producing artifacts per "evidence standard".

**Overall:** Multiple parallel agents executing. Training alignment remediation + operational + MQL5 tracks all live on 2026-05-27. Awaiting post-fix candidate + further hardening for next gates.

**Next agent spawn / continuation priorities:**
- Continue B: OOS splits + scorecard persistence + re-train for promotable candidate.
- E: Expand bare-except pass + test supervisor on VPS.
- MQL5: Weight exporter + first EA skeleton.
- F: Re-validate production_validator.py gates + feed new evidence here.

---

**This plan is living.** Update it as we discover better splits or new gaps during execution.

The overall mission: **Loop the above workstreams (with human + agent collaboration) until the Windows Production Go/No-Go Assessment shows a clear, evidenced "GO".**