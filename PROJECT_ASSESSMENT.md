# Chain Gambler — Comprehensive Project Assessment

**Date:** 2026-05-14  
**Project Root:** `/Volumes/AI_DRIVE/trading bot/chain_gambler-main`  
**Assessment Scope:** Full codebase audit (architecture, security, bugs, performance, testing, production readiness)

---

## Executive Summary

Chain Gambler is a sophisticated autonomous trading system targeting MetaTrader 5 (MT5) with an ensemble of LSTM, PPO (Stable Baselines3), and DreamerV3 models, a champion/canary promotion pipeline, live risk supervision, and a React dashboard. The codebase is large (~46,000 source lines across Python/modules, ~7,300 test lines) and demonstrates genuine engineering effort in risk controls, model registry integrity, and operational observability.

**However, critical security vulnerabilities, relaxed safety thresholds, dangerous position-sizing logic, and structural brittleness make this system unsafe for live trading in its current state.** The most severe issue is hardcoded broker credentials in a tracked config file. Secondary concerns include un-pinned dependencies, RPyC remote code execution paths, race conditions in the model registry, and "Full Kelly" position sizing that can blow up accounts.

---

## Architecture Overview

### High-Level Flow

```
MetaTrader 5 Broker
        |
        v
data_feed.py -> feature_pipeline.py (150-feature "ultimate_150" vector)
        |
        v
   HybridBrain
   /    |    \
LSTM   PPO   Dreamer
(regime) (policy) (optional blend)
        |
        v
RiskEngine + RiskSupervisor (soft limits + hard pre-trade gate)
        |
        v
   MT5Executor (symbol-scoped orders + SL/TP management)
```

### Champion/Canary Pipeline

```
training/ (train_lstm.py, train_drl.py, train_dreamer.py)
    |
    v
models/registry/candidates/<timestamp>/
    |
    v
model_evaluator.py (Sharpe, drawdown, return criteria)
    |
    v
Canary (shadow) in active.json -> promote to Champion -> hot-swap in Server_AGI
```

### Key Modules

| Module | Role | Lines (approx) |
|---|---|---|
| `Python/Server_AGI.py` | Main trading loop, risk supervision, MT5 execution | 1,310 |
| `Python/api_server.py` | Bottle HTTP API for React dashboard | ~4,240 |
| `Python/hybrid_brain.py` | Signal blending from LSTM + PPO + Dreamer | 664 |
| `Python/mt5_executor.py` | Live MT5 order execution + position management | 1,169 |
| `Python/risk_engine.py` | Soft risk limits (daily loss, trade count) | 121 |
| `Python/risk_supervisor.py` | Hard pre-trade circuit breaker | 172 |
| `Python/model_registry.py` | Champion/canary state, promotion policy | 752 |
| `Python/feature_pipeline.py` | 150-feature vector construction | 363 |
| `Python/agi_brain.py` | LSTM regime classifier | ~400 |
| `tools/project_status_ui.py` | Dashboard + control API | ~2,630 |

---

## Component Inventory

### Core Trading Stack
- **Server_AGI.py**: Orchestrates the main loop (data fetch -> inference -> risk check -> execution -> logging). Runs a background training thread.
- **HybridBrain**: Loads PPO/Dreamer models from registry, builds observations, runs inference, blends signals.
- **MT5Executor**: Sends orders via MT5 (or paper mode), manages SL/TP, breakeven, trailing stops, spread/session guards.
- **RiskEngine**: Daily loss cap, trade count limits, drawdown tracking, consecutive-error halt.
- **RiskSupervisor**: Pre-trade gate (spread, cooldown, position limits, exposure limits, confidence checks).
- **ModelRegistry**: File-based registry with integrity hashing (SHA-256), canary promotion policy, per-symbol champions.

### Data & Feature Engineering
- **data_feed.py**: MT5 candle acquisition, caching.
- **feature_pipeline.py**: Two feature versions: `engineered_v2` (21 features) and `ultimate_150` (150 features including multi-timeframe resamples).

