"""Tests for Beeper notification provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stock_sentinel.notifications.base import Notification, NotificationPriority
from stock_sentinel.notifications.beeper import BeeperProvider


class TestBeeperProvider:
    """Test suite for Beeper notification provider."""

    @pytest.fixture
    def beeper_provider(self):
        """Create a Beeper provider with test credentials."""
        return BeeperProvider(
            api_url="https://api.beeper.test",
            api_key="test_key_123",
            sender_id="+1234567890",
        )

    @pytest.fixture
    def sample_notification(self):
        """Create a sample notification."""
        return Notification(
            recipient="+1987654321",
            message="Test alert: AAPL is oversold!",
            priority=NotificationPriority.HIGH,
        )

    def test_beeper_provider_name(self, beeper_provider):
        """Test provider name."""
        assert beeper_provider.name == "Beeper"

    async def test_send_without_api_key(self):
        """Test send fails without API key."""
        provider = BeeperProvider(api_key="")
        notification = Notification(
            recipient="+1234567890",
            message="Test",
        )

        result = await provider.send(notification)

        assert result.success is False
        assert "not configured" in result.error.lower()

    async def test_send_success(self, beeper_provider, sample_notification):
        """Test successful message send."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": "msg_123"}

        with patch.object(beeper_provider, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            result = await beeper_provider.send(sample_notification)

            assert result.success is True
            assert result.message_id == "msg_123"
            assert result.provider == "Beeper"

    async def test_send_api_error(self, beeper_provider, sample_notification):
        """Test handling API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch.object(beeper_provider, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            result = await beeper_provider.send(sample_notification)

            assert result.success is False
            assert "API error" in result.error

    async def test_send_timeout(self, beeper_provider, sample_notification):
        """Test handling timeout errors."""
        with patch.object(beeper_provider, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.return_value.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            result = await beeper_provider.send(sample_notification)

            assert result.success is False
            assert "timed out" in result.error.lower()

    async def test_send_batch(self, beeper_provider):
        """Test sending batch notifications."""
        notifications = [
            Notification(recipient=f"+1{i}00000000", message=f"Test {i}") for i in range(3)
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": "msg_batch"}

        with patch.object(beeper_provider, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            results = await beeper_provider.send_batch(notifications)

            assert len(results) == 3
            assert all(r.success for r in results)

    async def test_is_available_with_key(self, beeper_provider):
        """Test availability check with API key."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(beeper_provider, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            is_available = await beeper_provider.is_available()

            assert is_available is True

    async def test_is_available_without_key(self):
        """Test availability check without API key."""
        provider = BeeperProvider(api_key="")

        is_available = await provider.is_available()

        assert is_available is False


class TestNotification:
    """Test suite for Notification model."""

    def test_notification_creation(self):
        """Test creating a notification."""
        notification = Notification(
            recipient="+1234567890",
            message="Test message",
            priority=NotificationPriority.HIGH,
        )

        assert notification.recipient == "+1234567890"
        assert notification.message == "Test message"
        assert notification.priority == NotificationPriority.HIGH

    def test_notification_formatted_message(self):
        """Test formatted message includes timestamp."""
        notification = Notification(
            recipient="+1234567890",
            message="Test message",
        )

        formatted = notification.formatted_message

        assert "Test message" in formatted
        assert "[" in formatted  # Has timestamp brackets
