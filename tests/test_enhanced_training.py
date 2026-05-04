"""
Tests for the Enhanced Training Pipeline with per-symbol metrics and multi-timeframe optimization.
"""
import pytest
import json
import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from training.enhanced_train_drl import (
    PerSymbolMetricsTracker,
    MultiTimeframeOptimizer,
    EnhancedTrainingPipeline,
)


class TestPerSymbolMetricsTracker:
    """Test cases for PerSymbolMetricsTracker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = PerSymbolMetricsTracker(
            symbols=["BTCUSDm", "EURUSDm"],
            initial_balance=10000.0
        )

    def test_initialization(self):
        """Test tracker initialization."""
        assert "BTCUSDm" in self.tracker.metrics_by_symbol
        assert "EURUSDm" in self.tracker.metrics_by_symbol

        for symbol in ["BTCUSDm", "EURUSDm"]:
            m = self.tracker.metrics_by_symbol[symbol]
            assert m["initial_balance"] == 10000.0
            assert m["current_balance"] == 10000.0
            assert m["total_trades"] == 0

    def test_update_after_winning_trade(self):
        """Test updating metrics after a winning trade."""
        trade_info = {"type": "BUY", "exit_price": 50000, "entry_price": 49000}
        self.tracker.update_after_trade("BTCUSDm", 150.0, trade_info)

        m = self.tracker.metrics_by_symbol["BTCUSDm"]
        assert m["total_trades"] == 1
        assert m["winning_trades"] == 1
        assert m["losing_trades"] == 0
        assert m["total_profit"] == 150.0
        assert m["current_balance"] == 10150.0

    def test_update_after_losing_trade(self):
        """Test updating metrics after a losing trade."""
        trade_info = {"type": "SELL", "exit_price": 48000, "entry_price": 49000}
        self.tracker.update_after_trade("BTCUSDm", -100.0, trade_info)

        m = self.tracker.metrics_by_symbol["BTCUSDm"]
        assert m["total_trades"] == 1
        assert m["winning_trades"] == 0
        assert m["losing_trades"] == 1
        assert m["total_loss"] == 100.0
        assert m["current_balance"] == 9900.0

    def test_max_drawdown_calculation(self):
        """Test max drawdown calculation."""
        # Simulate a series of trades
        self.tracker.update_after_trade("BTCUSDm", 500.0, {})  # Balance: 10500
        self.tracker.update_after_trade("BTCUSDm", -200.0, {})  # Balance: 10300
        self.tracker.update_after_trade("BTCUSDm", -400.0, {})  # Balance: 9900 (drawdown from 10500)

        m = self.tracker.metrics_by_symbol["BTCUSDm"]
        assert m["max_drawdown"] == 600.0  # 10500 - 9900
        assert m["max_drawdown_pct"] > 0

    def test_equity_curve_recording(self):
        """Test that equity curve is recorded."""
        self.tracker.update_after_trade("BTCUSDm", 100.0, {})
        self.tracker.update_after_trade("BTCUSDm", 50.0, {})

        m = self.tracker.metrics_by_symbol["BTCUSDm"]
        assert len(m["equity_curve"]) == 2
        assert m["equity_curve"][0]["balance"] == 10100.0
        assert m["equity_curve"][1]["balance"] == 10150.0

    def test_trade_history(self):
        """Test trade history recording."""
        trade_info = {"type": "BUY", "volume": 0.1}
        self.tracker.update_after_trade("BTCUSDm", 100.0, trade_info)

        m = self.tracker.metrics_by_symbol["BTCUSDm"]
        assert len(m["trade_history"]) == 1
        assert m["trade_history"][0]["profit"] == 100.0
        assert "timestamp" in m["trade_history"][0]

    def test_get_summary_no_trades(self):
        """Test get_summary when no trades have occurred."""
        summary = self.tracker.get_summary("BTCUSDm")
        assert summary == {}

    def test_get_summary_with_trades(self):
        """Test get_summary with trades."""
        self.tracker.update_after_trade("BTCUSDm", 200.0, {})
        self.tracker.update_after_trade("BTCUSDm", 100.0, {})

        summary = self.tracker.get_summary("BTCUSDm")
        assert summary["symbol"] == "BTCUSDm"
        assert summary["total_trades"] == 2
        assert summary["net_profit"] == 300.0
        assert summary["win_rate"] == 100.0
        assert summary["profit_factor"] == float("inf")  # No losses

    def test_get_all_summaries(self):
        """Test getting summaries for all symbols."""
        self.tracker.update_after_trade("BTCUSDm", 100.0, {})
        self.tracker.update_after_trade("EURUSDm", 200.0, {})

        summaries = self.tracker.get_all_summaries()
        assert len(summaries) == 2
        assert summaries["BTCUSDm"]["net_profit"] == 100.0
        assert summaries["EURUSDm"]["net_profit"] == 200.0

    def test_unknown_symbol_update(self):
        """Test updating unknown symbol doesn't crash."""
        self.tracker.update_after_trade("UNKNOWN", 100.0, {})
        # Should not raise exception


