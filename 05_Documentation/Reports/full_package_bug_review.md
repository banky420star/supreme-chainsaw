# Full Package Bug Review Report: React UI Monitoring App + Backend Feeders

**Date:** 2026-05-28  
**Agent:** Full Package Bug Review Agent  
**Scope:** 
- `frontend/` React SPA (monitoring trading data ingestion, equity curves, trades, pipeline stages, training loops, agent status, model registry, promotion gates, safety, etc.)
- Supporting stack: `Python/api_server.py` (primary API + WS), `Python/model_registry.py`, `Python/registry/promotion_gates.py`, `Python/parallel_lane_manager.py`, `Python/Server_AGI.py` (partial), training scripts, paper_trading, MT5 data ingest (`Python/data/ingest_mt5.py`), risk/supervisor layers, equity/trade sources (sqlite, jsonl, MT5), nginx proxy, Vite dev proxy.
- Focus: API contracts (api.ts fetch*/WS), data shapes for equity/pipeline/training/trades/agents, state sync, error handling, MT5/paper assumptions, type safety, races, production reliability for live trading monitoring.

**Methodology:** Systematic directory traversal, targeted greps across 100+ files for fetch/WS/equity/pipeline/training/trades/promotion/MT5/model_registry, deep reads of ~40 key files (api.ts, types, App.tsx, all major panels, api_server.py in sections, model_registry.py, promotion_gates.py, parallel_lane_manager.py, nginx configs, etc.), cross-referencing data flows, type usage, and integration points. Prioritized live trading impact (halt visibility, equity/trade accuracy, training health, promotion decisions).

**Overall Assessment:** The monitoring UI provides broad visibility but is fragile for production/live use. Real-time is broken, data often synthetic or stale/defaulted, heavy reliance on brittle parsing and loose types, excessive redundant polling, and several paths where backend failures or MT5 issues silently degrade the dashboard. Multiple critical issues directly impair ability to monitor live trading reliably.

---

## Critical Severity Bugs (Immediate Production Risk)

