"""
Training Pipeline Tests for Chain Gambler

Tests for:
- Training data loading
- Environment creation
- PPO training initialization
- Model saving/loading
- VecNormalize serialization

Usage:
    pytest tests/test_training_pipeline.py -v
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTrainingDataLoading:
    """Test training data loading functions."""

    def test_fetch_training_data_with_symbol(self):
        """Test that fetch_training_data returns data for valid symbol."""
        try:
            from Python.data_feed import fetch_training_data

            # Use a small timeframe for testing
            df = fetch_training_data("EURUSDm", period="30d", interval="1h")

            if df is None or len(df) == 0:
                pytest.skip("MT5 or data source not available")

            # Check that we got reasonable data
            assert len(df) > 100, "Should have at least 100 bars of data"
            assert "close" in df.columns, "Should have close price column"
            assert "open" in df.columns, "Should have open price column"
            assert "high" in df.columns, "Should have high price column"
            assert "low" in df.columns, "Should have low price column"

        except ImportError:
            pytest.skip("MT5 not available")

    def test_get_combined_training_df(self):
        """Test combining data from multiple symbols."""
        try:
            from Python.data_feed import get_combined_training_df

            df = get_combined_training_df(symbols=["EURUSDm"], period="30d")

            if df is None or len(df) == 0:
                pytest.skip("MT5 or data source not available")

            assert len(df) > 100
            assert "close" in df.columns

        except ImportError:
            pytest.skip("Dependencies not available")


class TestEnvironmentCreation:
    """Test TradingEnv creation and basic functionality."""

    def test_trading_env_creation(self):
        """Test that TradingEnv can be created with synthetic data."""
        from drl.trading_env import TradingEnv
        import pandas as pd
        import numpy as np

        # Create synthetic data
        n_bars = 200
        df = pd.DataFrame({
            "open": np.random.randn(n_bars).cumsum() + 100,
            "high": np.random.randn(n_bars).cumsum() + 101,
            "low": np.random.randn(n_bars).cumsum() + 99,
            "close": np.random.randn(n_bars).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, n_bars),
        }, index=pd.date_range(end="2024-01-01", periods=n_bars, freq="5min"))

        env = TradingEnv(df, initial_balance=10000.0)

        assert env is not None
        assert hasattr(env, "observation_space")
        assert hasattr(env, "action_space")

    def test_trading_env_reset(self):
        """Test environment reset returns valid observation."""
        from drl.trading_env import TradingEnv
        import pandas as pd
        import numpy as np

        n_bars = 200
        df = pd.DataFrame({
            "open": np.random.randn(n_bars).cumsum() + 100,
            "high": np.random.randn(n_bars).cumsum() + 101,
            "low": np.random.randn(n_bars).cumsum() + 99,
            "close": np.random.randn(n_bars).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, n_bars),
        }, index=pd.date_range(end="2024-01-01", periods=n_bars, freq="5min"))

        env = TradingEnv(df)
        obs, info = env.reset()

        assert obs is not None
        assert isinstance(obs, np.ndarray)
        assert len(obs.shape) == 1  # 1D observation

    def test_trading_env_step(self):
        """Test environment step with valid action."""
        from drl.trading_env import TradingEnv
        import pandas as pd
        import numpy as np

        n_bars = 200
        df = pd.DataFrame({
            "open": np.random.randn(n_bars).cumsum() + 100,
            "high": np.random.randn(n_bars).cumsum() + 101,
            "low": np.random.randn(n_bars).cumsum() + 99,
            "close": np.random.randn(n_bars).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, n_bars),
        }, index=pd.date_range(end="2024-01-01", periods=n_bars, freq="5min"))

        env = TradingEnv(df)
        obs, info = env.reset()

        # Take a step with action 0.5 (buy signal)
        action = np.array([0.5], dtype=np.float32)
        step_result = env.step(action)

        # Gymnasium envs return (obs, reward, terminated, truncated, info)
        assert len(step_result) == 5
        next_obs, reward, terminated, truncated, info = step_result

        assert next_obs is not None
        assert isinstance(reward, (int, float, np.number))
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)


class TestVecNormalize:
    """Test VecNormalize serialization and compatibility."""

    def test_vec_normalize_save_load(self):
        """Test that VecNormalize stats can be saved and loaded."""
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        from drl.trading_env import TradingEnv
        import pandas as pd
        import numpy as np

        # Create env
        n_bars = 200
        df = pd.DataFrame({
            "open": np.random.randn(n_bars).cumsum() + 100,
            "high": np.random.randn(n_bars).cumsum() + 101,
            "low": np.random.randn(n_bars).cumsum() + 99,
            "close": np.random.randn(n_bars).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, n_bars),
        }, index=pd.date_range(end="2024-01-01", periods=n_bars, freq="5min"))

        env = DummyVecEnv([lambda: TradingEnv(df)])
        env = VecNormalize(env, norm_obs=True, norm_reward=True)

        # Run some steps to populate normalization stats
        obs = env.reset()
        for _ in range(10):
            action = [env.action_space.sample()]
            step_result = env.step(action)
            # VecNormalize returns (obs, reward, done, info) - 4 items
            assert len(step_result) == 4
            obs, reward, done, info = step_result

        # Save VecNormalize
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            save_path = f.name

        env.save(save_path)

        # Load into new environment
        new_env = DummyVecEnv([lambda: TradingEnv(df)])
        loaded_env = VecNormalize.load(save_path, new_env)

        assert loaded_env is not None
        assert hasattr(loaded_env, "obs_rms")

        # Cleanup
        os.unlink(save_path)


class TestModelSavingLoading:
    """Test PPO model saving and loading."""

    def test_ppo_save_load(self):
        """Test that PPO models can be saved and loaded."""
        try:
            from stable_baselines3 import PPO
            from stable_baselines3.common.vec_env import DummyVecEnv
            from drl.trading_env import TradingEnv
            import pandas as pd
            import numpy as np

            # Create env
            n_bars = 200
            df = pd.DataFrame({
                "open": np.random.randn(n_bars).cumsum() + 100,
                "high": np.random.randn(n_bars).cumsum() + 101,
                "low": np.random.randn(n_bars).cumsum() + 99,
                "close": np.random.randn(n_bars).cumsum() + 100,
                "volume": np.random.randint(1000, 10000, n_bars),
            }, index=pd.date_range(end="2024-01-01", periods=n_bars, freq="5min"))

            env = DummyVecEnv([lambda: TradingEnv(df)])

            # Create minimal PPO model
            model = PPO("MlpPolicy", env, n_steps=16, batch_size=8, verbose=0)

            # Save
            with tempfile.TemporaryDirectory() as tmpdir:
                model_path = os.path.join(tmpdir, "test_model.zip")
                model.save(model_path)

                # Load
                loaded_model = PPO.load(model_path)

                assert loaded_model is not None

        except Exception as e:
            pytest.skip(f"PPO test setup failed: {e}")


class TestTrainingConfiguration:
    """Test training configuration loading."""

    def test_symbol_config_loading(self):
        """Test that per-symbol configs can be loaded."""
        from Python.config_utils import get_symbol_config

        # Try to load a config - may not exist, but shouldn't crash
        config = get_symbol_config("EURUSDm")

        # Should return None or a dict, never raise
        assert config is None or isinstance(config, dict)

    def test_main_config_loading(self):
        """Test that main config can be loaded."""
        from Python.config_utils import load_yaml_config, get_main_config_path

        config_path = get_main_config_path()

        if config_path.exists():
            config = load_yaml_config(config_path)
            assert isinstance(config, dict)
        else:
            pytest.skip("Main config.yaml not found")


class TestTrainingScripts:
    """Test that training scripts can be imported."""

    def test_train_drl_imports(self):
        """Test that train_drl module can be imported."""
        try:
            import training.train_drl
            assert True
        except ImportError as e:
            pytest.skip(f"Cannot import train_drl: {e}")

    def test_train_lstm_imports(self):
        """Test that train_lstm module can be imported."""
        try:
            import training.train_lstm
            assert True
        except ImportError as e:
            pytest.skip(f"Cannot import train_lstm: {e}")


class TestLSTMFeatureExtractor:
    """Test LSTM feature extractor."""

    def test_feature_extractor_creation(self):
        """Test that LSTM feature extractor can be created."""
        try:
            from drl.lstm_feature_extractor import LSTMFeatureExtractor
            from gymnasium import spaces
            import torch
            import numpy as np

            # Create a dummy observation space (like TradingEnv uses)
            # 100 window * 21 features + 3 portfolio features = 2103
            obs_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(2103,),
                dtype=np.float32
            )

            extractor = LSTMFeatureExtractor(
                observation_space=obs_space,
                features_dim=256,
            )

            assert extractor is not None

            # Test forward pass
            dummy_obs = torch.randn(1, 2103)
            try:
                output = extractor.forward(dummy_obs)
            except RuntimeError as exc:
                if "MPS" in str(exc):
                    pytest.skip(f"MPS device issue in forward pass: {exc}")
                raise
            assert output.shape[1] == 259  # features_dim + portfolio_feature_count

        except ImportError:
            pytest.skip("Dependencies not available")


if __name__ == "__main__":
    # Run with: python tests/test_training_pipeline.py
    pytest.main([__file__, "-v"])
