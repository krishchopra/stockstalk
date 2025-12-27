"""Base notification provider abstract class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NotificationPriority(str, Enum):
    """Priority level for notifications."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """Notification message to be sent."""

    recipient: str  # Phone number or chat ID
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    @property
    def formatted_message(self) -> str:
        """Format message with timestamp."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] {self.message}"


@dataclass
class NotificationResult:
    """Result of sending a notification."""

    success: bool
    notification: Notification
    provider: str
    message_id: str | None = None
    error: str | None = None
    sent_at: datetime = field(default_factory=datetime.now)


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name."""
        ...

    @abstractmethod
    async def send(self, notification: Notification) -> NotificationResult:
        """
        Send a notification.

        Args:
            notification: Notification to send

        Returns:
            NotificationResult with success/failure status
        """
        ...

    @abstractmethod
    async def send_batch(self, notifications: list[Notification]) -> list[NotificationResult]:
        """
        Send multiple notifications.

        Args:
            notifications: List of notifications to send

        Returns:
            List of NotificationResults
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the provider is available and configured.

        Returns:
            True if provider can send notifications
        """
        ...
