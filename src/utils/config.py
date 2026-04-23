"""Centralized configuration loading.

Loads configuration from per-symbol YAML files and the main config.yaml.
Provides a single Config object that all modules can import.
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Any

from src.utils.paths import CONFIG_DIR, PROJECT_ROOT


# Singleton config instance
_config = None


class Config:
    """Central configuration manager.

    Loads and merges:
    1. Main config.yaml (global settings)
    2. Per-symbol configs/*.yaml (symbol-specific overrides)

    Per-symbol configs take precedence over global settings.
    """

    def __init__(self, config_path: str = None):
        self._global = {}
        self._symbols = {}
        self._loaded = False

        if config_path is None:
            config_path = os.path.join(CONFIG_DIR, "config.yaml")

        self._load(config_path)

    def _load(self, config_path: str):
        """Load global config and all per-symbol configs."""
        # Load global config
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self._global = yaml.safe_load(f) or {}
        else:
            # Try legacy path
            legacy_path = os.path.join(PROJECT_ROOT, "config.yaml")
            if os.path.exists(legacy_path):
                with open(legacy_path, "r", encoding="utf-8") as f:
                    self._global = yaml.safe_load(f) or {}

        # Load per-symbol configs
        configs_dir = CONFIG_DIR
        if os.path.isdir(configs_dir):
            for filename in os.listdir(configs_dir):
                if filename.endswith((".yaml", ".yml")) and filename != "config.yaml":
                    symbol = filename.rsplit(".", 1)[0]
                    filepath = os.path.join(configs_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        self._symbols[symbol] = yaml.safe_load(f) or {}

        self._loaded = True

    def get(self, key: str, default: Any = None) -> Any:
        """Get a global config value by dot-notation key.

        Example: config.get("risk.max_daily_loss", 500)
        """
        return self._resolve(key, self._global, default)

    def symbol(self, symbol: str, key: str = None, default: Any = None) -> Any:
        """Get a per-symbol config value.

        Falls back to global config if not found in symbol config.

        Args:
            symbol: Symbol name (e.g. "EURUSDm")
            key: Dot-notation key (e.g. "risk.max_lots")
            default: Default value if key not found
        """
        sym_cfg = self._symbols.get(symbol, {})
        if key is None:
            # Return merged config for this symbol
            merged = {**self._global, **sym_cfg}
            return merged

        # Try symbol config first, then global
        val = self._resolve(key, sym_cfg)
        if val is not None:
            return val
        return self._resolve(key, self._global, default)

    def symbols(self) -> list:
        """Get list of configured symbols."""
        return list(self._symbols.keys())

    @staticmethod
    def _resolve(key: str, d: dict, default: Any = None) -> Any:
        """Resolve a dot-notation key from a nested dict."""
        keys = key.split(".")
        current = d
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current

    def reload(self):
        """Reload all configs from disk."""
        self._global = {}
        self._symbols = {}
        self._load(os.path.join(CONFIG_DIR, "config.yaml"))


def get_config() -> Config:
    """Get the singleton Config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config