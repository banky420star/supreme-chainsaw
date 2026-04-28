"""Start the AGI trading server with live mode and all env vars."""
import os
import sys

# Set all environment variables before importing server
os.environ["AGI_BIAS_STRENGTH"] = "0.3"
os.environ["AGI_LOW_VOL_MIN_ACTION"] = "0.0001"
os.environ["AGI_MED_VOL_MIN_ACTION"] = "0.0001"
os.environ["AGI_HIGH_VOL_MIN_ACTION"] = "0.0001"
os.environ["AGI_ACTION_THRESHOLD"] = "0.0001"
os.environ["AGI_TRADE_INTERVAL_SEC"] = "30"
os.environ["CANARY_MAX_LOSS_PCT"] = "10"
os.environ["AGI_LIVE_ENABLED"] = "true"
os.environ["AGI_REQUIRE_EXPLICIT_LIVE_ARM"] = "false"
os.environ["AGI_TRAIL_INTERVAL_SEC"] = "15"
os.environ["AGI_HEDGING_ENABLED"] = "true"
os.environ["AGI_TREND_FLIP_ENABLED"] = "true"
os.environ["AGI_NEG_TIMEOUT_MIN"] = "60"
os.environ["AGI_RISK_PERCENT"] = "1.0"
os.environ["AGI_MIN_LOTS"] = "0.02"
os.environ["AGI_MAX_POS_PER_SYMBOL"] = "5"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force --live in sys.argv
if "--live" not in sys.argv:
    sys.argv.append("--live")

from Python.Server_AGI import main
main(live=True)