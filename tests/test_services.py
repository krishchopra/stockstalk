"""Tests for services."""

import os
from unittest import mock

import pytest

from stockstalk.models import (
    AlertPriority,
    IndicatorResult,
)
from stockstalk.services.analyzer import IndicatorRegistry, StockAnalyzer


def test_indicator_registry_get_indicator() -> None:
    """Test getting an indicator from the registry."""
    indicator = IndicatorRegistry.get_indicator("RSI")
    assert indicator.name == "RSI"


def test_indicator_registry_list_indicators() -> None:
    """Test listing available indicators."""
    indicators = IndicatorRegistry.list_indicators()
    assert "RSI" in indicators
    assert "MACD" in indicators
    assert "Volume_Spike" in indicators


def test_indicator_registry_invalid_indicator() -> None:
    """Test getting an invalid indicator raises error."""
    with pytest.raises(ValueError):
        IndicatorRegistry.get_indicator("INVALID_INDICATOR")


def test_notification_service_should_notify() -> None:
    """Test notification priority filtering."""
    # Set min priority to MEDIUM via environment
    with mock.patch.dict(os.environ, {"MIN_PRIORITY": "medium"}, clear=False):
        from stockstalk.services.notifier import NotificationService

        service = NotificationService()

        low_result = IndicatorResult(
            indicator_name="Test",
            symbol="AAPL",
            is_triggered=True,
            priority=AlertPriority.LOW,
            signal_strength=0.5,
            message="Test",
        )

        high_result = IndicatorResult(
            indicator_name="Test",
            symbol="AAPL",
            is_triggered=True,
            priority=AlertPriority.HIGH,
            signal_strength=0.8,
            message="Test",
        )

        assert service.should_notify(low_result) is False
        assert service.should_notify(high_result) is True


def test_notification_service_not_triggered() -> None:
    """Test that non-triggered results don't notify."""
    from stockstalk.services.notifier import NotificationService

    service = NotificationService()

    result = IndicatorResult(
        indicator_name="Test",
        symbol="AAPL",
        is_triggered=False,
        priority=AlertPriority.HIGH,
        signal_strength=0.0,
        message="Test",
    )

    assert service.should_notify(result) is False


def test_notification_service_format_message() -> None:
    """Test message formatting for notifications."""
    from stockstalk.services.notifier import NotificationService

    service = NotificationService()

    result = IndicatorResult(
        indicator_name="Test",
        symbol="AAPL",
        is_triggered=True,
        priority=AlertPriority.HIGH,
        signal_strength=0.8,
        message="Test message",
    )

    formatted = service._format_message(result)

    assert "aapl" in formatted  # lowercase per implementation
    assert "test message" in formatted  # lowercase per implementation
    assert "[!]" in formatted  # HIGH priority prefix


def test_stock_analyzer_initialization() -> None:
    """Test stock analyzer initialization."""
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService

    data_fetcher = StockDataFetcher()
    notifier = NotificationService()
    analyzer = StockAnalyzer(data_fetcher, notifier, lookback_days=30)

    assert analyzer.lookback_days == 30
    assert analyzer.data_fetcher is data_fetcher
    assert analyzer.notifier is notifier
