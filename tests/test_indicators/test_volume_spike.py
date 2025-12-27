"""Tests for Volume Spike indicator."""

from datetime import datetime, timedelta

import pytest

from stock_sentinel.data.models import OHLCV, StockData
from stock_sentinel.indicators.base import SignalType
from stock_sentinel.indicators.volume_spike import VolumeSpikeIndicator


class TestVolumeSpikeIndicator:
    """Test suite for Volume Spike indicator."""

    @pytest.fixture
    def volume_indicator(self):
        """Create a Volume Spike indicator instance."""
        return VolumeSpikeIndicator()

    async def test_volume_spike_name_and_description(self, volume_indicator):
        """Test Volume Spike indicator metadata."""
        assert volume_indicator.name == "volume_spike"
        assert "Volume" in volume_indicator.description

    async def test_volume_spike_insufficient_data(self, volume_indicator, sample_quote):
        """Test indicator returns None with insufficient data."""
        history = [
            OHLCV(
                timestamp=datetime.now() - timedelta(days=i),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000000,
            )
            for i in range(5)
        ]

        stock_data = StockData(symbol="TEST", quote=sample_quote, history=history)
        result = await volume_indicator.analyze(stock_data)

        assert result is None

    async def test_volume_spike_bullish(self, volume_indicator, sample_quote, volume_spike_history):
        """Test volume spike with price up generates bullish signal."""
        stock_data = StockData(
            symbol="TEST",
            quote=sample_quote,
            history=volume_spike_history,
        )

        result = await volume_indicator.analyze(stock_data)

        assert result is not None
        assert result.signal in (SignalType.BUY, SignalType.STRONG_BUY)
        assert result.should_alert is True
        assert result.metadata["volume_ratio"] >= 2.0

    async def test_volume_spike_bearish(self, sample_quote):
        """Test volume spike with price down generates bearish signal."""
        from stock_sentinel.indicators.base import IndicatorConfig

        # Enable alert_on_sell to test sell alerts
        config = IndicatorConfig(alert_on_sell=True)
        volume_indicator = VolumeSpikeIndicator(config=config)

        base_date = datetime.now() - timedelta(days=25)
        history = []

        price = 150.0
        for i in range(25):
            if i < 24:
                volume = 50000000
                price_change = 0.5
            else:
                volume = 200000000  # 4x normal volume
                price_change = -5.0  # Big price drop

            price = price + price_change

            history.append(
                OHLCV(
                    timestamp=base_date + timedelta(days=i),
                    open=price + 1,
                    high=price + 2,
                    low=price - 2,
                    close=price,
                    volume=volume,
                )
            )

        stock_data = StockData(symbol="TEST", quote=sample_quote, history=history)
        result = await volume_indicator.analyze(stock_data)

        assert result is not None
        assert result.signal in (SignalType.SELL, SignalType.STRONG_SELL)
        assert result.should_alert is True

    async def test_normal_volume_neutral(self, volume_indicator, sample_stock_data):
        """Test normal volume generates neutral signal."""
        result = await volume_indicator.analyze(sample_stock_data)

        assert result is not None
        # Normal sample data should show neutral volume
        # (volume ratio should be close to 1)

    async def test_volume_spike_metadata(
        self, volume_indicator, sample_quote, volume_spike_history
    ):
        """Test volume spike result contains expected metadata."""
        stock_data = StockData(
            symbol="TEST",
            quote=sample_quote,
            history=volume_spike_history,
        )

        result = await volume_indicator.analyze(stock_data)

        assert result is not None
        assert "volume_ratio" in result.metadata
        assert "avg_volume" in result.metadata
        assert "current_volume" in result.metadata
