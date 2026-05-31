"""Stub Telegram alerter for when telegram is not configured."""
import logging

logger = logging.getLogger(__name__)

class TelegramAlerter:
    """Stub alerter that logs messages but doesn't send to Telegram."""

    def __init__(self, token=None, chat_id=None, enabled=False):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled
        self._queue = []

    def send(self, message, level="INFO", image_path=None):
        """Log the message instead of sending to Telegram."""
        logger.info(f"[TELEGRAM {level}] {message}")
        self._queue.append({"message": message, "level": level, "ts": __import__('time').time()})
        return True

    def notify_trade(self, symbol, direction, volume, price, sl=None, tp=None, pnl=None):
        """Log trade notification."""
        msg = f"Trade: {direction} {volume} {symbol} @ {price}"
        if pnl is not None:
            msg += f" | PnL: ${pnl:.2f}"
        logger.info(f"[TELEGRAM TRADE] {msg}")
        return True

    def notify_error(self, error_msg):
        """Log error notification."""
        logger.error(f"[TELEGRAM ERROR] {error_msg}")
        return True

    def notify_daily_summary(self, stats):
        """Log daily summary."""
        logger.info(f"[TELEGRAM SUMMARY] {stats}")
        return True

    def flush_queue(self):
        """No-op for stub."""
        count = len(self._queue)
        self._queue.clear()
        return count

    def online(self, msg=None):
        """Log online status."""
        logger.info(f"[TELEGRAM ONLINE] {msg or 'Trading engine online'}")
        return True

    def offline(self, msg=None):
        """Log offline status."""
        logger.info(f"[TELEGRAM OFFLINE] {msg or 'Trading engine offline'}")
        return True

    def heartbeat_full(self, **kwargs):
        """Log heartbeat."""
        status = kwargs.get('status', 'unknown')
        logger.debug(f"[TELEGRAM HEARTBEAT] Status: {status}")
        return True

    def notify_incident(self, incident_type, message, severity="info"):
        """Log incident notification."""
        logger.info(f"[TELEGRAM INCIDENT:{severity}] {incident_type}: {message}")
        return True

    def alert(self, message, level="WARNING"):
        """Log alert."""
        logger.warning(f"[TELEGRAM ALERT:{level}] {message}")
        return True

    def snapshot(self, **kwargs):
        """Log snapshot."""
        logger.debug(f"[TELEGRAM SNAPSHOT] {kwargs}")
        return True

    def trade(self, symbol, direction, volume, price, sl=None, tp=None, pnl=None, **kwargs):
        """Log trade execution."""
        msg = f"TRADE OPEN: {direction} {volume} {symbol} @ {price}"
        if sl:
            msg += f" SL:{sl}"
        if tp:
            msg += f" TP:{tp}"
        logger.info(f"[TELEGRAM TRADE] {msg}")
        return True

    def trade_closed(self, symbol, direction, pnl, exit_price=None, **kwargs):
        """Log trade close."""
        emoji = "✅" if pnl and pnl > 0 else "❌"
        logger.info(f"[TELEGRAM CLOSE] {emoji} {direction} {symbol} @ {exit_price or 'unknown'} | PnL: ${pnl:.2f}")
        return True

    def model(self, message, **kwargs):
        """Log model change."""
        logger.info(f"[TELEGRAM MODEL] {message}")
        return True

    def profitability_daily(self, learn_stats, **kwargs):
        """Log daily profitability."""
        logger.info(f"[TELEGRAM PROFIT] Daily stats: {learn_stats}")
        return True

    def trade_action(self, symbol, order_meta, **kwargs):
        """Log trade action."""
        action = order_meta.get('action', 'unknown') if isinstance(order_meta, dict) else str(order_meta)
        logger.info(f"[TELEGRAM ACTION] {symbol}: {action}")
        return True

    def symbol_status(self, symbol, state, **kwargs):
        """Log symbol status."""
        logger.info(f"[TELEGRAM SYMBOL] {symbol}: {state}")
        return True

    def training(self, trainer_type, message, **kwargs):
        """Log training status."""
        logger.info(f"[TELEGRAM TRAINING:{trainer_type}] {message}")
        return True
