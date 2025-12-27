"""Beeper notification provider implementation."""

import asyncio
from datetime import datetime

import httpx

from stock_sentinel.config.settings import get_settings
from stock_sentinel.notifications.base import (
    Notification,
    NotificationProvider,
    NotificationResult,
)


class BeeperProvider(NotificationProvider):
    """
    Beeper notification provider for sending SMS messages.

    Beeper is a unified messaging platform that can send messages
    to various platforms including SMS. This implementation uses
    their API to send text notifications.

    Note: You'll need to configure your Beeper API credentials
    in the environment variables.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        sender_id: str | None = None,
    ):
        """
        Initialize Beeper provider.

        Args:
            api_url: Beeper API URL (overrides settings)
            api_key: Beeper API key (overrides settings)
            sender_id: Sender ID or phone number (overrides settings)
        """
        settings = get_settings()
        self.api_url = api_url or settings.beeper_api_url
        self.api_key = api_key or settings.beeper_api_key.get_secret_value()
        self.sender_id = sender_id or settings.beeper_sender_id
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """Get provider name."""
        return "Beeper"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def send(self, notification: Notification) -> NotificationResult:
        """Send a notification via Beeper."""
        if not self.api_key:
            return NotificationResult(
                success=False,
                notification=notification,
                provider=self.name,
                error="Beeper API key not configured",
            )

        try:
            client = await self._get_client()

            # Beeper API payload (adjust based on actual Beeper API spec)
            payload = {
                "to": notification.recipient,
                "from": self.sender_id,
                "message": notification.formatted_message,
                "priority": notification.priority.value,
            }

            response = await client.post("/messages/send", json=payload)

            if response.status_code == 200:
                data = response.json()
                return NotificationResult(
                    success=True,
                    notification=notification,
                    provider=self.name,
                    message_id=data.get("message_id"),
                    sent_at=datetime.now(),
                )
            else:
                return NotificationResult(
                    success=False,
                    notification=notification,
                    provider=self.name,
                    error=f"API error: {response.status_code} - {response.text}",
                )

        except httpx.TimeoutException:
            return NotificationResult(
                success=False,
                notification=notification,
                provider=self.name,
                error="Request timed out",
            )
        except httpx.HTTPError as e:
            return NotificationResult(
                success=False,
                notification=notification,
                provider=self.name,
                error=f"HTTP error: {e!s}",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                notification=notification,
                provider=self.name,
                error=f"Unexpected error: {e!s}",
            )

    async def send_batch(self, notifications: list[Notification]) -> list[NotificationResult]:
        """Send multiple notifications."""
        tasks = [self.send(notification) for notification in notifications]
        return await asyncio.gather(*tasks)

    async def is_available(self) -> bool:
        """Check if Beeper provider is available."""
        if not self.api_key:
            return False

        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            # If we can't check health, assume available if key is set
            return bool(self.api_key)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if self._client and not self._client.is_closed:
            # Can't await in __del__, so just mark for cleanup
            pass
