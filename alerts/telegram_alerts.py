import json
import os
import time
from datetime import datetime, timezone


class TelegramAlerter:
    """Telegram bot for trade alerts, heartbeats, and status snapshots."""

    def __init__(self, token, chat_id, cards_state_path=None):
        self.token = token
        self.chat_id = chat_id
        self.last_sent = {}
        self._last_api_error = None
        self._api = None  # Override for testing
        self._cards_path = cards_state_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs", "telegram_cards.json"
        )
        self._cards = self._load_cards()

    # ── Card persistence ──────────────────────────────────────────────

    def _load_cards(self):
        try:
            if os.path.exists(self._cards_path):
                with open(self._cards_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_cards(self):
        try:
            os.makedirs(os.path.dirname(self._cards_path), exist_ok=True)
            with open(self._cards_path, "w") as f:
                json.dump(self._cards, f, indent=2)
        except Exception:
            pass

    def state_summary(self, limit=14):
        cards = self._cards
        items = []
        for key, val in cards.items():
            if isinstance(val, dict) and "message_id" in val:
                items.append({
                    "category": key,
                    "message_id": val["message_id"],
                    "delivery_status": val.get("delivery_status", "dashboard_only"),
                })
        return {"card_count": len(items), "cards": items[:limit]}

    # ── Core send ──────────────────────────────────────────────────────

    def _send(self, text):
        if not self.token or not self.chat_id:
            return None
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        try:
            import requests
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json() if resp.status_code == 200 else {}
            if resp.status_code == 429:
                retry_after = (data or {}).get("parameters", {}).get("retry_after", 60)
                self._last_api_error = {
                    "status_code": 429,
                    "retry_after": retry_after,
                    "body": data,
                }
                return None
            msg_id = data.get("result", {}).get("message_id")
            return msg_id
        except Exception:
            return None

    def _record_card(self, category, msg_id, text):
        if msg_id:
            self._cards[category] = {
                "message_id": msg_id,
                "delivery_status": "both",
                "category": category,
                "last_text": text[:200],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        else:
            self._cards[category] = {
                "message_id": None,
                "delivery_status": "dashboard_only",
                "category": category,
                "last_text": text[:200],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        self._save_cards()

    # ── Alert methods ──────────────────────────────────────────────────

    def heartbeat(self, uptime, mt5_connected, trading_enabled, equity=None, balance=None, positions=0, pnl=0.0):
        uptime_str = f"{int(uptime)//3600}h {int(uptime)%3600//60}m"
        lines = [
            "<b>💓 HEARTBEAT</b>",
            f"Uptime: {uptime_str}",
            f"MT5: {'✅ CONNECTED' if mt5_connected else '❌ DISCONNECTED'}",
            f"Trading: {'✅ ENABLED' if trading_enabled else '⛔ HALTED'}",
        ]
        if equity is not None:
            lines.append(f"Equity: ${equity:,.2f}")
        if balance is not None:
            lines.append(f"Balance: ${balance:,.2f}")
        if positions:
            lines.append(f"Open Positions: {positions}")
        if pnl != 0.0:
            emoji = "📈" if pnl >= 0 else "📉"
            lines.append(f"{emoji} Floating PnL: ${pnl:,.2f}")
        lines.append(f"Time: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("heartbeat", msg_id, text)
        return msg_id

    def trade(self, symbol, action, exposure, confidence, balance, equity, free_margin, sl=0, tp=0, tag=""):
        lines = [
            f"<b>📈 TRADE EXECUTED</b>",
            f"Symbol: <b>{symbol}</b>",
            f"Action: <b>{action}</b>",
            f"Exposure: {exposure:.4f}",
            f"Confidence: {confidence:.3f}",
        ]
        if sl:
            lines.append(f"SL: ${sl:,.2f}")
        if tp:
            lines.append(f"TP: ${tp:,.2f}")
        if tag:
            lines.append(f"Tag: {tag}")
        lines.extend([
            f"Balance: ${balance:,.2f}",
            f"Equity: ${equity:,.2f}",
            f"Free Margin: ${free_margin:,.2f}",
        ])
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("trade", msg_id, text)
        return msg_id

    def trade_close(self, symbol, action, profit, balance, equity, reason=""):
        emoji = "✅" if profit >= 0 else "❌"
        lines = [
            f"<b>{emoji} TRADE CLOSED</b>",
            f"Symbol: <b>{symbol}</b>",
            f"Action: {action}",
            f"PnL: ${profit:,.2f}",
        ]
        if reason:
            lines.append(f"Reason: {reason}")
        lines.extend([
            f"Balance: ${balance:,.2f}",
            f"Equity: ${equity:,.2f}",
        ])
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("trade_close", msg_id, text)
        return msg_id

    def snapshot(self, balance, equity, pnl_today, floating, open_positions):
        lines = [
            "<b>📊 STATUS SNAPSHOT</b>",
            f"Balance: ${balance:,.2f}",
            f"Equity: ${equity:,.2f}",
            f"PnL Today: ${pnl_today:,.2f}",
            f"Floating: ${floating:,.2f}",
            f"Open Positions: {open_positions}",
        ]
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("snapshot", msg_id, text)
        return msg_id

    def model(self, message):
        text = f"🧠 MODEL UPDATE\n{message}"
        msg_id = self._send(text)
        self._record_card("model", msg_id, text)
        return msg_id

    def alert(self, message):
        text = f"⚠️ ALERT\n{message}"
        msg_id = self._send(text)
        self._record_card("alerts", msg_id, text)
        return msg_id

    def risk_event(self, event_type, details=""):
        lines = [
            f"<b>🛡️ RISK EVENT</b>",
            f"Type: {event_type}",
        ]
        if details:
            lines.append(f"Details: {details}")
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("risk", msg_id, text)
        return msg_id

    def training_cycle(self, status, symbols, result=None, detail=""):
        lines = [
            f"<b>🔄 TRAINING {status.upper()}</b>",
            f"Symbols: {', '.join(symbols)}",
        ]
        if result:
            mode = result.get("mode", "unknown")
            lines.append(f"Mode: {mode}")
            sym_results = result.get("symbols", [])
            for sr in sym_results:
                sym = sr.get("symbol", "?")
                won = sr.get("wins", False)
                passed = sr.get("passes_thresholds", False)
                status_icon = "✅" if won else "❌"
                lines.append(f"  {sym}: {status_icon} wins={won} passes={passed}")
        if detail:
            lines.append(detail)
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("training_cycle", msg_id, text)
        return msg_id is not None

    def sl_hit(self, symbol, loss, balance, equity, cooldown_min=15):
        lines = [
            f"<b>🛑 STOP-LOSS HIT</b>",
            f"Symbol: <b>{symbol}</b>",
            f"Loss: ${loss:,.2f}",
            f"Cooldown: {cooldown_min} min",
            f"Balance: ${balance:,.2f}",
            f"Equity: ${equity:,.2f}",
        ]
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("sl_hit", msg_id, text)
        return msg_id

    def trailing_stop_moved(self, symbol, position_ticket, old_sl, new_sl, locked_profit):
        lines = [
            f"<b>📐 TRAILING STOP</b>",
            f"Symbol: {symbol}",
            f"Ticket: #{position_ticket}",
            f"SL moved: ${old_sl:,.2f} → ${new_sl:,.2f}",
            f"Locked profit: ${locked_profit:,.2f}",
        ]
        text = "\n".join(lines)
        msg_id = self._send(text)
        self._record_card("trailing", msg_id, text)
        return msg_id