### 1. WebSocket Real-Time Channel Is Effectively Non-Functional (Always Falls Back to Polling)
- **Severity:** Critical
- **Files/Lines:**
  - `Python/api_server.py:4364` (`if WS_AVAILABLE:` then `@app.route('/ws/status')`)
  - `Python/api_server.py:4367-4384` (uses `wsgi.websocket` + `gevent_sleep` + direct call to `api_status()`)
  - `Python/api_server.py:83-92` (WS_AVAILABLE only if geventwebsocket installed; falls back to no-op)
  - `Python/api_server.py:4448` (always starts with `ThreadedWSGIRefServer` / wsgiref, **never** GeventWSGIServer)
  - `frontend/src/services/api.ts:206-208` (`new WebSocket(\`${protocol}//${location.host}/ws/status\`)`)
  - `frontend/src/services/api.ts:223-230` (reconnect logic, `MAX_FAILURES=3`)
  - `frontend/vite.config.ts:27-31` (WS proxy)
  - `nginx.conf:67-75` (proxy with Upgrade, but backend can't fulfill)
- **Description/Repro:** `createStatusWS` unconditionally connects. Server only registers the route (and only the gevent-specific handler) when the optional dep is present **and** would require switching the entire server runner to gevent (which is not done; wsgiref ThreadedMixIn does not support WS upgrades). On any normal start (or missing dep), every WS connect fails immediately. `onclose`/`onerror` trigger, `failures` increments to 3, then reconnects **stop forever** (`if (failures < MAX_FAILURES)` guard). `wsConnected` stays false. UI shows "POLL" badge.
  - Repro: `cd frontend; npm run dev` (or prod build + nginx) + start API normally; open browser console + network WS tab + UI status bar.
- **Impact:** No real-time push for status (account equity/balance, risk.halt, training visual progress, open positions, agent heartbeats, incidents). All monitoring (halt detection, live equity, training loops, trades) delayed up to 10s (App.tsx poll). In live trading, a risk halt or MT5 disconnect can be invisible for up to 10s+ (or permanently stuck in POLL after initial failures). Contradicts "real-time" design comments in api_server.py:2676.
- **Suggested Fix:** 
  1. Remove dead WS code or implement proper SSE fallback that frontend actually uses (already partially exists at `/api/status/stream`).
  2. Or adopt a real WS server (FastAPI + uvicorn with websockets, or standalone). Update frontend `createStatusWS` (or replace with EventSource) + proxy rules.
  3. Increase MAX_FAILURES or add exponential backoff recovery + manual reconnect button in UI.
  4. Make WS_AVAILABLE also control a working path.

### 2. Unprotected Concurrent MT5 Access in Threaded API Server (Crashes / Corrupt Telemetry)
- **Severity:** Critical
- **Files/Lines:**
  - `Python/api_server.py:533-642` (`_get_mt5_account_and_positions` — 5x `mt5.initialize()` retry loop + `account_info` + `positions_get`)
  - `Python/api_server.py:1540-1593` (`_fetch_trade_history` — `mt5.initialize()` + `history_deals_get`)
  - `Python/api_server.py:985+` (api_status calls it unconditionally)
  - `Python/api_server.py:1432+` (trades), `1723+` (equity indirect), health checks, etc.
  - `Python/api_server.py:4393` (`ThreadingMixIn` + WSGIRequestHandler — concurrent requests allowed)
  - `Python/mt5_compat.py` and callers in paper_trading / risk_engine
- **Description/Repro:** Status endpoint (polled 10s + side data + per-panel 15s + WS attempts) and trades/equity hit MT5 on nearly every request. No locks, no singleton MT5 client, no rate limiting beyond coarse _status_limiter. On Windows + live MT5 terminal, concurrent `initialize`/`history_deals_get`/`positions_get` from different request threads are known to cause IPC failures, partial data, or terminal crashes. Non-Windows or paper mode falls back but still executes paths.
  - Repro: Hammer `/api/status` + `/api/trades` concurrently while MT5 connected; observe missing equity/positions in UI or server logs with MT5 errors.
- **Impact:** Live trading monitor shows stale/wrong equity, open_positions=0 when trades are open, corrupted trade history, false "no positions" in agent status (api.ts:119). Can mask or trigger incorrect halts. Directly breaks production reliability for any live/demo MT5 session. Paper mode partially masks but decision cache fallback is even weaker.
- **Suggested Fix:** 
  - Add `threading.Lock` (or `mt5_lock`) around all MT5 calls in api_server.py (and centralize MT5 access).
  - Or use a dedicated MT5 poller thread that caches results (update every 1-2s) and serve from cache in API handlers.
  - Make paper mode the default safe path for dashboard when MT5 unavailable.
  - Add circuit breaker + clear error in responses when MT5 calls fail repeatedly.

### 3. Promotion Gates and Validation Status Always Return "Unknown"/Defaults (No Real Data)
- **Severity:** Critical
- **Files/Lines:**
  - `Python/api_server.py:946-958` (`_get_validation_status` — try: `from Python.registry.promotion_gates import get_promotion_status`)
  - `Python/api_server.py:3906-3926` (`api_promotion_gates` — always calls above or hard-coded gates using progress files only)
  - `Python/api_server.py:944` (similar for validation)
  - `Python/registry/promotion_gates.py:1-216` (defines `PromotionGates` class + `evaluate` + `DEFAULT_GATES`, **no** `get_promotion_status` top-level export)
  - `frontend/src/components/PromotionGatesPanel.tsx:33-34` + `api.ts:558`
  - `frontend/src/types.ts:284-290` (PromotionGateItem)
  - ModelRegistry + champion_cycle callers (not wired here)
- **Description/Repro:** Import always fails → always returns `{"backtest_status":"unknown", ...}`. `api_promotion_gates` builds fake gates using only training progress booleans + mt5 equity >0 (not real `PromotionGates.evaluate(validation_report)` or scorecard). UI shows empty/never-passing gates.
  - Repro: Hit `/api/promotion_gates` or open Promotion Gates tab after any training run.
- **Impact:** Operators cannot see real promotion readiness, canary gates, or why a model was/wasn't promoted. Breaks the entire "champion/canary" monitoring story for live trading. UI lies about production readiness. Directly tied to autonomous loop decisions.
- **Suggested Fix:** 
  - Implement `get_promotion_status()` (or `get_latest_gate_results()`) in `Python/registry/promotion_gates.py` that returns actual state from promotion logs / last evaluate calls / artifacts.
  - Wire `ModelRegistry` + recent scorecard from `artifacts/` or `logs/post_training_promotion_decisions.jsonl` into the endpoint.
  - Update api_promotion_gates to call real evaluator when possible.

### 4. Infinite / Stuck Loading Screen on Any Backend/API Failure
- **Severity:** High (affects all monitoring)
- **Files/Lines:**
  - `frontend/src/App.tsx:315` (`if (!pipe.status) return <LoadingScreen />`)
  - `frontend/src/App.tsx:260-264` (initial `fetchStatus().catch(() => null)` — only sets if truthy)
  - `frontend/src/App.tsx:279-286` (poll path same)
  - `frontend/src/services/api.ts:23-24` (`fetchStatus`: `r.ok ? r.json() : {}`)
- **Description/Repro:** Any 4xx/5xx, network error, or rate-limit on first `/api/status` (or during poll) leaves `pipe.status === null` forever. Loading animation runs indefinitely. No error UI, no retry button, no "API unreachable" state.
  - Repro: Stop backend or block port 5050; load UI.
- **Impact:** Complete loss of visibility into live trading when the feeder is degraded (exactly when you need the monitor most — during incidents, MT5 disconnects, training crashes). Production ops nightmare.
- **Suggested Fix:** Track `apiError` / `lastStatus` separately. Show error banner + last-known data + manual refresh. Never block render on first fetch. Add global error boundary.

---

## High Severity Bugs

### 5. Duplicate/Redundant Polling + No Shared State (High Load + Inconsistent Views)
- **Severity:** High
- **Files/Lines:**
  - `frontend/src/App.tsx:223-256` (refreshSideData + 10s poll of 8+ endpoints + status)
  - `frontend/src/components/PipelinePanel.tsx:54-71` (own 15s `/api/pipeline/stages`)
  - `frontend/src/components/PromotionGatesPanel.tsx:28-44` (own 15s)
  - `frontend/src/components/RegistryPanel.tsx`, `TradesPanel.tsx`, `DemoCanaryPanel.tsx`, `TradeCoronerPanel.tsx`, `ModelBrainsPanel.tsx`, `AgentsPanel.tsx` etc. (similar independent `useEffect` polls)
  - `frontend/src/services/api.ts:538-596` (new mission-control fetches)
  - `Python/api_server.py:202-205` (status rate limiter 60/min)
- **Description:** Every tab/panel independently fetches overlapping data every 10-15s. App + 6+ panels = 30-50+ requests/min even in idle. Status rate limiter kicks in (returns 429 with body). Panels can be out of sync with each other and with WS (when it "works").
- **Impact:** Unnecessary load on API/MT5/training processes. 429s cause panels to show empty data. State desync (e.g. registry vs promotion gates vs training lanes show contradictory champion status). Wastes resources that should be on trading/training.
- **Suggested Fix:** Centralize all data in App (or React Query/SWR context). Pass down or use global store. Increase intervals to 30s+. Make panels consume props instead of fetching.

### 6. Equity Curve Is Synthetic + Diverges From Live Account Equity (Misleading Monitoring)
- **Severity:** High
- **Files/Lines:**
  - `frontend/src/services/api.ts:435-440` + `EquityCurveResponse`
  - `Python/api_server.py:1723-1859` (`get_equity_curve` — SQLite `trades`/`bets` or `logs/paper_closed_trades.jsonl` only; manual cumulative from `starting_balance` calc using risk equity minus profits)
  - `Python/api_server.py:1142` (status `account` from real MT5/risk `_current_equity`)
  - `frontend/src/components/TradesPanel.tsx:189-193` + local EquityChart
  - `frontend/src/components/DashboardPanel.tsx:264` + EquityChart.tsx:170-173 (assumes points have numeric equity/balance/drawdown_pct)
- **Description:** Curve only replays closed trade profits. Ignores deposits, withdrawals, commissions, floating PnL, swaps. Backend calc can use stale `srv.get_account_info()`. No sync to live MT5 equity or risk engine `_current_equity`/`peak_equity`.
  - Repro: Run live trades; compare UI Equity Curve "Current" vs status panel account.equity or MT5 terminal.
- **Impact:** Operators see wrong drawdown/equity trajectory during live trading. Can mask real risk or give false confidence. Equity summary in trades tab lies.
- **Suggested Fix:** 
  - Primary source: account snapshots from risk engine / MT5 polls (store time-series in DB or runtime/runtime/account_snapshots.py).
  - Keep trade-profit curve as "realized PnL curve" (label it clearly).
  - Add warning in UI when using synthetic source.

### 7. Brittle Log/String Parsing for Training Progress + Visual State
- **Severity:** High
- **Files/Lines:**
  - `Python/api_server.py:645-799` (`_read_training_progress` — tail logs, `split("|")`, `split("epoch")`, regex-lite on "DRL Training | symbols=", "best_score=", "Rainforest trained on", etc.)
  - `Python/api_server.py:991-995` (status uses it for visual)
  - `frontend/src/components/TrainingPanel.tsx:193-211` + TrainingProgressPanel.tsx:38-53 (derive from `visual` + booleans)
  - Training scripts (train_lstm.py, train_ppo.py, etc.) that write the logs/progress json
- **Description:** Progress for LSTM/PPO/Dreamer/Rainforest falls back to parsing the last N lines of .log files with fragile string matching. Any log format change, log rotation, different logger, or non-English env breaks it → empty `visual` → UI shows "Idle" / 0% even when training is active.
- **Impact:** Training monitoring (core feature) is unreliable. Agent status (api.ts:86-113) shows wrong "Training"/progress. Perpetual lanes and promotion decisions invisible.
- **Suggested Fix:** All trainers must write canonical structured JSON progress files (already attempted with *_progress.json — make mandatory + atomic). Remove or deprecate log parsing. Add schema validation.

### 8. Heavy `any` / Loose Types + Direct Property Access Without Guards
- **Severity:** High (hides bugs, enables runtime crashes)
- **Files/Lines:**
  - `frontend/src/types.ts:9,13-14,24,39,83-87,141-145,155` (dozens of `any`, optional everything)
  - `frontend/src/services/api.ts:79` (`(status.risk as any)`), 179,184,257,288,293,308,400,412
  - `frontend/src/App.tsx:195`
  - Panels: `TrainingPanel.tsx:193` (`as any` for parallel_lanes), `DashboardPanel.tsx:329,409`, `TradingPanel.tsx:408,462`, `ModelsPanel.tsx:115,187`, many `toneFromStatus` etc. returning `any`
  - EquityChart.tsx:80-81,170-173,212 (assumes shape); similar in local charts
- **Description:** Almost every data path from backend uses `any` or `?`. No runtime validation (zod/io-ts). Backend can return missing keys, wrong types (string vs number for progress_pct), nulls where number expected → `.toFixed()`, `.map()`, `b.bundle_id.slice` etc. throw.
  - Repro: Corrupt a progress json or send bad payload → panel crash (no error boundary in App).
- **Impact:** Silent or loud crashes in monitoring UI during real incidents (exactly when data is messy). Hard to debug. TypeScript gives false safety.
- **Suggested Fix:** Strict types + runtime guards (or generated from OpenAPI). Add React ErrorBoundary per panel. Replace `as any` casts with proper interfaces. Add `??` / `typeof` checks before math/string ops.

### 9. Model Registry API + Active Reads Ignore Real Registry + Per-Symbol State
- **Severity:** High
- **Files/Lines:**
  - `Python/api_server.py:362-365` (`_read_active_registry` — plain file read)
  - `Python/api_server.py:3872-3903` (`api_registry` — loops only over config symbols, hardcodes most fields from progress)
  - `Python/model_registry.py:173-217` (locked reads/writes with per-symbol "symbols" map, history, canary_policy)
  - `frontend/src/components/RegistryPanel.tsx:114` (assumes `bundle_id`, `symbol` etc always present)
  - `Python/api_server.py:1071` (status uses active["symbols"] partially)
- **Description:** API bypasses `ModelRegistry` class entirely for most reads. Per-symbol champions/canaries in active.json "symbols" dict are under-used. Registry UI shows only top-level config symbols.
- **Impact:** Inaccurate view of what is actually live (per-symbol vs global). Promotion/rollback actions via control may not match what UI shows. Integration drift between model_registry and dashboard.
- **Suggested Fix:** Make api_server use `ModelRegistry()` instance (respect locks). Expose full per-symbol + history data. Keep simple fallbacks for standalone mode.

---

## Medium Severity Bugs & Issues

### 10. Fetch Error Handling Swallows All Errors + Returns Silent Defaults
- **Severity:** Medium (compounds with others)
- **Files:** `api.ts:24` (status), 172 (patterns), 180 (perf), 260 (ppo), 274, 311, 333, 354, 403, 409, 435 (equity), 460, 481, 502+ (many `r.ok ? json : default`)
- **Description:** Network errors, 5xx, JSON parse fails → silent {} / [] / null. No logging, no distinction between "no data" and "backend broken".
- **Impact:** UI looks healthy with zeros/empties while real data is unavailable. Delays incident detection.
- **Fix:** Introduce typed error results or global toast/error state. At minimum console.error + optional "degraded" flag.

### 11. ParallelLaneManager Race Conditions on Lane State Mutation
- **Severity:** Medium
- **Files/Lines:** `Python/parallel_lane_manager.py:141-169` (`_run_lane` gets ref via `_get_lane` (locked briefly), then mutates fields outside lock), `269-278` (get_status locks only for copy)
- **Description:** Training threads mutate `LaneState` objects while API/status threads read via `get_status`. No deep copy protection; to_dict can see half-updated objects.
- **Impact:** Training progress in UI (and agent status) can show inconsistent/jumpy % or phases. Minor for monitoring but can confuse during long runs.
- **Fix:** Hold lock during mutation or use immutable updates + queue.

### 12. No Atomicity / Lock on API Direct Reads of active.json + progress files
- **Severity:** Medium
- **Files:** `Python/api_server.py:351-358` (`_read_json_file` plain open), 362 (`_read_active_registry`), 645 (`_read_training_progress`)
- **Vs.** model_registry.py which uses FileLock + temp+move for writes.
- **Impact:** During promotion/registration/training writes, API can read truncated or backup .bak state → UI flashes wrong champion/canary.
- **Fix:** Centralize reads through ModelRegistry or add shared reader locks/timeouts.

### 13. Duplicate EquityChart Implementations + Inconsistent Rendering
- **Severity:** Medium
- **Files:** `frontend/src/components/EquityChart.tsx` (full featured) vs `TradesPanel.tsx:7-50` (simplified local version with hardcoded 800px viewBox, no resize, different smoothing/tooltip)
- **Impact:** Different visuals for "the same" equity data depending on tab. Maintenance burden, subtle bugs.
- **Fix:** Delete duplicate; always use the shared component.

### 14. Training/Agent Status Hardcodes Fake Metrics + Brittle Derivations
- **Severity:** Medium
- **Files:** `frontend/src/services/api.ts:34-162` (`extractAgentStatus` — hardcodes "Candles/min: 12", "Score: neutral", pattern counts from status, etc.)
- **Impact:** Misleading "live" metrics in AgentsPanel. Doesn't reflect real ingestion rate or MT5 health.
- **Fix:** Pull real counters from data_feed / provenance / risk engine.

### 15. Vite/Prod Base Path + Proxy Assumptions Can Break Deployment
- **Severity:** Medium
- **Files:** `frontend/vite.config.ts:16` (`base: '/app/'`), `frontend/index.html`, nginx configs, Dockerfile.frontend
- **Description:** Relative BASE='' + proxy works in dev; prod deploys may have path or origin mismatches for WS/API.
- **Impact:** Monitoring app fails to load data in some container/K8s/VPS setups.
- **Fix:** Make base/API origin configurable via env.

### Additional Lower/Medium Issues (Summary)
- **Log format / MT5 version assumptions** in trade history parsing and _extract_bot_lane (api_server.py).
- **No pagination safety / huge responses** for trades when DB grows (limit hardcoded, full scan in summary).
- **Paper trading JSONL** appends without rotation/locking → can corrupt on concurrent writes (paper_trader + API).
- **Health endpoints** have fragile subprocess ps hacks for Windows (api_server.py:2742-2804) that can hang or give wrong "server_running".
- **Missing CORS / origin validation** in some paths; rate limiter is per-IP only.
- **No circuit breakers** around slow MT5/DB calls (can stall entire API thread pool).
- **Frontend has no React Query / caching / deduping** — every tab switch re-fetches.
- **Date parsing** in equity/trades assumes ISO or specific formats; many `new Date(d)` with fallbacks to now (api.ts:36-42).
- **Inconsistent "running" detection** across lstm/ppo/dreamer (progress json mtime vs log vs flags).

---

## Recommendations & Prioritization for Live Trading

1. **Immediate (before next live run):** Fix WS/SSE (or accept polling + document), add MT5 lock + cache layer, implement real promotion_status, add error states + last-known data to UI, remove or guard all `as any` + add ErrorBoundaries.
2. **High:** Unify data fetching, make equity source authoritative (risk snapshots), harden training progress to structured JSON only.
3. **Architecture:** Consider moving API to FastAPI/Starlette (native async + WS + Pydantic models for contracts) to eliminate Bottle + conditional gevent hacks. Generate TS client from OpenAPI.
4. **Observability:** Add request logging + timing in api_server, expose last_error per component in /api/status, UI banners for "data stale >30s".
5. **Testing:** Add contract tests (backend responses vs frontend types), chaos test (kill MT5 mid-poll), load test concurrent status calls.
6. **Monitoring the Monitor:** The dashboard itself should have a self-health panel that shows its own fetch success rate and data freshness.

**Positive Notes (for balance):** 
- Excellent resilience in trade/equity fallbacks (4 sources).
- Good use of locks in ModelRegistry writes.
- Rich set of panels and honest "truth" intent in many endpoints.
- Loading animations and visual polish are production-grade.

This review covers the primary paths for equity, pipeline, training, trades, agents, registry, promotion, and safety. Additional files (full training_*.py, risk_engine.py, data/provenance.py, autonomy_loop.py) were spot-checked for assumptions but primary integration is through the API layer documented above.

**End of Report.** Fix the Criticals first — they directly compromise the ability to safely monitor and react to live trading behavior. 

(Report generated from exhaustive static + flow analysis; dynamic repro would require running the full stack + MT5 terminal.)