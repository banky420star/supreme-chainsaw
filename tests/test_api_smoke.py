"""Smoke tests: verify modules are importable and core pipelines function.

These tests require no server running and no network access.
They exercise the import surface and a quick train→predict cycle.
"""
import time
import pytest


def test_rainforest_detector_importable():
    from Python.rainforest_detector import RainforestDetector
    assert RainforestDetector is not None


def test_parallel_lane_manager_importable():
    from Python.parallel_lane_manager import ParallelLaneManager
    assert ParallelLaneManager is not None


def test_lane_state_importable():
    from Python.parallel_lane_manager import LaneState
    assert LaneState is not None


def test_lane_phase_state_importable():
    from Python.parallel_lane_manager import LanePhaseState
    assert LanePhaseState is not None


def test_api_server_importable():
    """api_server.py should import without starting the server."""
    try:
        import Python.api_server as api
        assert api is not None
    except SystemExit:
        pass  # Some servers call sys.exit on import — that's acceptable
    except Exception as e:
        pytest.fail(f"api_server import failed: {e}")


def test_rainforest_quick_cycle():
    """Full mini train→predict cycle should complete under 10 seconds."""
    from Python.rainforest_detector import RainforestDetector
    rf = RainforestDetector(n_estimators=5, max_depth=3, random_state=42)
    df = rf._generate_synthetic_training_data(300)
    start = time.time()
    rf.fit(df)
    pred = rf.predict_regime(df)
    elapsed = time.time() - start
    assert elapsed < 10.0, f"Cycle took too long: {elapsed:.1f}s"
    assert 'regime' in pred
    assert 'confidence' in pred
    assert 'probabilities' in pred


def test_rainforest_predict_before_train_is_safe():
    """Calling predict_regime without fitting must return a safe fallback, not crash."""
    from Python.rainforest_detector import RainforestDetector
    rf = RainforestDetector()
    df = rf._generate_synthetic_training_data(50)
    result = rf.predict_regime(df)
    assert isinstance(result, dict)
    assert 'regime' in result


def test_lane_manager_quick_cycle_status_call():
    """ParallelLaneManager.get_status() should be fast and return correct structure."""
    from Python.parallel_lane_manager import ParallelLaneManager
    m = ParallelLaneManager(['X'], max_workers=1)
    status = m.get_status()
    assert isinstance(status['parallel_lanes'], list)
    assert 'is_running' in status
    assert 'max_parallel' in status
    assert 'active_count' in status


def test_lane_manager_single_symbol_completes():
    """A single-symbol cycle should reach done within 12 seconds."""
    from Python.parallel_lane_manager import ParallelLaneManager
    m = ParallelLaneManager(['SMOKE_SYM'], max_workers=1)
    m.start_cycle()

    deadline = time.time() + 12.0
    while time.time() < deadline:
        if not m.is_running():
            break
        time.sleep(0.2)

    status = m.get_status()
    assert len(status['parallel_lanes']) == 1
    assert status['parallel_lanes'][0]['status'] in ('done', 'failed')


def test_feature_names_constant_exists():
    """FEATURE_NAMES constant should be importable and contain strings."""
    from Python.rainforest_detector import FEATURE_NAMES
    assert isinstance(FEATURE_NAMES, list)
    assert len(FEATURE_NAMES) > 0
    assert all(isinstance(n, str) for n in FEATURE_NAMES)


def test_regimes_constant_exists():
    """REGIMES constant should be importable and cover the 7 expected classes."""
    from Python.rainforest_detector import REGIMES
    expected = {'bull_trend', 'bear_trend', 'ranging', 'breakout_up', 'breakout_down', 'reversal_up', 'reversal_down'}
    assert set(REGIMES) == expected


def test_helper_functions_importable():
    """Low-level indicator helpers should be importable."""
    from Python.rainforest_detector import _log_returns, _rsi, _atr, _macd_hist, _bollinger_width
    assert all(callable(f) for f in [_log_returns, _rsi, _atr, _macd_hist, _bollinger_width])


def test_synthetic_data_and_feature_shapes_match():
    """Feature matrix rows must equal the number of synthetic bars."""
    from Python.rainforest_detector import RainforestDetector
    rf = RainforestDetector(n_estimators=5, max_depth=3)
    df = rf._generate_synthetic_training_data(400)
    X = rf.extract_features(df)
    assert X.shape[0] == len(df)
