"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from stock_sentinel.data.models import OHLCV, StockData, StockQuote
from stock_sentinel.storage.database import Database, init_database


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_database() -> AsyncGenerator[Database, None]:
    """Create a test database with in-memory SQLite."""
    db = await init_database("sqlite+aiosqlite:///:memory:")
    yield db
    await db.close()


@pytest.fixture
def sample_quote() -> StockQuote:
    """Create a sample stock quote for testing."""
    return StockQuote(
        symbol="AAPL",
        price=150.0,
        change=2.50,
        change_percent=1.69,
        volume=50000000,
        market_cap=2500000000000,
        pe_ratio=28.5,
        week_52_high=180.0,
        week_52_low=120.0,
        avg_volume=45000000,
        dividend_yield=0.005,
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_history() -> list[OHLCV]:
    """Create sample historical OHLCV data for testing."""
    base_date = datetime.now() - timedelta(days=60)
    history = []

    # Create 60 days of sample data with a general uptrend
    price = 140.0
    for i in range(60):
        # Add some randomness
        change = (i % 5 - 2) * 0.5  # Oscillate between -1 and 1
        price = max(100, price + change)

        ohlcv = OHLCV(
            timestamp=base_date + timedelta(days=i),
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=50000000 + (i % 10) * 1000000,
            adjusted_close=price,
        )
        history.append(ohlcv)

    return history


@pytest.fixture
def sample_stock_data(sample_quote: StockQuote, sample_history: list[OHLCV]) -> StockData:
    """Create a complete sample StockData object for testing."""
    return StockData(
        symbol="AAPL",
        quote=sample_quote,
        history=sample_history,
        metadata={
            "provider": "test",
            "period": "3mo",
            "interval": "1d",
        },
    )


@pytest.fixture
def oversold_history() -> list[OHLCV]:
    """Create historical data that would result in oversold RSI."""
    base_date = datetime.now() - timedelta(days=30)
    history = []

    # Create a strong downtrend
    price = 200.0
    for i in range(30):
        price = max(50, price - 4)  # Strong consistent decline

        ohlcv = OHLCV(
            timestamp=base_date + timedelta(days=i),
            open=price + 2,
            high=price + 3,
            low=price - 1,
            close=price,
            volume=80000000,  # High volume on decline
            adjusted_close=price,
        )
        history.append(ohlcv)

    return history


@pytest.fixture
def overbought_history() -> list[OHLCV]:
    """Create historical data that would result in overbought RSI."""
    base_date = datetime.now() - timedelta(days=30)
    history = []

    # Create a strong uptrend
    price = 100.0
    for i in range(30):
        price = price + 4  # Strong consistent gains

        ohlcv = OHLCV(
            timestamp=base_date + timedelta(days=i),
            open=price - 2,
            high=price + 1,
            low=price - 3,
            close=price,
            volume=80000000,
            adjusted_close=price,
        )
        history.append(ohlcv)

    return history


@pytest.fixture
def volume_spike_history() -> list[OHLCV]:
    """Create historical data with a volume spike."""
    base_date = datetime.now() - timedelta(days=25)
    history = []

    price = 150.0
    for i in range(25):
        # Normal volume for first 24 days, spike on last day
        if i < 24:
            volume = 50000000
            price_change = 0.5
        else:
            volume = 200000000  # 4x normal volume
            price_change = 5.0  # Big price jump

        price = price + price_change

        ohlcv = OHLCV(
            timestamp=base_date + timedelta(days=i),
            open=price - 1,
            high=price + 2,
            low=price - 2,
            close=price,
            volume=volume,
            adjusted_close=price,
        )
        history.append(ohlcv)

    return history


@pytest.fixture
def mock_data_provider():
    """Create a mock data provider."""
    provider = AsyncMock()
    provider.name = "Mock Provider"
    provider.is_market_open = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_notification_provider():
    """Create a mock notification provider."""
    from stock_sentinel.notifications.base import NotificationResult

    provider = AsyncMock()
    provider.name = "Mock Notifications"
    provider.is_available = AsyncMock(return_value=True)

    def create_result(notification):
        return NotificationResult(
            success=True,
            notification=notification,
            provider="Mock",
            message_id="test-123",
        )

    provider.send = AsyncMock(side_effect=lambda n: create_result(n))
    provider.send_batch = AsyncMock(side_effect=lambda ns: [create_result(n) for n in ns])

    return provider
