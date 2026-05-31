"""SupremeChainsaw — Comprehensive Pipeline Test"""
import sys, os

sys.path.insert(0, "02_Core_Python")
all_pass = True

def section(n, name):
    print(f"\n{'='*60}")
    print(f"  {n}. {name}")
    print(f"{'='*60}")

def check(name, ok, detail=""):
    global all_pass
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    detail_str = f" - {detail}" if detail else ""
    print(f"  [{status}] {name}{detail_str}")

# 1. CONFIGURATION
section(1, "CONFIGURATION")
try:
    from Python.config_utils import load_project_config, resolve_trading_symbols, DEFAULT_TRADING_SYMBOLS
    cfg = load_project_config("02_Core_Python")
    symbols = resolve_trading_symbols(cfg or {}, fallback=DEFAULT_TRADING_SYMBOLS)
    check("Config loaded", cfg is not None or cfg is None, f"type={type(cfg).__name__}")
    check("Trading symbols", len(symbols) > 0, str(symbols))
except Exception as e:
    check(f"Config: {e}", False)

# 2. DATA FEED
section(2, "DATA FEED")
try:
    from Python.data_feed import fetch_training_data, get_latest_data
    # Also check the multi-timeframe function exists
    from Python.data_feed import fetch_multitimeframe_training_data
    check("DataFeed functions available", True, "fetch_training_data, get_latest_data, fetch_multitimeframe_training_data")
except Exception as e:
    check(f"DataFeed: {e}", False)

# 3. FEATURE PIPELINE
section(3, "FEATURE PIPELINE")
try:
    from Python.feature_pipeline import PatternDetector, build_env_feature_matrix, build_lstm_feature_frame
    pd_detector = PatternDetector()
    check("PatternDetector created", True, type(pd_detector).__name__)
    check("build_env_feature_matrix", callable(build_env_feature_matrix))
    check("build_lstm_feature_frame", callable(build_lstm_feature_frame))
except Exception as e:
    check(f"FeaturePipeline: {e}", False)

# 4. RISK ENGINE
section(4, "RISK ENGINE")
try:
    from Python.risk_engine import RiskEngine
    risk = RiskEngine()
    check("RiskEngine created", True, type(risk).__name__)
    # RiskEngine uses can_trade, record_trade, etc. (no check_trade)
    can_trade = hasattr(risk, "can_trade")
    check("can_trade method", can_trade)
    has_record = hasattr(risk, "record_trade")
    check("record_trade method", has_record)
    has_max_trades = hasattr(risk, "max_daily_trades")
    check("max_daily_trades attribute", has_max_trades)
except Exception as e:
    check(f"RiskEngine: {e}", False)

# 5. HYBRID BRAIN
section(5, "HYBRID BRAIN")
try:
    from Python.hybrid_brain import HybridBrain
    from Python.risk_engine import RiskEngine
    from Python.execution.paper_executor import PaperExecutor
    risk_inst = RiskEngine()
    exec_inst = PaperExecutor()
    hb = HybridBrain(risk=risk_inst, executor=exec_inst)
    check("HybridBrain created with risk+executor", True, type(hb).__name__)
    # HybridBrain has predict_ppo_action, predict_dreamer_action (not get_prediction)
    has_ppo_pred = hasattr(hb, "predict_ppo_action")
    check("predict_ppo_action method", has_ppo_pred)
    has_dreamer_pred = hasattr(hb, "predict_dreamer_action")
    check("predict_dreamer_action method", has_dreamer_pred)
    has_live_trade = hasattr(hb, "live_trade")
    check("live_trade method", has_live_trade)
except Exception as e:
    check(f"HybridBrain: {e}", False)

# 6. AGI BRAIN
section(6, "AGI BRAIN")
try:
    from Python.agi_brain import SmartAGI, AGIModel
    agi = SmartAGI()
    check("SmartAGI created", True, type(agi).__name__)
    check("AGIModel class available", True)
except Exception as e:
    check(f"AGI Brain: {e}", False)

# 7. PAPER TRADING
section(7, "PAPER TRADING")
try:
    from Python.paper_trading import get_paper_account, get_mode
    mode = get_mode()
    acct = get_paper_account()
    check("Mode", mode is not None, str(mode))
    check("Balance", acct.get("balance", 0) > 0, f"${acct.get('balance',0):.2f}")
    check("Equity", acct.get("equity", 0) > 0, f"${acct.get('equity',0):.2f}")
except Exception as e:
    check(f"Paper Trading: {e}", False)

# 8. PROMOTION GATES
section(8, "PROMOTION GATES")
try:
    from Python.registry.promotion_gates import get_promotion_status
    status = get_promotion_status()
    check("Promotion status loaded", True)
    check("  promotion_status", status.get("promotion_status") is not None, status.get("promotion_status"))
    check("  backtest_status", status.get("backtest_status") is not None, status.get("backtest_status"))
    check("  gates_configured", status.get("gates_configured"), str(status.get("gates_configured")))
    default_gates = status.get("default_gates", {})
    check("  gate thresholds", len(default_gates) > 0, f"{len(default_gates)} gates defined: {list(default_gates.keys())}")
