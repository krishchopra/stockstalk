"""Tests for data models."""

from datetime import datetime

import pytest

from stockstalk.models import (
    AlertPriority,
    AppConfig,
    IndicatorResult,
    NotificationConfig,
    StockData,
    WatchlistItem,
)


def test_stock_data_creation() -> None:
    """Test creating a StockData instance."""
    stock = StockData(
        symbol="AAPL",
        current_price=150.0,
        open_price=148.0,
        high_price=152.0,
        low_price=147.0,
        volume=1000000,
        previous_close=149.0,
    )

    assert stock.symbol == "AAPL"
    assert stock.current_price == 150.0
    assert stock.volume == 1000000


def test_stock_data_symbol_normalization() -> None:
    """Test that stock symbols are normalized to uppercase."""
    stock = StockData(
        symbol="aapl",
        current_price=150.0,
        open_price=148.0,
        high_price=152.0,
        low_price=147.0,
        volume=1000000,
        previous_close=149.0,
    )

    assert stock.symbol == "AAPL"


def test_stock_data_validation() -> None:
    """Test that invalid stock data raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        StockData(
            symbol="AAPL",
            current_price=-150.0,  # Invalid negative price
            open_price=148.0,
            high_price=152.0,
            low_price=147.0,
            volume=1000000,
            previous_close=149.0,
        )


def test_indicator_result_creation() -> None:
    """Test creating an IndicatorResult instance."""
    result = IndicatorResult(
        indicator_name="RSI",
        symbol="AAPL",
        is_triggered=True,
        signal_strength=0.8,
        message="RSI is oversold",
        priority=AlertPriority.HIGH,
    )

    assert result.indicator_name == "RSI"
    assert result.is_triggered is True
    assert result.signal_strength == 0.8
    assert result.priority == AlertPriority.HIGH


def test_watchlist_item_creation() -> None:
    """Test creating a WatchlistItem instance."""
    item = WatchlistItem(
        symbol="MSFT",
        enabled_indicators=["RSI", "MACD"],
        custom_params={"rsi_period": 14},
    )

    assert item.symbol == "MSFT"
    assert len(item.enabled_indicators) == 2
    assert item.custom_params["rsi_period"] == 14


def test_notification_config_defaults() -> None:
    """Test NotificationConfig with defaults."""
    config = NotificationConfig()

    assert config.phone_numbers == []
    assert config.beeper_webhook_url is None
    assert config.min_priority == AlertPriority.MEDIUM


def test_app_config_creation() -> None:
    """Test creating an AppConfig instance."""
    config = AppConfig(
        watchlist=[
            WatchlistItem(symbol="AAPL", enabled_indicators=["RSI"]),
        ],
        check_interval_minutes=15,
    )

    assert len(config.watchlist) == 1
    assert config.check_interval_minutes == 15
    assert config.data_lookback_days == 30  # default
