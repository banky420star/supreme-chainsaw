# Supreme Chainsaw - Demo Trading Bot

## Quick Start

Double-click **`START_DEMO_BOT.bat`** on your Desktop to launch the full stack.

## What Was Fixed

1. **Created alerts module stub** (`02_Core_Python/alerts/telegram_alerts.py`)
   - The bot was crashing because the Telegram alerts module was missing
   - Created a stub that logs to console instead of sending to Telegram

2. **Fixed feature size mismatch** (`Python/agi_brain.py`)
   - The LSTM model expected 17 features but the pipeline generated 150
   - Updated to auto-detect the correct feature count

3. **Fixed React syntax error** (`TrainingScorecard.jsx:345`)
   - Changed `training.per_symbol?.?.[symbol]` to `training.per_symbol?.[symbol]`

## Services Running

| Service | Port | Description |
|---------|------|-------------|
| API Server | 5051 | Backend API for dashboard |
| Trading Bot | - | Server_AGI making trading decisions |
| React UI | 4180 | Dashboard interface |

## Account Info

- **Login**: 435656990
- **Server**: Exness-MT5Trial9
- **Balance**: $100.00 (Demo)
- **Mode**: DEMO (No real money risk)

## Status Check

Once running, check status at:
- API: http://localhost:5051/api/status
- Dashboard: http://localhost:4180

## Manual Start (if needed)

If the batch file doesn't work, you can start manually:

1. Start API Server:
```powershell
cd "02_Core_Python"
..\.venv312\Scripts\python.exe -m Python.api_server
```

2. Start Trading Bot:
```powershell
cd "02_Core_Python"
$env:CHAIN_GAMBLER_EXECUTION_MODE="demo"
$env:AGI_LIVE_ENABLED="true"
$env:MT5_LOGIN="435656990"
$env:MT5_PASSWORD="Fuckyou2/"
$env:MT5_SERVER="Exness-MT5Trial9"
..\.venv312\Scripts\python.exe -m Python.Server_AGI
```

3. Start React UI:
```powershell
cd "03_UI_Monitoring"
npm run dev -- --port 4180
```

## Troubleshooting

- **MT5 not connected**: Make sure MetaTrader 5 is running
- **Module not found**: The alerts module is now included
- **Port in use**: Change ports in config or kill existing processes

## Current Status

The bot is now running and making trading decisions on 4 symbols:
- BTCUSDm (Bitcoin)
- XAUUSDm (Gold)
- EURUSDm (Euro/USD)
- GBPUSDm (Pound/USD)

Decisions show as "HOLD" when confidence is below trading threshold.
