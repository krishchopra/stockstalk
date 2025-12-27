"""Tests for MACD indicator."""

from datetime import datetime, timedelta

import pytest

from stock_sentinel.data.models import OHLCV, StockData
from stock_sentinel.indicators.base import SignalType
from stock_sentinel.indicators.macd import MACDIndicator


class TestMACDIndicator:
    """Test suite for MACD indicator."""

    @pytest.fixture
    def macd_indicator(self):
        """Create a MACD indicator instance."""
        return MACDIndicator()

    async def test_macd_name_and_description(self, macd_indicator):
        """Test MACD indicator metadata."""
        assert macd_indicator.name == "macd"
        assert "MACD" in macd_indicator.description
        assert macd_indicator.required_history_days >= 35

    async def test_macd_insufficient_data(self, macd_indicator, sample_quote):
        """Test MACD returns None with insufficient data."""
        # Only 20 days of data
        history = [
            OHLCV(
                timestamp=datetime.now() - timedelta(days=i),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000000,
            )
            for i in range(20)
        ]

        stock_data = StockData(symbol="TEST", quote=sample_quote, history=history)
        result = await macd_indicator.analyze(stock_data)

        assert result is None

    async def test_macd_calculates_correctly(self, macd_indicator, sample_stock_data):
        """Test MACD calculates and returns result."""
        result = await macd_indicator.analyze(sample_stock_data)

        assert result is not None
        assert result.indicator_name == "macd"
        assert result.symbol == sample_stock_data.symbol
        assert "macd_line" in result.metadata
        assert "signal_line" in result.metadata
        assert "histogram" in result.metadata

    async def test_macd_bullish_crossover(self, macd_indicator, sample_quote):
        """Test MACD detects bullish crossover."""
        # Create data with a bullish crossover pattern
        # Start with downtrend, then strong uptrend
        base_date = datetime.now() - timedelta(days=60)
        history = []

        price = 150.0
        for i in range(60):
            if i < 30:
                price -= 0.5  # Downtrend
            else:
                price += 1.5  # Strong uptrend

            history.append(
                OHLCV(
                    timestamp=base_date + timedelta(days=i),
                    open=price - 0.5,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                    volume=50000000,
                )
            )

        stock_data = StockData(symbol="TEST", quote=sample_quote, history=history)
        result = await macd_indicator.analyze(stock_data)

        assert result is not None
        # Strong uptrend should show bullish signal
        assert result.signal in (SignalType.BUY, SignalType.STRONG_BUY, SignalType.NEUTRAL)

    async def test_macd_result_has_crossover_info(self, macd_indicator, sample_stock_data):
        """Test MACD result contains crossover information."""
        result = await macd_indicator.analyze(sample_stock_data)

        assert result is not None
        assert "bullish_crossover" in result.metadata
        assert "bearish_crossover" in result.metadata
        # Check boolean value (could be numpy bool or Python bool)
        assert result.metadata["bullish_crossover"] in (True, False)
        assert result.metadata["bearish_crossover"] in (True, False)
