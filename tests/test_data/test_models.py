"""Tests for data models."""

from datetime import datetime

import pytest

from stock_sentinel.data.models import OHLCV, StockQuote


class TestOHLCV:
    """Test suite for OHLCV model."""

    def test_ohlcv_creation(self):
        """Test creating an OHLCV object."""
        ohlcv = OHLCV(
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        assert ohlcv.open == 100.0
        assert ohlcv.high == 105.0
        assert ohlcv.low == 98.0
        assert ohlcv.close == 103.0
        assert ohlcv.volume == 1000000

    def test_ohlcv_typical_price(self):
        """Test typical price calculation."""
        ohlcv = OHLCV(
            timestamp=datetime.now(),
            open=100.0,
            high=110.0,
            low=90.0,
            close=100.0,
            volume=1000000,
        )

        # Typical price = (high + low + close) / 3 = (110 + 90 + 100) / 3 = 100
        assert ohlcv.typical_price == 100.0

    def test_ohlcv_is_frozen(self):
        """Test OHLCV model is immutable."""
        ohlcv = OHLCV(
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        with pytest.raises((TypeError, ValueError)):  # ValidationError for frozen model
            ohlcv.close = 110.0


class TestStockQuote:
    """Test suite for StockQuote model."""

    def test_stock_quote_creation(self, sample_quote):
        """Test creating a StockQuote object."""
        assert sample_quote.symbol == "AAPL"
        assert sample_quote.price == 150.0
        assert sample_quote.change == 2.50
        assert sample_quote.change_percent == 1.69

    def test_stock_quote_52_week_high(self):
        """Test 52-week high detection."""
        quote = StockQuote(
            symbol="TEST",
            price=178.0,  # Within 2% of 180 high
            change=0,
            change_percent=0,
            volume=1000000,
            week_52_high=180.0,
            week_52_low=120.0,
        )

        assert quote.is_at_52_week_high is True
        assert quote.is_at_52_week_low is False

    def test_stock_quote_52_week_low(self):
        """Test 52-week low detection."""
        quote = StockQuote(
            symbol="TEST",
            price=121.0,  # Within 2% of 120 low
            change=0,
            change_percent=0,
            volume=1000000,
            week_52_high=180.0,
            week_52_low=120.0,
        )

        assert quote.is_at_52_week_high is False
        assert quote.is_at_52_week_low is True


class TestStockData:
    """Test suite for StockData model."""

    def test_stock_data_creation(self, sample_stock_data):
        """Test creating a StockData object."""
        assert sample_stock_data.symbol == "AAPL"
        assert sample_stock_data.quote is not None
        assert len(sample_stock_data.history) > 0

    def test_stock_data_closes(self, sample_stock_data):
        """Test getting list of closing prices."""
        closes = sample_stock_data.closes

        assert len(closes) == len(sample_stock_data.history)
        assert all(isinstance(c, float) for c in closes)

    def test_stock_data_volumes(self, sample_stock_data):
        """Test getting list of volumes."""
        volumes = sample_stock_data.volumes

        assert len(volumes) == len(sample_stock_data.history)
        assert all(isinstance(v, int) for v in volumes)

    def test_stock_data_average_volume(self, sample_stock_data):
        """Test average volume calculation."""
        avg_vol = sample_stock_data.average_volume

        assert avg_vol > 0
        assert isinstance(avg_vol, float)

    def test_stock_data_latest_close(self, sample_stock_data):
        """Test getting latest closing price."""
        latest = sample_stock_data.latest_close

        assert latest is not None
        assert latest == sample_stock_data.history[-1].close

    def test_stock_data_returns(self, sample_stock_data):
        """Test calculating returns."""
        returns = sample_stock_data.get_returns()

        assert len(returns) == len(sample_stock_data.history) - 1
        assert all(isinstance(r, float) for r in returns)

    def test_stock_data_dataframe(self, sample_stock_data):
        """Test converting to pandas DataFrame."""
        df = sample_stock_data.df

        assert not df.empty
        assert "close" in df.columns
        assert "volume" in df.columns
        assert len(df) == len(sample_stock_data.history)
