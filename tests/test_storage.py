"""Tests for database storage."""

from stock_sentinel.storage.database import (
    AlertRecord,
)


class TestDatabase:
    """Test suite for database operations."""

    async def test_database_init(self, test_database):
        """Test database initialization."""
        assert test_database is not None

    async def test_add_to_watchlist(self, test_database):
        """Test adding a symbol to watchlist."""
        item = await test_database.add_to_watchlist("AAPL", notes="Apple Inc")

        assert item.symbol == "AAPL"
        assert item.enabled is True
        assert item.notes == "Apple Inc"

    async def test_add_duplicate_to_watchlist(self, test_database):
        """Test adding duplicate symbol re-enables it."""
        await test_database.add_to_watchlist("GOOGL")
        await test_database.remove_from_watchlist("GOOGL")

        # Re-add should enable
        item = await test_database.add_to_watchlist("GOOGL")

        assert item.enabled is True

    async def test_remove_from_watchlist(self, test_database):
        """Test removing from watchlist."""
        await test_database.add_to_watchlist("MSFT")

        removed = await test_database.remove_from_watchlist("MSFT")

        assert removed is True

        # Should be disabled, not deleted
        items = await test_database.get_watchlist(enabled_only=False)
        msft = next((i for i in items if i.symbol == "MSFT"), None)
        assert msft is not None
        assert msft.enabled is False

    async def test_get_watchlist(self, test_database):
        """Test getting watchlist."""
        await test_database.add_to_watchlist("AAPL")
        await test_database.add_to_watchlist("GOOGL")
        await test_database.add_to_watchlist("MSFT")
        await test_database.remove_from_watchlist("MSFT")

        # Get enabled only
        enabled = await test_database.get_watchlist(enabled_only=True)
        assert len(enabled) >= 2
        assert all(i.enabled for i in enabled)

        # Get all
        all_items = await test_database.get_watchlist(enabled_only=False)
        assert len(all_items) >= 3

    async def test_add_phone_number(self, test_database):
        """Test adding a phone number."""
        phone = await test_database.add_phone_number("+1234567890", label="Work")

        assert phone.phone_number == "+1234567890"
        assert phone.label == "Work"
        assert phone.enabled is True

    async def test_remove_phone_number(self, test_database):
        """Test removing a phone number."""
        await test_database.add_phone_number("+1987654321")

        removed = await test_database.remove_phone_number("+1987654321")

        assert removed is True

    async def test_get_phone_numbers(self, test_database):
        """Test getting phone numbers."""
        await test_database.add_phone_number("+1111111111")
        await test_database.add_phone_number("+2222222222")

        numbers = await test_database.get_phone_numbers()

        assert len(numbers) >= 2
        assert all(n.enabled for n in numbers)

    async def test_add_alert(self, test_database):
        """Test adding an alert record."""
        alert = AlertRecord(
            symbol="AAPL",
            indicator="rsi",
            signal="buy",
            value=25.5,
            message="RSI oversold",
            sent_to="+1234567890",
        )

        saved = await test_database.add_alert(alert)

        assert saved.id is not None
        assert saved.symbol == "AAPL"
        assert saved.indicator == "rsi"

    async def test_get_recent_alerts(self, test_database):
        """Test getting recent alerts."""
        alert = AlertRecord(
            symbol="TSLA",
            indicator="macd",
            signal="buy",
            value=0.5,
            message="MACD crossover",
            sent_to="+1234567890",
        )
        await test_database.add_alert(alert)

        recent = await test_database.get_recent_alerts("TSLA", "macd", minutes=60)

        assert len(recent) >= 1
        assert recent[0].symbol == "TSLA"

    async def test_get_alerts_count_in_hour(self, test_database):
        """Test counting alerts in last hour."""
        for i in range(5):
            alert = AlertRecord(
                symbol=f"SYM{i}",
                indicator="test",
                signal="buy",
                value=0,
                message="Test",
                sent_to="+1234567890",
            )
            await test_database.add_alert(alert)

        count = await test_database.get_alerts_count_in_hour()

        assert count >= 5