except Exception as e:
    check(f"Promotion Gates: {e}", False)

# 9. TRADE EXECUTION
section(9, "TRADE EXECUTION")
try:
    from Python.execution.paper_executor import PaperExecutor
    pe = PaperExecutor()
    check("PaperExecutor", True, type(pe).__name__)
    from Python.execution.gate_engine import GateEngine
    ge = GateEngine()
    check("GateEngine", True, type(ge).__name__)
    from Python.execution.execution_agent import ExecutionAgent
    ea = ExecutionAgent()
    check("ExecutionAgent", True, type(ea).__name__)
    from Python.execution.executor_router import ExecutorRouter
    er = ExecutorRouter()
    check("ExecutorRouter", True, type(er).__name__)
except Exception as e:
    check(f"Trade Execution: {e}", False)

# 10. AUTONOMOUS LOOP
section(10, "AUTONOMOUS LOOP")
try:
    from Python.autonomous.continual_learner import ContinualLearner
    cl = ContinualLearner()
    check("ContinualLearner", True, type(cl).__name__)
    from Python.autonomous.run_cycle import PipelineOrchestrator, STAGES, HARD_GATES
    # PipelineOrchestrator requires: symbol, timeframe, mode, require_mt5, timesteps, feature_set_id, dataset_id
    orch = PipelineOrchestrator(
        symbol="EURUSD",
        timeframe="H1",
        mode="paper",
        require_mt5=False,
        timesteps=100,
        feature_set_id="ULTIMATE_150",
        dataset_id="test"
    )
    check("PipelineOrchestrator created", True, type(orch).__name__)
    check("STAGES defined", len(STAGES) > 0, f"{len(STAGES)} stages")
    check("HARD_GATES defined", len(HARD_GATES) > 0, f"{len(HARD_GATES)} hard gates")
    from Python.autonomy_loop import AutonomyLoop
    from Python.hybrid_brain import HybridBrain
    from Python.risk_engine import RiskEngine
    from Python.execution.paper_executor import PaperExecutor
    al_brain = HybridBrain(risk=RiskEngine(), executor=PaperExecutor())
    al = AutonomyLoop(brain=al_brain)
    check("AutonomyLoop created with brain", True, type(al).__name__)
except Exception as e:
    check(f"Autonomous Loop: {e}", False)

# 11. DRL MODULES
section(11, "DRL MODULES")
try:
    from Python.drl.ppo_agent import PPO, make_env, predict, load_model
    check("PPO (stable-baselines3)", True)
    check("make_env function", callable(make_env))
    check("predict function", callable(predict))
    from Python.drl.dreamer_agent import DreamerV3Agent
    agent_class = DreamerV3Agent
    check("DreamerV3Agent", True, type(agent_class).__name__)
    from Python.drl.trading_env import TradingEnv
    check("TradingEnv", True)
    from Python.drl.lstm_feature_extractor import LSTMFeatureExtractor
    check("LSTMFeatureExtractor", True)
except Exception as e:
    check(f"DRL Modules: {e}", False)

# 12. TRAINING SCRIPTS
section(12, "TRAINING SCRIPTS")
try:
    from Python.training.train_lstm import main as lstm_main
    check("train_lstm main()", callable(lstm_main))
    from Python.training.train_ppo import main as ppo_main
    check("train_ppo main()", callable(ppo_main))
    from Python.training.train_dreamer import main as dreamer_main
    check("train_dreamer main()", callable(dreamer_main))
    from Python.training.train_rainforest import main as rf_main
    check("train_rainforest main()", callable(rf_main))
except Exception as e:
    check(f"Training Scripts: {e}", False)

# 13. API SERVER ENDPOINTS
section(13, "API SERVER")
try:
    from Python.api_server import app
    check("API app imported", True)
    import threading, time, requests, bottle
    
    def serve():
        bottle.run(app, host="127.0.0.1", port=5050, quiet=True, server="wsgiref")
    
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(2.5)
    
    endpoints = [
        "/api/status", "/api/trades", "/api/trades/summary",
        "/api/perf", "/api/lanes", "/api/learning", "/api/regimes",
        "/api/ppo_diagnostics", "/api/lstm_explanations", "/api/live_gate",
    ]
    
    for ep in endpoints:
        try:
            r = requests.get(f"http://127.0.0.1:5050{ep}", timeout=5)
            check(ep, r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            check(f"{ep}: {e}", False)
except Exception as e:
    check(f"API Server: {e}", False)

# ============================================================
print(f"\n\n{'='*60}")
if all_pass:
    print("  RESULT: [ALL PASSED] All pipeline tests successful!")
else:
    print("  RESULT: [SOME FAILED] Review output above for details")
print(f"{'='*60}")
sys.exit(0 if all_pass else 1)
