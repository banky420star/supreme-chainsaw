"""Centralized MT5 compatibility import.

Handles the conditional import pattern used across the project.
On Windows, MetaTrader5 is available. On Mac/Linux, it gracefully degrades.
"""
import os
import sys

_mt5 = None
_mt5_available = False

if os.name == "nt":
    try:
        import MetaTrader5 as mt5
        _mt5 = mt5
        _mt5_available = True
    except ImportError:
        pass


def is_mt5_available() -> bool:
    """Check if MT5 is available on this platform."""
    return _mt5_available


def get_mt5():
    """Get the MT5 module, or None if not available."""
    return _mt5


def mt5_initialized() -> bool:
    """Check if MT5 is initialized and connected."""
    if _mt5 is None:
        return False
    try:
        return _mt5.initialize()
    except Exception:
        return False