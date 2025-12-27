"""Tests for RSI indicator."""

import pytest

from stock_sentinel.data.models import OHLCV, StockData
from stock_sentinel.indicators.base import SignalType
from stock_sentinel.indicators.rsi import RSIIndicator


class TestRSIIndicator:
    """Test suite for RSI indicator."""

    @pytest.fixture
    def rsi_indicator(self):
        """Create an RSI indicator instance."""
        return RSIIndicator()

    async def test_rsi_name_and_description(self, rsi_indicator):
        """Test RSI indicator metadata."""
        assert rsi_indicator.name == "rsi"
        assert "RSI" in rsi_indicator.description
        assert rsi_indicator.required_history_days >= 14

    async def test_rsi_insufficient_data(self, rsi_indicator, sample_quote):
        """Test RSI returns None with insufficient data."""
        # Only 5 days of data
        history = [
            OHLCV(
                timestamp=sample_quote.timestamp,
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000000,
            )
            for _ in range(5)
        ]

        stock_data = StockData(symbol="TEST", quote=sample_quote, history=history)
        result = await rsi_indicator.analyze(stock_data)

        assert result is None

    async def test_rsi_oversold_signal(self, rsi_indicator, sample_quote, oversold_history):
        """Test RSI generates buy signal when oversold."""
        stock_data = StockData(
            symbol="TEST",
            quote=sample_quote,
            history=oversold_history,
        )

        result = await rsi_indicator.analyze(stock_data)

        assert result is not None
        assert result.signal in (SignalType.BUY, SignalType.STRONG_BUY)
        assert result.value < 30
        assert result.should_alert is True
        assert "oversold" in result.message.lower()

    async def test_rsi_overbought_signal(self, sample_quote, overbought_history):
        """Test RSI generates sell signal when overbought."""
        # Enable alert_on_sell to test sell alerts
        from stock_sentinel.indicators.base import IndicatorConfig

        config = IndicatorConfig(alert_on_sell=True)
        indicator = RSIIndicator(config=config)

        stock_data = StockData(
            symbol="TEST",
            quote=sample_quote,
            history=overbought_history,
        )

        result = await indicator.analyze(stock_data)

        assert result is not None
        assert result.signal in (SignalType.SELL, SignalType.STRONG_SELL)
        assert result.value > 70
        assert result.should_alert is True
        assert "overbought" in result.message.lower()

    async def test_rsi_neutral_signal(self, rsi_indicator, sample_stock_data):
        """Test RSI generates neutral signal in normal conditions."""
        result = await rsi_indicator.analyze(sample_stock_data)

        # With sample data, RSI should be in neutral zone
        assert result is not None
        assert result.signal == SignalType.NEUTRAL
        assert 30 <= result.value <= 70
        assert result.should_alert is False

    async def test_rsi_custom_thresholds(self, sample_quote, overbought_history):
        """Test RSI with custom thresholds."""
        # Use more extreme thresholds
        indicator = RSIIndicator(oversold=20, overbought=80)

        stock_data = StockData(
            symbol="TEST",
            quote=sample_quote,
            history=overbought_history,
        )

        result = await indicator.analyze(stock_data)

        # With stricter thresholds, high RSI might still be "neutral"
        assert result is not None
        # The value should still be high, but signal might differ with thresholds

    async def test_rsi_result_metadata(self, rsi_indicator, sample_stock_data):
        """Test RSI result contains expected metadata."""
        result = await rsi_indicator.analyze(sample_stock_data)

        assert result is not None
        assert result.indicator_name == "rsi"
        assert result.symbol == sample_stock_data.symbol
        assert "period" in result.metadata
        assert "oversold_threshold" in result.metadata
        assert "overbought_threshold" in result.metadata
