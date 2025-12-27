"""Notification service for sending alerts via Beeper."""

import logging
from typing import Any

import requests

from stockstalk.models import AlertPriority, IndicatorResult, NotificationConfig

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via Beeper webhook."""

    def __init__(self, config: NotificationConfig) -> None:
        """
        Initialize notification service.

        Args:
            config: Notification configuration
        """
        self.config = config

    def should_notify(self, result: IndicatorResult) -> bool:
        """
        Check if a result should trigger a notification.

        Args:
            result: Indicator result to check

        Returns:
            True if notification should be sent
        """
        if not result.is_triggered:
            return False

        # Check if priority meets minimum threshold
        priority_order = {
            AlertPriority.LOW: 0,
            AlertPriority.MEDIUM: 1,
            AlertPriority.HIGH: 2,
            AlertPriority.CRITICAL: 3,
        }

        return priority_order[result.priority] >= priority_order[self.config.min_priority]

    def send_notification(self, result: IndicatorResult) -> bool:
        """
        Send notification via Beeper.

        Args:
            result: Indicator result to send

        Returns:
            True if notification was sent successfully
        """
        if not self.should_notify(result):
            logger.debug(
                f"Skipping notification for {result.symbol} - "
                f"priority {result.priority} below threshold"
            )
            return False

        if not self.config.beeper_webhook_url:
            logger.warning("Beeper webhook URL not configured, skipping notification")
            return False

        try:
            payload = {
                "text": result.message,
                "priority": result.priority.value,
                "metadata": {
                    "symbol": result.symbol,
                    "indicator": result.indicator_name,
                    "signal_strength": result.signal_strength,
                    "timestamp": result.timestamp.isoformat(),
                    **result.metadata,
                },
            }

            response = requests.post(
                self.config.beeper_webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            logger.info(f"Sent notification for {result.symbol} via Beeper: {result.message}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Beeper notification: {str(e)}")
            return False

    def send_sms_notifications(self, result: IndicatorResult) -> bool:
        """
        Send SMS notifications to configured phone numbers.

        Note: This requires Twilio or similar SMS service to be configured.
        For now, this is a placeholder that logs the notification.

        Args:
            result: Indicator result to send

        Returns:
            True if notifications were sent successfully
        """
        if not self.should_notify(result):
            return False

        if not self.config.phone_numbers:
            logger.debug("No phone numbers configured for SMS notifications")
            return False

        # TODO: Implement actual SMS sending via Twilio
        # This is currently a placeholder that only logs messages.
        # To enable SMS:
        # 1. Install twilio: pip install twilio
        # 2. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER env vars
        # 3. Implement actual SMS sending using Twilio client
        logger.warning(
            "SMS notifications are not yet implemented. "
            "Messages are being logged instead of sent."
        )
        for phone_number in self.config.phone_numbers:
            logger.info(f"Would send SMS to {phone_number}: {result.message}")

        return True

    def notify(self, result: IndicatorResult) -> None:
        """
        Send notifications via all configured channels.

        Args:
            result: Indicator result to send
        """
        self.send_notification(result)
        self.send_sms_notifications(result)