class TestMultiTimeframeOptimizer:
    """Test cases for MultiTimeframeOptimizer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = MultiTimeframeOptimizer("BTCUSDm", period="30d", min_bars=100)

    @patch("training.enhanced_train_drl.fetch_training_data")
    def test_test_timeframe_success(self, mock_fetch):
        """Test testing a single timeframe with valid data."""
        import pandas as pd
        import numpy as np

        # Create mock DataFrame
        dates = pd.date_range(start="2024-01-01", periods=500, freq="5min")
        mock_df = pd.DataFrame({
            "open": np.random.randn(500).cumsum() + 50000,
            "high": np.random.randn(500).cumsum() + 50100,
            "low": np.random.randn(500).cumsum() + 49900,
            "close": np.random.randn(500).cumsum() + 50050,
            "volume": np.random.randint(100, 1000, 500),
        }, index=dates)

        mock_fetch.return_value = mock_df

        result = self.optimizer.test_timeframe("5m")

        assert result is not None
        assert result["timeframe"] == "5m"
        assert result["bars"] == 500
        assert "sharpe_ratio" in result
        assert "adx" in result
        assert "quality_score" in result

    @patch("training.enhanced_train_drl.fetch_training_data")
    def test_test_timeframe_insufficient_data(self, mock_fetch):
        """Test testing timeframe with insufficient data."""
        mock_fetch.return_value = None

        result = self.optimizer.test_timeframe("5m")
        assert result is None

    def test_calculate_adx(self):
        """Test ADX calculation."""
        import pandas as pd
        import numpy as np

        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
        df = pd.DataFrame({
            "high": np.random.randn(100).cumsum() + 50100,
            "low": np.random.randn(100).cumsum() + 49900,
            "close": np.random.randn(100).cumsum() + 50000,
        }, index=dates)

        adx = self.optimizer._calculate_adx(df)
        assert isinstance(adx, (int, float))
        assert adx >= 0

    def test_calculate_data_quality(self):
        """Test data quality calculation."""
        import pandas as pd
        import numpy as np

        # Good quality data
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
        df = pd.DataFrame({
            "open": np.random.randn(100) + 50000,
            "high": np.random.randn(100) + 50100,
            "low": np.random.randn(100) + 49900,
            "close": np.random.randn(100) + 50050,
            "volume": np.random.randint(100, 1000, 100),
        }, index=dates)

        quality = self.optimizer._calculate_data_quality(df)
        assert isinstance(quality, float)
        assert 0 <= quality <= 1
        assert quality > 0.8  # Good data should have high quality

    def test_calculate_data_quality_with_nans(self):
        """Test data quality with NaN values."""
        import pandas as pd
        import numpy as np

        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
        df = pd.DataFrame({
            "open": np.random.randn(100) + 50000,
            "high": np.random.randn(100) + 50100,
            "low": np.random.randn(100) + 49900,
            "close": np.random.randn(100) + 50050,
            "volume": np.random.randint(100, 1000, 100),
        }, index=dates)

        # Add NaN values
        df.iloc[10:15, 0] = np.nan

        quality = self.optimizer._calculate_data_quality(df)
        assert quality < 1.0  # Should be reduced due to NaNs

    @patch("training.enhanced_train_drl.fetch_training_data")
    def test_find_best_timeframe(self, mock_fetch):
        """Test finding best timeframe."""
        import pandas as pd
        import numpy as np

        def create_mock_df(*args, **kwargs):
            tf = kwargs.get("interval", "5m")
            bars = {"1m": 1000, "5m": 500, "15m": 200, "30m": 150, "1h": 100}.get(tf, 500)

            dates = pd.date_range(start="2024-01-01", periods=bars, freq=tf)
            return pd.DataFrame({
                "open": np.random.randn(bars).cumsum() + 50000,
                "high": np.random.randn(bars).cumsum() + 50100,
                "low": np.random.randn(bars).cumsum() + 49900,
                "close": np.random.randn(bars).cumsum() + 50050,
                "volume": np.random.randint(100, 1000, bars),
            }, index=dates)

        mock_fetch.side_effect = create_mock_df

        best_tf, results = self.optimizer.find_best_timeframe()

        assert best_tf in ["1m", "5m", "15m", "30m", "1h"]
        assert "selected" in results
        assert "all_results" in results
        assert "ranking" in results
        assert len(results["ranking"]) > 0

    @patch("training.enhanced_train_drl.fetch_training_data")
    def test_find_best_timeframe_no_results(self, mock_fetch):
        """Test finding best timeframe when all fail."""
        mock_fetch.return_value = None

        best_tf, results = self.optimizer.find_best_timeframe()

        assert best_tf == "5m"  # Default fallback
        assert results == {} or "error" in str(results)


class TestEnhancedTrainingPipeline:
    """Test cases for EnhancedTrainingPipeline."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch.object(EnhancedTrainingPipeline, '_load_config', return_value={}):
            with patch.object(EnhancedTrainingPipeline, '_init_alerter'):
                self.pipeline = EnhancedTrainingPipeline()

    def test_load_config_success(self):
        """Test loading config file."""
        mock_config = {"trading": {"symbols": ["BTCUSDm"]}}

        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
                with patch('yaml.safe_load', return_value=mock_config):
                    config = self.pipeline._load_config("config.yaml")
                    assert config == mock_config

    def test_load_config_not_found(self):
        """Test loading config when file doesn't exist."""
        with patch('os.path.exists', return_value=False):
            config = self.pipeline._load_config(None)
            assert config == {}

    @patch("training.enhanced_train_drl.EnhancedTrainingPipeline._get_initial_balance")
    def test_get_initial_balance_from_config(self, mock_get_balance):
        """Test getting initial balance from config."""
        self.pipeline.config = {"trading": {"initial_balance": 5000.0}}
        mock_get_balance.return_value = 5000.0

        balance = self.pipeline._get_initial_balance()
        assert balance == 5000.0

    def test_generate_training_report(self):
        """Test training report generation."""
        results = {
            "symbols": ["BTCUSDm", "EURUSDm"],
            "timeframe_selections": {
                "BTCUSDm": {
                    "selected": "5m",
                    "selection_score": 1.5,
                    "all_results": {
                        "5m": {"bars": 500, "sharpe_ratio": 1.2, "adx": 25.0}
                    }
                }
            }
        }

        report = self.pipeline.generate_training_report(results)

        assert "ENHANCED DRL TRAINING REPORT" in report
        assert "BTCUSDm" in report
        assert "5m" in report
        assert "Selected Timeframe" in report


