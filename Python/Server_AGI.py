"""
Server AGI — Main engine with socket server, risk polling, and autonomy loop.
Works on both Windows (MT5 live) and Mac (dry-run dev mode).

Usage:
  python -m Python.Server_AGI          # dry-run dev mode
  python -m Python.Server_AGI --live   # live trading (Windows + MT5 only)
"""
import os
import sys
import time
import json
import socket
import asyncio
import threading
from datetime import datetime, date as datetime_date
from loguru import logger

# ── Conditional MT5 import ──────────────────────────────────────────
_mt5 = None
if sys.platform == "win32":
    try:
        import MetaTrader5 as mt5
        _mt5 = mt5
    except ImportError:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Python.risk_engine import RiskEngine
from Python.risk_supervisor import RiskSupervisor
from Python.mt5_executor import MT5Executor
from Python.hybrid_brain import HybridBrain
from Python.data_feed import get_latest_data, fetch_training_data
from Python.api_server import start_api_server, cache_decision
from Python.order_manager import OrderManager
from alerts.telegram_alerts import TelegramAlerter

# ── Logging ─────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(os.path.join(LOG_DIR, "server_agi.log"), rotation="10 MB", level="INFO")


class AGIServer:
    """Main server engine that coordinates brain, risk, and execution."""

    def __init__(self, live: bool = False):
        self.live = live
        self.live_armed = False  # Must be explicitly armed even in live mode
        if live:
            os.environ["AGI_IS_LIVE"] = "1"
            # Auto-arm if explicit arm is not required
            if os.environ.get("AGI_REQUIRE_EXPLICIT_LIVE_ARM", "true").lower() != "true":
                self.live_armed = True
                logger.info("Live mode auto-armed (AGI_REQUIRE_EXPLICIT_LIVE_ARM=false)")

        # Initialize MT5 if available
        if _mt5 is not None and live:
            if not _mt5.initialize():
                logger.error("MT5 failed to initialize — running in dry-run mode")
                self.live = False
            else:
                logger.success("MT5 connected successfully")

        # Core components
        self.risk = RiskEngine()
        self.risk_supervisor = RiskSupervisor()
        self.executor = MT5Executor(self.risk)
        self.executor.set_server_ref(self)  # Wire server ref for preflight checks
        self.brain = HybridBrain(self.risk, self.executor)
        self.risk_engine = self.risk  # Alias for AutonomyLoop compatibility
        self.order_manager = OrderManager(self.executor)

        # Socket server config
        self.host = os.environ.get("AGI_HOST", "127.0.0.1")
        self.port = int(os.environ.get("AGI_PORT", "9090"))
        self.token = os.environ.get("AGI_TOKEN", "").strip()

        # Trading symbols from config
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            self.symbols = cfg.get("trading", {}).get("symbols", ["EURUSD"])
        except Exception:
            self.symbols = ["EURUSD"]

        # Telegram alerter
        tel_cfg = (cfg or {}).get("telegram", {}) if isinstance(cfg, dict) else {}
        tel_token = os.environ.get("TELEGRAM_TOKEN", "") or str(tel_cfg.get("token", "")).strip()
        tel_chat = os.environ.get("TELEGRAM_CHAT_ID", "") or str(tel_cfg.get("chat_id", "")).strip()
        self.telegram = TelegramAlerter(tel_token or None, tel_chat or None)
        if self.telegram.token:
            logger.success(f"Telegram bot wired | chat_id={tel_chat}")
        else:
            logger.info("Telegram bot not configured — alerts disabled")

        self.start_time = time.time()
        self._equity_poll_interval = int(os.environ.get("AGI_EQUITY_POLL_SEC", "30"))
        self._trade_interval = int(os.environ.get("AGI_TRADE_INTERVAL_SEC", "900"))
        self._heartbeat_interval = int(os.environ.get("AGI_HEARTBEAT_SEC", "1800"))  # 30 min default
        logger.success(f"AGIServer initialized | live={self.live} | symbols={self.symbols} | trade_interval={self._trade_interval}s")

        # Start equity polling in background
        self._equity_thread = threading.Thread(target=self._equity_poll_loop, daemon=True)
        self._equity_thread.start()

        # Start autonomous trading loop in background
        self._trade_thread = threading.Thread(target=self._auto_trade_loop, daemon=True)
        self._trade_thread.start()

        # Start trailing stop manager in background
        self._trail_interval = int(os.environ.get("AGI_TRAIL_INTERVAL_SEC", "45"))
        self._trail_thread = threading.Thread(target=self._trailing_stop_loop, daemon=True)
        self._trail_thread.start()

        # Start Telegram heartbeat in background
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

    def handle_command(self, request: dict) -> dict:
        """Process a command from the socket server or n8n bridge."""
        # Token auth
        if self.token and request.get("token") != self.token:
            return {"error": "Invalid token", "action": "ERROR"}

        command = request.get("action", "").lower()
        symbol = request.get("symbol", self.symbols[0])

        if command == "arm_live":
            return self._arm_live()
        elif command == "disarm_live":
            self.live_armed = False
            logger.warning("Live mode DISARMED")
            return {"ok": True, "action": "DISARM_LIVE", "live_armed": False}

        if command == "predict":
            return self._handle_predict(symbol)
        elif command == "trade":
            return self._handle_trade(symbol)
        elif command == "health":
            return self._handle_health()
        elif command == "risk_status":
            return self._handle_risk_status()
        else:
            return {"error": f"Unknown command: {command}", "action": "ERROR"}

    def _arm_live(self) -> dict:
        """Arm live trading mode. Requires AGI_LIVE_ENABLED=true env var AND self.live=True."""
        if not self.live:
            return {"ok": False, "action": "ARM_LIVE", "error": "Server not started in live mode (--live flag required)"}
        live_enabled = os.environ.get("AGI_LIVE_ENABLED", "false").lower() == "true"
        require_explicit = os.environ.get("AGI_REQUIRE_EXPLICIT_LIVE_ARM", "true").lower() == "true"
        if require_explicit and not live_enabled:
            return {"ok": False, "action": "ARM_LIVE", "error": "AGI_LIVE_ENABLED env var must be 'true' to arm live trading"}
        self.live_armed = True
        logger.success("LIVE TRADING ARMED — orders will now be sent to MT5")
        try:
            self.telegram.risk_event("LIVE ARMED", "Live trading has been explicitly armed via API")
        except Exception:
            pass
        return {"ok": True, "action": "ARM_LIVE", "live_armed": True}

    def _handle_predict(self, symbol: str) -> dict:
        """Get prediction without executing."""
        try:
            df = fetch_training_data(symbol, period="5d", interval="5m")
            if df is None or df.empty or len(df) < 100:
                return {"error": f"Insufficient data for {symbol}", "action": "ERROR"}

            decision = self.brain.decide(symbol, df)
            cache_decision(symbol, decision)
            return decision
        except Exception as e:
            return {"error": str(e), "action": "ERROR"}

    def _handle_trade(self, symbol: str) -> dict:
        """Get prediction and execute."""
        try:
            df = fetch_training_data(symbol, period="5d", interval="5m")
            if df is None or df.empty or len(df) < 100:
                return {"error": f"Insufficient data for {symbol}", "action": "ERROR"}

            decision = self.brain.live_trade(
                symbol, df,
                risk_supervisor=self.risk_supervisor,
                max_positions_per_symbol=int(os.environ.get("AGI_MAX_POS_PER_SYMBOL", "5"))
            )
            result = decision if decision else {"action": "HOLD", "reason": "risk_blocked"}
            cache_decision(symbol, result)

            # Send Telegram alert for executed trades
            action = result.get("action", "HOLD")
            if action in ("BUY", "SELL"):
                try:
                    self.telegram.trade(
                        symbol=symbol,
                        action=action,
                        exposure=result.get("exposure", 0.0),
                        confidence=result.get("confidence", 0.0),
                        balance=getattr(self.risk, "_mt5_balance", 0) or 0,
                        equity=getattr(self.risk, "_current_equity", 0) or 0,
                        free_margin=getattr(self.risk, "_mt5_free_margin", 0) or 0,
                        sl=result.get("sl", 0),
                        tp=result.get("tp", 0),
                        tag=result.get("tag", ""),
                    )
                except Exception as e:
                    logger.debug(f"Telegram trade alert failed: {e}")

            return result
        except Exception as e:
            return {"error": str(e), "action": "ERROR"}

    def _handle_health(self) -> dict:
        uptime = int(time.time() - self.start_time)
        mt5_ok = _mt5 is not None and _mt5.initialize() if _mt5 else False
        return {
            "status": "OK",
            "action": "HEALTH",
            "uptime_sec": uptime,
            "mt5_connected": mt5_ok,
            "trading_enabled": not self.risk.halt,
            "daily_trades": self.risk.daily_trades,
            "realized_pnl": self.risk.realized_pnl_today,
            "mode": "LIVE" if self.live else "DRY-RUN",
        }

    def _handle_risk_status(self) -> dict:
        return {
            "action": "RISK_STATUS",
            "halt": self.risk.halt,
            "daily_trades": self.risk.daily_trades,
            "max_daily_trades": self.risk.max_daily_trades,
            "realized_pnl": self.risk.realized_pnl_today,
            "max_daily_loss": self.risk.max_daily_loss,
            "current_dd": self.risk.current_dd,
            "can_trade": self.risk.can_trade(),
        }

    def _equity_poll_loop(self):
        """Background thread: poll MT5 account equity and update the risk engine."""
        logger.info(f"Equity poll started (every {self._equity_poll_interval}s)")
        prev_halt = False
        _last_reset_date = datetime_date.today()
        while True:
            try:
                # Daily reset: reset risk engine counters at midnight
                today = datetime_date.today()
                if today != _last_reset_date:
                    logger.info(f"Daily risk reset: {_last_reset_date} -> {today}")
                    self.risk.reset_daily()
                    _last_reset_date = today

                equity = self._read_equity()
                if equity is not None and equity > 0:
                    self.risk.update_equity(equity)
                    logger.debug(f"Equity update: ${equity:.2f} | peak=${self.risk._peak_equity:.2f} | dd={self.risk.current_dd:.2f}%")
                    # Alert on risk halt activation
                    if self.risk.halt and not prev_halt:
                        try:
                            self.telegram.risk_event(
                                "RISK HALT ACTIVATED",
                                f"drawdown={self.risk.current_dd:.1f}% | daily_loss=${self.risk.realized_pnl_today:.2f} | trades={self.risk.daily_trades}"
                            )
                        except Exception:
                            pass
                    prev_halt = self.risk.halt
            except Exception as e:
                logger.warning(f"Equity poll error: {e}")
            time.sleep(self._equity_poll_interval)

    def _heartbeat_loop(self):
        """Background thread: periodic Telegram heartbeat and status snapshot."""
        logger.info(f"Telegram heartbeat started (every {self._heartbeat_interval}s)")
        # Wait for server to stabilize before first heartbeat
        time.sleep(60)
        while True:
            try:
                uptime = time.time() - self.start_time
                mt5_ok = _mt5 is not None and self.live
                equity = getattr(self.risk, "_current_equity", 0) or 0
                balance = getattr(self.risk, "_mt5_balance", 0) or 0
                profit = getattr(self.risk, "_mt5_profit", 0) or 0

                # Count open positions
                positions = 0
                if _mt5 is not None and self.live:
                    try:
                        if _mt5.initialize():
                            pos = _mt5.positions_get()
                            if pos:
                                positions = len(pos)
                            _mt5.shutdown()
                    except Exception:
                        pass

                self.telegram.heartbeat(
                    uptime=uptime,
                    mt5_connected=mt5_ok,
                    trading_enabled=not self.risk.halt,
                    equity=equity,
                    balance=balance,
                    positions=positions,
                    pnl=profit,
                )
            except Exception as e:
                logger.debug(f"Telegram heartbeat error: {e}")
            time.sleep(self._heartbeat_interval)

    def _read_equity(self) -> float | None:
        """Read current account equity from MT5 (Windows) or return None for dry-run.

        Also stores full account info on the risk engine for API access.
        """
        if _mt5 is not None and self.live:
            try:
                info = _mt5.account_info()
                if info is not None:
                    # Store full account info so the API can read it
                    self.risk._mt5_balance = float(info.balance)
                    self.risk._mt5_free_margin = float(info.margin_free)
                    self.risk._mt5_profit = float(info.profit)
                    return float(info.equity)
            except Exception as e:
                logger.debug(f"MT5 equity read failed: {e}")
                return None
        # Dry-run mode: no live equity feed — rely on initial bootstrap value
        return None

    def _trailing_stop_loop(self):
        """Background thread: manage trailing stops, breakeven, and partial closes via OrderManager."""
        logger.info(f"Order management loop started (every {self._trail_interval}s)")
        time.sleep(30)  # Let positions settle before first check
        while True:
            try:
                results = self.order_manager.manage_all_positions()
                for r in results:
                    if r.success:
                        logger.info(
                            f"OrderManager: {r.action} on {r.ticket} "
                            f"SL={r.old_sl:.5f}->{r.new_sl:.5f}"
                            + (f" closed={r.volume_closed:.2f}" if r.volume_closed else "")
                        )
            except Exception as e:
                logger.warning(f"Order management loop error: {e}")
            time.sleep(self._trail_interval)

    def _auto_trade_loop(self):
        """Background thread: scan ALL symbols each cycle for parallel lane-based trading."""
        logger.info(f"Auto-trade loop started (every {self._trade_interval}s, symbols={self.symbols})")
        # Initial delay to let models load
        time.sleep(15)
        _last_armed_log = 0
        while True:
            # In live mode, refuse to trade unless explicitly armed
            if self.live and not self.live_armed:
                now = time.time()
                if now - _last_armed_log > 60:
                    logger.warning("Live mode active but NOT ARMED — skipping trades. Send 'arm_live' action to enable.")
                    _last_armed_log = now
                time.sleep(self._trade_interval)
                continue
            for symbol in self.symbols:
                try:
                    result = self._handle_trade(symbol)
                    action = result.get("action", "UNKNOWN") if result else "ERROR"
                    reason = result.get("reason", "") if result else ""
                    exposure = result.get("exposure", 0.0) if result else 0.0
                    logger.info(f"AUTO-TRADE {symbol}: {action} | exposure={exposure:.4f} | {reason}")
                except Exception as e:
                    logger.warning(f"Auto-trade error for {symbol}: {e}")
            time.sleep(self._trade_interval)

    def run_socket_server(self):
        """Run the TCP socket server for n8n bridge communication."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        server.settimeout(1.0)  # Allow periodic checking
        logger.success(f"Socket server listening on {self.host}:{self.port}")

        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Socket server error: {e}")
                time.sleep(1)

    def _handle_connection(self, conn, addr):
        try:
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk

            raw = data.decode("utf-8", errors="replace").strip()
            if not raw:
                return

            request = json.loads(raw.split("\n")[0])
            response = self.handle_command(request)
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

        except Exception as e:
            error_resp = json.dumps({"error": str(e), "action": "ERROR"}) + "\n"
            try:
                conn.sendall(error_resp.encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()


def main(live=False):
    server = AGIServer(live=live)

    # Start HTTP API server for React dashboard (port 8088)
    start_api_server(server)

    # Start socket server in background
    socket_thread = threading.Thread(target=server.run_socket_server, daemon=True)
    socket_thread.start()

    # Optionally start autonomy loop
    try:
        from Python.autonomy_loop import AutonomyLoop
        autonomy = AutonomyLoop(server)
        server.autonomy = autonomy  # Wire for API control actions

        async def run_autonomy():
            await autonomy.start()

        logger.info("Starting AutonomyLoop...")
        asyncio.run(run_autonomy())

    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Autonomy loop error: {e}")
        # Fall back to simple heartbeat loop
        logger.info("Running in simple heartbeat mode...")
        while True:
            uptime = int(time.time() - server.start_time)
            logger.debug(f"Heartbeat: uptime={uptime}s trades={server.risk.daily_trades}")
            time.sleep(120)


if __name__ == "__main__":
    live_flag = "--live" in sys.argv or "--production" in sys.argv
    main(live=live_flag)
