# Production Deployment Guide

This guide covers a complete production deployment of Chain Gambler on a Windows VPS or dedicated machine with MetaTrader 5 access.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Secrets Setup](#2-secrets-setup)
3. [MT5 Connection](#3-mt5-connection)
4. [Python Environment](#4-python-environment)
5. [Docker Stack (Optional)](#5-docker-stack-optional)
6. [Frontend Build and Serving](#6-frontend-build-and-serving)
7. [Health Validation](#7-health-validation)
8. [Process Supervision](#8-process-supervision)
9. [Log Locations and Rotation](#9-log-locations-and-rotation)
10. [Backup and Recovery](#10-backup-and-recovery)
11. [Upgrading](#11-upgrading)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows | 10 / Server 2019+ | MT5 requires Windows; Linux/Mac supported in dry-run only |
| Python | 3.12 | Use the `.venv312` convention |
| Node.js | 20 LTS | Required to build the React dashboard |
| Git | Any | For pulling updates |
| MetaTrader 5 | Latest | Must be installed and logged in on the same machine |
| Docker Desktop | 24+ | Optional — for Redis + n8n sidecar services |
| Telegram Bot | — | Required for alert delivery; create via @BotFather |

**Minimum hardware:**
- 4 CPU cores (8 recommended for parallel training)
- 8 GB RAM (16 GB recommended)
- 50 GB disk (models, logs, and backups accumulate)

---

## 2. Secrets Setup

Never commit `config.yaml`. It is gitignored and must be created on each deployment machine.

```powershell
# From the project root
Copy-Item config.yaml.example config.yaml
```

Open `config.yaml` and set all required fields:

```yaml
mt5:
  login: ENV:MT5_LOGIN       # Or your MT5 account number
  password: ENV:MT5_PASSWORD  # Or your MT5 password
  server: ENV:MT5_SERVER    # Or your broker's MT5 server name

telegram:
  token: "YOUR_BOT_TOKEN_HERE"  # From @BotFather
  chat_id: "YOUR_CHAT_ID_HERE"    # Your Telegram group or user chat ID

trading:
  symbols:
    - BTCUSDm
    - XAUUSDm
```

**For Docker deployments**, create a `.env` file in the project root:

```bash
# .env — never commit this file
AGI_CONTROL_TOKEN=change-this-to-a-long-random-string
AGI_IS_LIVE=1
AGI_ALLOWED_ORIGINS=https://your-dashboard-domain.com
PYTHONUNBUFFERED=1
```

Generate a strong control token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The `AGI_CONTROL_TOKEN` must be set before starting the server in production. Without it, protected control actions (emergency stop, promote canary, restart) are blocked.

---

## 3. MT5 Connection

### Windows Native (Recommended)

MetaTrader 5 must be installed and running on the same Windows machine. The Python MetaTrader5 package communicates with the MT5 terminal via the Windows COM interface.

1. Install MT5 from your broker's website.
2. Log in to your live or demo account.
3. Enable "Allow DLL imports" and "Allow automated trading" in MT5 settings.
4. Verify the connection:

```powershell
python -c "import MetaTrader5 as mt5; print(mt5.initialize(), mt5.account_info())"
```

Expected output: `True AccountInfo(login=..., server=..., ...)`

### Mac / Linux (Wine Bridge — Dry-Run Only)

The MetaTrader5 Python package does not run natively on Mac or Linux. For local development, the server falls back to dry-run mode automatically when MT5 is unavailable.

For production on Linux (e.g., a VPS), two options exist:

**Option A — Windows VPS (recommended):** Rent a Windows VPS from providers like Vultr, Contabo, or AWS (EC2 Windows instance) and run everything natively.

**Option B — Forward MT5 from a Windows machine:** Run `Python/Server_AGI.py` on Windows and expose only the dashboard/API via a reverse proxy. The trading loop and MT5 must remain on Windows.

---

## 4. Python Environment

```powershell
# From the project root
python -m venv .venv312
.venv312\Scripts\activate
pip install -r requirements.txt
```

Verify the install:

```powershell
.venv312\Scripts\python.exe -m compileall Python training tools drl
.venv312\Scripts\python.exe -m pytest --tb=short -q
```

Both commands must complete without errors before proceeding.

---

## 5. Docker Stack (Optional)

The Docker Compose file adds Redis (for state caching) and n8n (workflow automation) alongside the AGI container. The primary production path uses the Windows venv directly; Docker is an optional sidecar layer.

**Start the full stack:**

```bash
docker compose up -d
```

**Services:**

| Service | Port | Purpose |
|---|---|---|
| `agi` | 9090 | AGI engine (Python) |
| `redis` | 6379 | Persistent key-value state |
| `n8n` | 5678 | Workflow automation (optional) |

**Production notes:**

- `config.yaml` is mounted read-only into the `agi` container — place it in the project root before starting.
- Model artifacts in `models/` and logs in `logs/` are bind-mounted so they persist across container restarts.
- Set `restart: always` in `docker-compose.yml` (instead of `unless-stopped`) to survive host reboots.

**Stop the stack:**

```bash
docker compose down
```

---

## 6. Frontend Build and Serving

The React dashboard must be built once and served statically (or via the Vite dev server for development).

**Development (Vite dev server — hot reload):**

```powershell
cd frontend
npm install
npm run dev
# Dashboard available at http://localhost:4180
```

**Production (static build):**

```powershell
cd frontend
npm install
npm run build
# Output: frontend/dist/
```

Serve `frontend/dist/` with any static file server. The simplest option on Windows is to use the Vite preview server:

```powershell
npm run preview --port 8088
```

For a real production deployment, serve `dist/` behind nginx or IIS and proxy `/api/*` to the API server on port 5000:

```nginx
# nginx snippet
location /api/ {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
}
location / {
    root /path/to/chain_gambler/frontend/dist;
    try_files $uri $uri/ /index.html;
}
```

---

## 7. Health Validation

After starting the server, run these checks before enabling live trading:

**API health check:**

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

Expected: `status: "ok"` with all component checks passing.

**Readiness probe (all components loaded):**

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health/ready
```

Expected: `ready: true`. This check fails until a champion model is promoted.

**System status:**

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/status | ConvertTo-Json -Depth 5
```

Look for `state: "online"`, `mode: "LIVE"` (if armed), and `risk.halt: false`.

**MT5 account connectivity:**

```powershell
(Invoke-RestMethod http://127.0.0.1:5000/api/status).account
```

Confirm `balance` and `equity` match your MT5 terminal.

**Smoke test script (if present):**

```powershell
python smoke_test.py
```

---

## 8. Process Supervision

### Option A — Docker restart policy (recommended for Docker deployments)

In `docker-compose.yml`, set:

```yaml
services:
  agi:
    restart: always   # Restart on crash and on host reboot
```

### Option B — Windows Task Scheduler

For the native Python deployment, create a scheduled task that starts on system boot:

1. Open Task Scheduler → Create Task.
2. General: Run whether user is logged on or not, Run with highest privileges.
3. Triggers: At startup, delay 30 seconds.
4. Actions: Start a program:
   - Program: `C:\path\to\project\.venv312\Scripts\python.exe`
   - Arguments: `-m Python.Server_AGI --live`
   - Start in: `C:\path\to\project\`
5. Settings: Restart if the task fails, attempt restart after 1 minute.

Create a separate task for the dashboard (`tools/project_status_ui.py`) following the same pattern.

### Option C — NSSM (Non-Sucking Service Manager)

```powershell
# Install NSSM, then:
nssm install ChainGamblerAGI "C:\path\to\.venv312\Scripts\python.exe"
nssm set ChainGamblerAGI AppParameters "-m Python.Server_AGI --live"
nssm set ChainGamblerAGI AppDirectory "C:\path\to\project"
nssm set ChainGamblerAGI AppStdout "C:\path\to\project\logs\agi_stdout.log"
nssm set ChainGamblerAGI AppStderr "C:\path\to\project\logs\agi_stderr.log"
nssm start ChainGamblerAGI
```

---

## 9. Log Locations and Rotation

| File | Contents |
|---|---|
| `logs/audit_events.jsonl` | Every trade, promotion, halt, and system event |
| `logs/trade_events.jsonl` | Closed trade history with PnL |
| `logs/learning/trade_learning_latest.json` | Rolling trade-memory metrics |
| `logs/lstm_progress.json` | LSTM training progress (updated during training) |
| `logs/ppo_progress.json` | PPO training progress |
| `logs/dreamer_progress.json` | Dreamer training progress |
| `logs/decisions.jsonl` | Per-decision log from the brain |
| `logs/patterns.jsonl` | Detected candlestick patterns |
| `logs/bot_stdout.log` | Bot process stdout (when started via API) |
| `logs/bot_stderr.log` | Bot process stderr |

**Log rotation:** Logs are append-only JSONL files and will grow unbounded. Set up rotation using Windows Task Scheduler or a cron job:

```powershell
# Example: rotate audit_events.jsonl weekly
$log = "logs\audit_events.jsonl"
$archive = "logs\archive\audit_events_$(Get-Date -Format 'yyyyMMdd').jsonl"
if (Test-Path $log) {
    Move-Item $log $archive
}
```

Alternatively, wrap the Python process with `logrotate` on Linux/Docker deployments.

---

## 10. Backup and Recovery

**Create a point-in-time backup (safe to commit):**

```powershell
python tools/create_migration_backup.py
# Output: backups/<timestamp>-vps-migration.zip (credentials redacted)
```

**API-triggered backup:**

```powershell
Invoke-RestMethod -Method POST http://127.0.0.1:5000/api/backup/create
```

**Check backup status:**

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/backup/status
```

**Recovery:**

1. Extract the backup zip to a fresh clone of the repo.
2. Restore `config.yaml` from your secrets store (never stored in backups).
3. Copy `models/` and `logs/` from the backup.
4. Run `python -m pytest` to verify the restored environment.
5. Start the server and confirm `/api/health/ready` returns `ready: true`.

**Critical files to back up separately (outside the script):**
- `config.yaml` (store in a password manager or secrets vault — never in git)
- `models/registry/active.json`
- `models/per_symbol/` (LSTM artifacts)
- `models/registry/` (PPO candidates and champion bundles)

---

## 11. Upgrading

```powershell
# 1. Pull the latest code
git pull origin main

# 2. Activate the venv
.venv312\Scripts\activate

# 3. Install any new dependencies
pip install -r requirements.txt

# 4. Rebuild the frontend (if frontend/ changed)
cd frontend
npm install
npm run build
cd ..

# 5. Run the test suite
.venv312\Scripts\python.exe -m pytest --tb=short -q

# 6. Restart the server
# Option A: Kill and restart the Python process via Task Scheduler or NSSM
nssm restart ChainGamblerAGI

# Option B: Use the API control endpoint
Invoke-RestMethod -Method POST http://127.0.0.1:5000/api/control `
  -Body '{"action":"restart_server"}' `
  -ContentType "application/json" `
  -Headers @{"X-Control-Token"="your-token-here"}

# 7. Validate health
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

**After a major update that changes model features (`feature_version`):**

The existing champion model may become incompatible with the new feature vector. Re-train before going live:

```powershell
python tools/champion_cycle.py
```

Wait for a new champion to be promoted (check `/api/learning`), then verify `/api/health/ready` returns `ready: true`.