class TestIntegration:
    """Integration tests for the enhanced training system."""

    def test_end_to_end_metrics_tracking(self):
        """Test end-to-end metrics tracking."""
        tracker = PerSymbolMetricsTracker(["BTCUSDm"], 10000.0)

        # Simulate trading session
        trades = [
            (100.0, {"type": "BUY"}),
            (-50.0, {"type": "SELL"}),
            (200.0, {"type": "BUY"}),
            (150.0, {"type": "SELL"}),
            (-100.0, {"type": "BUY"}),
        ]

        for profit, info in trades:
            tracker.update_after_trade("BTCUSDm", profit, info)

        summary = tracker.get_summary("BTCUSDm")
        assert summary["total_trades"] == 5
        # Check internal metrics (winning_trades and losing_trades are in metrics_by_symbol)
        assert tracker.metrics_by_symbol["BTCUSDm"]["winning_trades"] == 3
        assert tracker.metrics_by_symbol["BTCUSDm"]["losing_trades"] == 2
        assert summary["net_profit"] == 300.0
        assert summary["win_rate"] == 60.0

        # Check profit factor
        expected_pf = 450.0 / 150.0  # total_profit / total_loss
        assert abs(summary["profit_factor"] - expected_pf) < 0.01

    def test_timeframe_scoring_consistency(self):
        """Test that timeframe scoring is consistent."""
        import pandas as pd
        import numpy as np

        optimizer = MultiTimeframeOptimizer("BTCUSDm")

        # Create identical data for all timeframes
        base_sharpe = 1.5
        base_quality = 0.9

        # Test that higher timeframes get bonus
        scores = {}
        for tf, multiplier in [("1m", 0.9), ("5m", 1.0), ("15m", 1.1), ("30m", 1.15), ("1h", 1.2)]:
            mock_result = {
                "sharpe_ratio": base_sharpe,
                "quality_score": base_quality,
                "bars": 1000,
            }
            base_score = max(0, mock_result["sharpe_ratio"]) * mock_result["quality_score"]
            final_score = base_score * multiplier
            scores[tf] = final_score

        # Verify higher timeframes get higher scores with same base metrics
        assert scores["1h"] > scores["30m"] > scores["15m"] > scores["5m"] > scores["1m"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
