"""Project path constants and directory resolution."""
import os

# Project root is chain_gambler/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Standard directories
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DATA_RAW_DIR = os.path.join(DATA_DIR, "raw")
DATA_PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
DATA_CACHE_DIR = os.path.join(DATA_DIR, "cache")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
LOGS_DIR = os.path.join(PROJECT_ROOT, "outputs", "logs")
BACKTESTS_DIR = os.path.join(PROJECT_ROOT, "outputs", "backtests")
TESTER_RUNS_DIR = os.path.join(PROJECT_ROOT, "outputs", "tester_runs")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "outputs", "model_checkpoints")
CHARTS_DIR = os.path.join(PROJECT_ROOT, "outputs", "charts")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "outputs", "reports")

# Legacy paths (backward compat)
LEGACY_CONFIG = os.path.join(PROJECT_ROOT, "config.yaml")
LEGACY_CONFIGS_DIR = os.path.join(PROJECT_ROOT, "configs")
LEGACY_PYTHON_DIR = os.path.join(PROJECT_ROOT, "Python")
LEGACY_DRL_DIR = os.path.join(PROJECT_ROOT, "drl")
LEGACY_TRAINING_DIR = os.path.join(PROJECT_ROOT, "training")


def ensure_dirs():
    """Create all standard directories if they don't exist."""
    for d in [CONFIG_DIR, DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_CACHE_DIR,
              MODELS_DIR, LOGS_DIR, BACKTESTS_DIR, TESTER_RUNS_DIR,
              CHECKPOINTS_DIR, CHARTS_DIR, REPORTS_DIR]:
        os.makedirs(d, exist_ok=True)