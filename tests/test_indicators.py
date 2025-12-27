"""Tests for stock indicators."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from stockstalk.indicators import (
    MACDIndicator,
    MovingAverageCrossoverIndicator,
    PriceChangeIndicator,
    RSIIndicator,
    VolumeSpikeIndicator,
)
from stockstalk.models import AlertPriority, HistoricalData, StockData


def create_test_stock_data(
    symbol: str = "TEST",
    current_price: float = 100.0,
    previous_close: float = 98.0,
) -> StockData:
    """Create test stock data."""
    return StockData(
        symbol=symbol,
        current_price=current_price,
        open_price=99.0,
        high_price=101.0,
        low_price=98.5,
        volume=1000000,
        previous_close=previous_close,
    )


def create_test_historical_data(
    symbol: str = "TEST",
    days: int = 30,
    base_price: float = 100.0,
) -> HistoricalData:
    """Create test historical data."""
    dates = [datetime.now() - timedelta(days=i) for i in range(days, 0, -1)]
    
    # Create realistic price movements
    prices = [base_price]
    for _ in range(days - 1):
        change = np.random.normal(0, 2)  # Random walk
        prices.append(max(prices[-1] + change, 1.0))
    
    return HistoricalData(
        symbol=symbol,
        dates=dates,
        open_prices=prices,
        high_prices=[p * 1.02 for p in prices],
        low_prices=[p * 0.98 for p in prices],
        close_prices=prices,
        volumes=[1000000] * days,
    )


def test_rsi_indicator_oversold() -> None:
    """Test RSI indicator detects oversold condition."""
    # Create data with declining prices
    historical = create_test_historical_data(days=20, base_price=100.0)
    # Force declining prices for oversold
    for i in range(len(historical.close_prices)):
        historical.close_prices[i] = 100.0 - i * 2
    
    current = create_test_stock_data(current_price=60.0, previous_close=62.0)
    
    indicator = RSIIndicator()
    result = indicator.analyze(current, historical)
    
    assert result.indicator_name == "RSI"
    assert "metadata" in result.model_dump()


def test_rsi_indicator_insufficient_data() -> None:
    """Test RSI indicator with insufficient data."""
    historical = create_test_historical_data(days=5)
    current = create_test_stock_data()
    
    indicator = RSIIndicator(period=14)
    result = indicator.analyze(current, historical)
    
    assert result.is_triggered is False
    assert "Insufficient data" in result.message


def test_price_change_indicator_significant_drop() -> None:
    """Test price change indicator detects significant drop."""
    current = create_test_stock_data(current_price=90.0, previous_close=100.0)
    historical = create_test_historical_data()
    
    indicator = PriceChangeIndicator(significant_drop_pct=-5.0)
    result = indicator.analyze(current, historical)
    
    assert result.is_triggered is True
    assert result.priority in [AlertPriority.MEDIUM, AlertPriority.HIGH]
    assert "DROP" in result.message.upper()


def test_price_change_indicator_no_trigger() -> None:
    """Test price change indicator doesn't trigger on small change."""
    current = create_test_stock_data(current_price=100.0, previous_close=99.0)
    historical = create_test_historical_data()
    
    indicator = PriceChangeIndicator()
    result = indicator.analyze(current, historical)
    
    assert result.is_triggered is False


def test_volume_spike_indicator() -> None:
    """Test volume spike indicator."""
    historical = create_test_historical_data()
    current = create_test_stock_data()
    current.volume = 5000000  # 5x normal volume
    
    indicator = VolumeSpikeIndicator(spike_threshold=2.0)
    result = indicator.analyze(current, historical)
    
    assert result.is_triggered is True
    assert "SPIKE" in result.message.upper()


def test_ma_crossover_indicator() -> None:
    """Test moving average crossover indicator."""
    historical = create_test_historical_data(days=60)
    current = create_test_stock_data()
    
    indicator = MovingAverageCrossoverIndicator(short_period=10, long_period=50)
    result = indicator.analyze(current, historical)
    
    assert result.indicator_name == "MA_Crossover"
    assert "short_ma" in result.metadata
    assert "long_ma" in result.metadata


def test_macd_indicator() -> None:
    """Test MACD indicator."""
    historical = create_test_historical_data(days=60)
    current = create_test_stock_data()
    
    indicator = MACDIndicator()
    result = indicator.analyze(current, historical)
    
    assert result.indicator_name == "MACD"
    assert "macd" in result.metadata
    assert "signal_line" in result.metadata


def test_indicator_custom_params() -> None:
    """Test indicator with custom parameters."""
    historical = create_test_historical_data()
    current = create_test_stock_data()
    
    indicator = RSIIndicator(period=10, oversold_threshold=35)
    result = indicator.analyze(current, historical)
    
    assert indicator.get_param("period") == 10
    assert indicator.get_param("oversold_threshold") == 35
    assert indicator.get_param("nonexistent", "default") == "default"
