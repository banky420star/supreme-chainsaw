"""
Tests for the Training Analyzer module with Ollama integration.
"""
import pytest
import json
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Python.training_analyzer import (
    TrainingAnalyzer,
    analyze_current_training,
    analyze_training_trading_connection,
    get_training_description,
)


class TestTrainingAnalyzer:
    """Test cases for TrainingAnalyzer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = TrainingAnalyzer(model="qwen3:4b")

    def test_analyze_training_progress_basic(self):
        """Test basic training progress analysis."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            "total_epochs": 100,
            "loss": 0.0234,
            "val_loss": 0.0312,
            "avg_reward": 0.156,
            "win_rate": 58.5,
            "total_trades": 234,
        }

        # Mock Ollama response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "The model is learning to identify bullish patterns during high volatility periods. It's currently refining its entry timing based on RSI and MACD divergence signals."
        }
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = self.analyzer.analyze_training_progress(metrics)

        assert result["symbol"] == "BTCUSDm"
        assert result["epoch"] == 50
        assert result["progress_pct"] == 50.0
        assert "learning_stage" in result
        assert "stage_description" in result
        assert "ai_description" in result

    def test_learning_stage_exploration(self):
        """Test that early training is classified as exploration."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 5,
            "total_epochs": 100,
            "loss": 0.5,
            "avg_reward": 0.01,
            "win_rate": 45.0,
            "total_trades": 10,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Exploring action space"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = self.analyzer.analyze_training_progress(metrics)

        assert result["learning_stage"] == "exploration"

    def test_learning_stage_convergence(self):
        """Test that late training is classified as convergence."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 95,
            "total_epochs": 100,
            "loss": 0.02,
            "avg_reward": 0.5,
            "win_rate": 65.0,
            "total_trades": 500,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Policy converging"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = self.analyzer.analyze_training_progress(metrics)

        assert result["learning_stage"] == "convergence"

    def test_cache_hit(self):
        """Test that caching works correctly."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            "total_epochs": 100,
            "loss": 0.0234,
            "avg_reward": 0.156,
            "win_rate": 58.5,
            "total_trades": 234,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test description"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response) as mock_post:
            # First call - should hit Ollama
            result1 = self.analyzer.analyze_training_progress(metrics)

            # Second call within cache TTL - should return cached result
            result2 = self.analyzer.analyze_training_progress(metrics)

            # Ollama should only be called once
            assert mock_post.call_count == 1
            assert result1 == result2

    def test_analyze_trading_connection(self):
        """Test training-trading connection analysis."""
        training_metrics = {
            "symbol": "BTCUSDm",
            "epoch": 75,
            "total_epochs": 100,
            "win_rate": 60.0,
            "avg_reward": 0.3,
        }

        trading_metrics = {
            "symbol": "BTCUSDm",
            "pnl": 250.50,
            "live_win_rate": 55.0,
            "open_positions": 2,
            "recent_actions": ["BUY", "HOLD", "SELL"],
            "avg_confidence": 0.72,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "The model's training on trend-following strategies is translating well to live trading, with similar win rates between training and live environments."
        }
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = self.analyzer.analyze_trading_connection(
                training_metrics, trading_metrics
            )

        assert result["training_symbol"] == "BTCUSDm"
        assert result["trading_symbol"] == "BTCUSDm"
        assert "connection_description" in result
        assert "alignment_score" in result
        assert 0 <= result["alignment_score"] <= 1

    def test_alignment_calculation_high(self):
        """Test alignment score calculation - high alignment case."""
        training = {"win_rate": 60, "symbol": "BTCUSDm"}
        trading = {
            "live_win_rate": 58,
            "pnl": 100,
            "avg_confidence": 0.8,
            "symbol": "BTCUSDm",
        }

        score = self.analyzer._calculate_alignment(training, trading)
        assert score > 0.7  # Should be high alignment

    def test_alignment_calculation_low(self):
        """Test alignment score calculation - low alignment case."""
        training = {"win_rate": 60, "symbol": "BTCUSDm"}
        trading = {
            "live_win_rate": 30,
            "pnl": -100,
            "avg_confidence": 0.8,
            "symbol": "BTCUSDm",
        }

        score = self.analyzer._calculate_alignment(training, trading)
        assert score < 0.5  # Should be low alignment

    def test_get_learning_trajectory_no_history(self):
        """Test getting learning trajectory when no history exists."""
        result = self.analyzer.get_learning_trajectory("BTCUSDm")
        assert "error" in result
        assert result["error"] == "No history for symbol"

    def test_get_learning_trajectory_with_history(self):
        """Test getting learning trajectory with history."""
        # Add some history
        for i in range(5):
            self.analyzer._analysis_history.append({
                "symbol": "BTCUSDm",
                "learning_stage": f"stage_{i}",
                "metrics_summary": {"loss": 0.1 - i * 0.01},
            })

        result = self.analyzer.get_learning_trajectory("BTCUSDm")
        assert result["symbol"] == "BTCUSDm"
        assert result["total_analyses"] == 5
        assert result["current_stage"] == "stage_4"

    def test_generate_insights_no_data(self):
        """Test insights generation with no training data."""
        insights = self.analyzer.generate_training_insights()
        assert len(insights) == 1
        assert "No training data" in insights[0]

    def test_generate_insights_with_data(self):
        """Test insights generation with training data."""
        # Add some history
        self.analyzer._analysis_history.append({
            "symbol": "BTCUSDm",
            "learning_stage": "optimization",
            "metrics_summary": {"loss": 0.05},
        })

        insights = self.analyzer.generate_training_insights()
        assert len(insights) > 0

    def test_ollama_call_failure(self):
        """Test handling of Ollama call failure."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            "total_epochs": 100,
            "loss": 0.0234,
            "avg_reward": 0.156,
            "win_rate": 58.5,
            "total_trades": 234,
        }

        with patch('requests.post', side_effect=Exception("Connection failed")):
            result = self.analyzer.analyze_training_progress(metrics)

        assert result["symbol"] == "BTCUSDm"
        assert "ai_description" in result
        assert "Analysis unavailable" in result["ai_description"]


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_analyze_current_training(self):
        """Test analyze_current_training function."""
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            "total_epochs": 100,
            "loss": 0.0234,
            "avg_reward": 0.156,
            "win_rate": 58.5,
            "total_trades": 234,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = analyze_current_training(metrics)
            assert result["symbol"] == "BTCUSDm"

    def test_get_training_description_no_progress_files(self):
        """Test get_training_description when no progress files exist."""
        with patch('glob.glob', return_value=[]):
            result = get_training_description("BTCUSDm")
            assert "error" in result

    def test_get_training_description_with_progress_file(self):
        """Test get_training_description with existing progress file."""
        mock_progress = {
            "symbol": "BTCUSDm",
            "timesteps": 50000,
            "target_timesteps": 100000,
            "win_rate": 55.0,
        }

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = json.dumps(mock_progress)

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test analysis"}
        mock_response.raise_for_status.return_value = None

        with patch('glob.glob', return_value=['ppo_BTCUSDm_progress.json']):
            with patch('builtins.open', return_value=mock_file):
                with patch('json.load', return_value=mock_progress):
                    with patch('requests.post', return_value=mock_response):
                        result = get_training_description("BTCUSDm")
                        assert "symbol" in result


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_total_epochs(self):
        """Test handling of zero total_epochs."""
        analyzer = TrainingAnalyzer()
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 0,
            "total_epochs": 0,
            "loss": 0.5,
            "avg_reward": 0,
            "win_rate": 0,
            "total_trades": 0,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = analyzer.analyze_training_progress(metrics)
            assert result["progress_pct"] == 0

    def test_missing_metrics(self):
        """Test handling of missing optional metrics."""
        analyzer = TrainingAnalyzer()
        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            # Missing other fields
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response):
            result = analyzer.analyze_training_progress(metrics)
            assert result["symbol"] == "BTCUSDm"
            assert "learning_stage" in result

    def test_cache_expiry(self):
        """Test that cache expires after TTL."""
        analyzer = TrainingAnalyzer()
        analyzer.cache_ttl = 0.1  # 100ms for testing

        metrics = {
            "symbol": "BTCUSDm",
            "epoch": 50,
            "total_epochs": 100,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test"}
        mock_response.raise_for_status.return_value = None

        with patch('requests.post', return_value=mock_response) as mock_post:
            analyzer.analyze_training_progress(metrics)
            time.sleep(0.15)  # Wait for cache to expire
            analyzer.analyze_training_progress(metrics)
            assert mock_post.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
