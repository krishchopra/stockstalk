"""Tests for the webhook server."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class TestWebhookServer:
    """Test suite for webhook server endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the server."""
        # Need to patch database init before importing app
        with patch("stock_sentinel.server.webhook.init_database", new_callable=AsyncMock):
            from stock_sentinel.server.webhook import app

            return TestClient(app)

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_list_indicators(self, client):
        """Test listing indicators endpoint."""
        response = client.get("/api/indicators")

        assert response.status_code == 200
        data = response.json()
        assert "indicators" in data
        assert len(data["indicators"]) >= 6  # Our built-in indicators

        # Check indicator structure
        indicator = data["indicators"][0]
        assert "name" in indicator
        assert "description" in indicator
        assert "required_history_days" in indicator


class TestCommandHandler:
    """Test suite for the command handler."""

    @pytest.fixture
    def handler(self):
        """Create a command handler instance."""
        from stock_sentinel.server.webhook import CommandHandler

        return CommandHandler()

    def test_help_command(self, handler):
        """Test HELP command."""
        from stock_sentinel.server.webhook import IncomingMessage

        async def run_test():
            message = IncomingMessage(sender="+1234567890", message="HELP")
            response = await handler.handle_message(message)

            assert "QUOTE" in response
            assert "CHECK" in response
            assert "WATCH" in response

        import asyncio

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_empty_message(self, handler):
        """Test empty message handling."""
        from stock_sentinel.server.webhook import IncomingMessage

        async def run_test():
            message = IncomingMessage(sender="+1234567890", message="")
            response = await handler.handle_message(message)

            assert "Empty" in response or "HELP" in response

        import asyncio

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_unknown_command(self, handler):
        """Test unknown command handling."""
        from stock_sentinel.server.webhook import IncomingMessage

        async def run_test():
            message = IncomingMessage(sender="+1234567890", message="UNKNOWNCOMMAND123")
            response = await handler.handle_message(message)

            assert "Unknown" in response or "HELP" in response

        import asyncio

        asyncio.get_event_loop().run_until_complete(run_test())