### Training Pipeline
- **training/train_lstm.py**: Per-symbol LSTM training.
- **training/train_drl.py** / **train_ppo.py**: PPO training with Optuna hyperparameter search.
- **training/train_dreamer.py**: DreamerV3 world-model training.
- **tools/champion_cycle.py**: Automated retrain -> evaluate -> stage cycle.

### Safety & Observability
- **live_safety.py**: Multi-gate live trading safety (telemetry, pytest pass, champion validation, canary check).
- **event_guard.py** / **event_intel.py**: Economic calendar/news hold-out windows.
- **alerts/telegram_alerts.py**: Telegram bot for alerts.
- **api_server.py**: 40+ endpoint REST API (status, trades, equity curve, models, control actions).
- **tools/project_status_ui.py**: Dashboard server with WebSocket/SSE support.

### UI / Frontend
- **frontend/**: React + Vite dashboard (13 tabs).
- **ui_lab_app/**: Secondary Vite app.

### Infrastructure
- **Dockerfile**: Python 3.12-slim, non-root user, healthcheck.
- **docker-compose.yml**: AGI + n8n + Redis stack.
- **nginx.conf**: Reverse proxy config.

---

## Bugs & Issues (Prioritized)

### Critical

| ID | Issue | Location | Impact |
|---|---|---|---|
| C1 | ~~Hardcoded MT5 credentials in config.yaml~~ | `config.yaml:137` | ~~Password `"Fuckyou2/"` and login `435656990` are committed to the repo. This is a severe secret leak.~~ **FIXED**: Credentials moved to `.env` and `config.yaml` now uses `ENV:MT5_*` references. `config.yaml` removed from git index. |
| C2 | **Full Kelly position sizing is dangerously aggressive** | `Python/mt5_executor.py:543-648` | Uses full Kelly fraction `f* = (p*b - q) / b` with no fractional dampening (e.g., Half-Kelly or Quarter-Kelly). On small accounts with limited history, this can size to the maximum allowed lots instantly, risking ruin. |
| C3 | **Race condition on active.json (model registry)** | `Python/model_registry.py` | `_read_active()` and `_write_active()` have no file locking. If Server_AGI reads while champion_cycle writes, the JSON can be partially written or corrupted. The code has a JSONDecodeError fallback, but concurrent writes during promotion could lose state. |
| C4 | **RPyC remote eval() in mt5_compat.py** | `Python/mt5_compat.py:107-276` | The Wine bridge constructs Python expressions via string interpolation and executes them remotely with `conn.eval()`. If `_WINE_HOST`/` _WINE_PORT` are MITM'd or misconfigured, an attacker can inject arbitrary code into the remote Python process. |
| C5 | **Training thread is daemon with no cleanup/join** | `Python/Server_AGI.py:945-952` | `autonomy.training_cycle()` runs in a `daemon=True` thread. If it crashes or hangs, Server_AGI has no way to detect or restart it. The thread is started every N loops without checking if a previous instance is still running (there is a basic `is_alive()` check, but no timeout or deadlock detection). |

### High

| ID | Issue | Location | Impact |
|---|---|---|---|
| H1 | **SQL injection via f-string in api_server.py** | `Python/api_server.py:1656` | `f"SELECT close_time, profit FROM {table_name} {where} ORDER BY close_time ASC"` concatenates `table_name` and `where` directly. While currently sourced from hardcoded values, this pattern is brittle if ever refactored to accept user input. |
| H2 | **Unpinned dependencies in requirements.txt** | `requirements.txt` | No version pins for `pandas`, `numpy`, `torch`, `stable-baselines3`, etc. A breaking change in any dependency (especially PyTorch or SB3) can render models unloadable or change inference behavior silently. |
| H3 | **Evaluation thresholds dangerously relaxed** | `config.yaml:86-100` | `min_sharpe: -0.5`, `min_return: -0.10`, `min_pass_rate: 0.5`, `min_forward_win_rate: 0.34`. These gates allow models with negative expected value to be promoted to canary and potentially champion. |
| H4 | **Model integrity only checks two files** | `Python/model_registry.py:14` | `INTEGRITY_TARGETS = {"model": "ppo_trading.zip", "vec_normalize": "vec_normalize.pkl"}`. If metadata or scaler files are corrupted, the integrity check passes. Also, SHA-256 is computed but not cryptographically signed — an attacker with filesystem access can simply recompute the hash. |
| H5 | **Paper/demo mode bypasses halt persistence** | `Python/risk_supervisor.py:80-81` | `_is_demo_mode()` skips loading `halt_until` from state. While intentional for continuous demo trading, this logic is easy to accidentally trigger in production by setting the wrong env var, disabling a critical safety mechanism. |
| H6 | **No HTTPS / WSS on API server** | `Python/api_server.py` | Bottle runs HTTP only. Control actions (emergency stop, unblock, arm_live) are protected by `AGI_CONTROL_TOKEN`, but the token is sent in plaintext over HTTP. No TLS termination is configured in the provided Dockerfile or docker-compose. |
| H7 | **n8n service has no authentication** | `docker-compose.yml:28` | `N8N_BASIC_AUTH_ACTIVE=false` exposes the n8n workflow engine without auth on port 5678. |
| H8 | **MT5 `order_send` passes raw dict to RPyC eval string** | `Python/mt5_compat.py:251-252` | `order_send` does `self._call(f"mt5.order_send({request})")` where `request` is a dict. The string conversion is implicit and could be manipulated if the dict contains unsanitized values. |

### Medium

| ID | Issue | Location | Impact |
|---|---|---|---|
| M1 | **Magic number collision risk** | `Python/mt5_executor.py:24-53` | `MAGIC_BY_SYMBOL` only defines BTCUSDm and XAUUSDm. Other symbols fall back to a generic base. If multiple symbols share the same magic base, orders/comments can collide, making trade attribution unreliable. |
| M2 | **config.yaml is tracked with secrets** | `.gitignore` | `.gitignore` does NOT exclude `config.yaml` (only `config.yaml.example` is meant to be tracked). The actual `config.yaml` with live credentials is in the repo. |
| M3 | **`live_safety` runs pytest on every live gate check** | `Python/live_safety.py:54-86` | `_check_pytest_passes()` spawns a subprocess running the full test suite with a 120s timeout. Called on every `live_trading_allowed()` invocation. This is expensive and can block the trading loop. |
| M4 | **No database migrations or schema versioning** | `trades.db`, `bets.db` | SQLite schemas are created ad-hoc. There is no migration system; schema changes require manual intervention. |
| M5 | **Duplicate/conflicting config loading paths** | Multiple modules | Many modules load `config.yaml` independently with slightly different path resolution logic. This can lead to inconsistent configs if files exist in multiple locations. |
| M6 | **`_position_exposure_state` has complex branching for dict vs object** | `Python/Server_AGI.py:715-730` | Heavy use of `isinstance(pos, dict)` ternaries per position. This is error-prone and slow if many positions are open. |
| M7 | **Feature pipeline uses `min_periods=1` everywhere** | `Python/feature_pipeline.py:236-362` | Rolling windows with `min_periods=1` on small dataframes produce unstable statistics. Early bars in a window can have extreme values due to tiny sample sizes. |
| M8 | **No graceful shutdown of Server_AGI** | `Python/Server_AGI.py` | `while True:` loop with `time.sleep()` has no signal handler for SIGTERM/SIGINT. Positions may be left open on restart. |

### Low

| ID | Issue | Location | Impact |
|---|---|---|---|
| L1 | **Typo in MT5 executor comment** | `Python/mt5_executor.py:640` | "Fall back to Kelly sizing if ATR is unavailable" — the method is called `_kelly_lot_size` but is labeled "Full Kelly" and is extremely aggressive, contrary to the "Half-Kelly" docstring earlier. |
| L2 | **Dead code / unused imports** | Various | Many files import modules that are never used (e.g., `asyncio` in `hybrid_brain.py` with no async functions). |
| L3 | **.DS_Store files committed** | Multiple | macOS metadata files are in the repo. |
| L4 | **No rate limiting on API** | `Python/api_server.py` | Control endpoints could be brute-forced for the control token. |
| L5 | **Inconsistent logging levels** | Various | Some modules use `logging`, others use `loguru`, leading to mixed log formats. |

---

## Security Audit

### Secret Exposure
- **CRITICAL**: `config.yaml` contains a live MT5 password (`"Fuckyou2/"`) and login ID (`435656990`). This file is tracked by git.
- **MEDIUM**: Telegram token and chat_id fields are empty strings in `config.yaml`, which is safer, but the example file shows placeholder values.
- **RECOMMENDATION**: Immediately rotate the MT5 password. Add `config.yaml` to `.gitignore`. Use environment variables or a secrets manager (e.g., Docker secrets, Vault).

### Remote Code Execution
- **HIGH**: `mt5_compat.py` uses `rpyc.classic.connect()` and `conn.eval()` to execute dynamically constructed Python strings on a remote host. If the RPyC server is exposed beyond localhost or lacks authentication, this is a full remote code execution vector.
- **RECOMMENDATION**: Bind RPyC to `127.0.0.1` only, enable RPyC's SSL/authentication, and validate all serialized arguments against an allowlist.

### API Security
- **MEDIUM**: Control actions use `secrets.compare_digest()` which is good (constant-time comparison), but the token travels over HTTP unless a reverse proxy provides TLS.
- **MEDIUM**: CORS allows `localhost:4180` and `127.0.0.1:4180` by default. In production, `_extra_origins` can be set via env but there is no validation of origin format.
- **LOW**: The `api_server.py` logs control actions with their payloads, which could inadvertently log sensitive data.

### Database
- **LOW**: SQLite queries in `api_server.py` are mostly static, but the f-string pattern for `table_name` and `where` is a latent SQL injection risk.

### Docker
- **MEDIUM**: `docker-compose.yml` mounts the entire project root as a volume (`- .:/app`). Any file modification on the host is immediately reflected in the container, including potential tampering with `config.yaml` or model files.
- **MEDIUM**: n8n runs without basic auth.

---

## Performance Analysis

### Bottlenecks
1. **Feature Engineering (ultimate_150)**: The `_build_ultimate_feature_frame` function creates ~150 features with multiple resample operations (`15min`, `1h`, `4h`, `1d`) on every tick for every symbol. On a tight loop (e.g., 20s intervals), this is CPU-intensive and memory-allocating.
2. **PPO Model Loading**: `HybridBrain._load_ppo_bundles_for_symbol()` loads `.zip` models from disk and reconstructs `DummyVecEnv` on every initialization. If called repeatedly (e.g., on registry hot-swap), this causes GC pressure.
3. **Subprocess Pytest in Live Gate**: `live_safety._check_pytest_passes()` spawns `pytest` as a subprocess with a 120s timeout. This can block the main loop for up to 2 minutes.
4. **JSONL Logging**: `_append_jsonl()` opens/closes the file on every event. Under high event volume, this is I/O heavy. The rotation logic (`_rotate_jsonl_if_needed`) also does file size checks on every write.
5. **MT5 History Queries**: `_update_kelly_stats()` fetches 30 days of deals every 5 minutes per symbol. On symbols with high turnover, this data transfer is unnecessary; incremental updates would be more efficient.

### Memory
- `seen_closed_deals` is a Python `set` that grows unbounded until it hits 20,000 entries, then trims to 10,000. With many symbols and high frequency, this set can consume significant memory.
- `_decision_cache` in `api_server.py` stores up to 50 decisions per symbol indefinitely (no TTL).

### Scalability
- The architecture is single-process, single-threaded for the main trading loop. Background training is a single daemon thread. This will not scale to a large symbol universe or high-frequency regimes without multiprocessing.

---

## Testing Coverage

### Quantitative
- **Source Lines (Python/src/drl/training/tools)**: ~46,436
- **Test Lines (tests/)**: ~7,344
- **Ratio**: ~15.8% test-to-source line ratio
- **Test Files**: 38+ test modules

### Qualitative
- Tests cover key components: risk engine, risk supervisor, model registry, hybrid brain, training pipeline, API schema, MT5 executor reconciliation, order manager.
- **Missing coverage areas**:
  - `Server_AGI.py` main loop (no integration tests for the full loop)
  - `mt5_executor.py` live order_send paths (mocked only)
  - `feature_pipeline.py` correctness (no property-based tests for feature values)
  - `mt5_compat.py` Wine bridge (untested)
  - Telegram alert delivery failures
  - Champion/canary promotion race conditions
  - Live safety gate subprocess timeout handling

### Test Infrastructure
- `pytest.ini` exists but only sets `cache_dir`. No coverage reporting, no markers, no timeout plugin.
- No CI/CD workflow files that run tests automatically (`.github/workflows/build.yml` exists but was not read in detail; needs verification).

---

## Missing Features for Production

### 1. Secrets Management
- No integration with a secrets manager. Passwords in config files are unacceptable for production.

### 2. TLS/HTTPS
- API server and dashboard communicate over plaintext HTTP. Production requires TLS termination (e.g., Traefik, Nginx with Let's Encrypt).

### 3. Database Persistence
- SQLite is used ad-hoc with no migrations. Consider Alembic or a managed PostgreSQL for trade history.

### 4. High Availability
- Single-instance architecture. No failover, no leader election, no horizontal scaling.

### 5. Audit Logging
- JSONL audit logs are local files. Production needs tamper-proof audit logging (e.g., append-only object storage, signed log streams).

### 6. Model Provenance
- Model registry tracks SHA-256 hashes but no digital signatures. A compromised host can replace models and update hashes.

### 7. Graceful Shutdown
- No SIGTERM handler to close positions or flush logs before exiting.

### 8. Dependency Pinning & SBOM
- `requirements.txt` lacks version pins. No Software Bill of Materials (SBOM) for supply-chain security.

### 9. Health Checks
- The Docker healthcheck curls `localhost:9090/api/health`, but the main loop has no internal liveness probe (e.g., heartbeat within the loop).

### 10. Circuit Breaker for Model Inference
- If PPO inference fails repeatedly (10 times), PPO is disabled per-symbol. However, there is no automatic re-enrollment or alert escalation.

---

## Recommendations

### Immediate (Do Before Any Live Trading)
1. **Rotate the MT5 password** exposed in `config.yaml` immediately.
2. **Add `config.yaml` to `.gitignore`** and remove it from git history (use `git-filter-repo` or BFG Repo-Cleaner).
3. **Replace Full Kelly with Half-Kelly or Quarter-Kelly** in `mt5_executor.py`, or cap Kelly fraction at a conservative maximum (e.g., 0.05 lots for accounts under $1,000).
4. **Add file locking** (`filelock` or `fasteners`) around `active.json` reads/writes in `ModelRegistry`.
5. **Pin all dependencies** in `requirements.txt` with exact versions and hashes.

### Short Term (1-2 Weeks)
6. **Fix the SQL f-string** in `api_server.py` to use parameterized queries or a query builder.
7. **Add TLS termination** in front of the API server (Nginx/Traefik with Let's Encrypt).
8. **Refactor `live_safety._check_pytest_passes()`** to run asynchronously or cache results with a longer TTL, and never block the trading loop.
9. **Add SIGTERM/SIGINT handlers** in `Server_AGI.py` for graceful shutdown.
10. **Tighten evaluation thresholds** back to sensible defaults (e.g., `min_sharpe >= 0.3`, `min_return >= 0.015`, `min_forward_win_rate >= 0.67`).

### Medium Term (1 Month)
11. **Replace RPyC Wine bridge** with a safer IPC mechanism (e.g., gRPC with protobuf, or a REST bridge) to eliminate `eval()` usage.
12. **Implement a real migration system** for SQLite/PostgreSQL schemas.
13. **Add integration tests** for the full Server_AGI loop using a mock MT5 bridge.
14. **Add distributed tracing** (e.g., OpenTelemetry) across the trading loop, API, and training pipeline.
15. **Implement a secrets manager** integration (e.g., HashiCorp Vault, AWS Secrets Manager, or at minimum Docker secrets).

### Long Term
16. **Migrate to a multi-process or microservice architecture** for training vs. inference separation.
17. **Add formal model provenance** with cryptographic signatures and immutable artifact storage (e.g., S3 with object locking).
18. **Implement automated chaos engineering** tests (e.g., kill MT5 connection mid-trade, corrupt active.json, disk-full scenarios).

---

*End of Assessment*
