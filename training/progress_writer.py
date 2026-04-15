"""Atomic training progress writer for API consumption."""
import json
import os
import time

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1  # seconds


def update_training_progress(trainer_key, data, symbol=None):
    """Write progress for a single trainer to its own JSON file.

    Args:
        trainer_key: "lstm", "ppo", or "dreamer"
        data: dict with progress fields (running, symbol, epoch, loss, etc.)
        symbol: optional per-symbol key to avoid file contention during parallel training
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    if symbol and trainer_key == "ppo":
        path = os.path.join(LOGS_DIR, f"ppo_{symbol}_progress.json")
    else:
        path = os.path.join(LOGS_DIR, f"{trainer_key}_progress.json")
    payload = {**data, "updated_at": time.time()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    # On Windows, os.replace can fail with PermissionError if another process
    # is reading the file. Retry with a short delay.
    for attempt in range(_MAX_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)
            else:
                # Fallback: write directly (non-atomic but better than crashing)
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
