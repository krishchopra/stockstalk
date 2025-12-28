"""Notification service for sending alerts via AWS SNS."""

import logging
import os
from typing import Any

import aioboto3

from stockstalk.models import AlertPriority, IndicatorResult, NotificationConfig

logger = logging.getLogger(__name__)


class NotificationService:
    """Async service for sending SMS notifications via AWS SNS."""

    def __init__(self, config: NotificationConfig) -> None:
        """
        Initialize notification service.

        Args:
            config: Notification configuration
        """
        self.config = config
        self._session = aioboto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )

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

    async def send_sms(self, phone_number: str, message: str) -> bool:
        """
        Send a single SMS via AWS SNS.

        Args:
            phone_number: Phone number in E.164 format (e.g., +14155551234)
            message: Message to send

        Returns:
            True if message was sent successfully
        """
        try:
            async with self._session.client("sns") as sns:
                response = await sns.publish(
                    PhoneNumber=phone_number,
                    Message=message,
                    MessageAttributes={
                        "AWS.SNS.SMS.SMSType": {
                            "DataType": "String",
                            "StringValue": "Transactional",  # Higher delivery priority
                        }
                    },
                )
                message_id = response.get("MessageId")
                logger.info(f"SMS sent to {phone_number}, MessageId: {message_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {e}")
            return False

    async def send_notification(self, result: IndicatorResult) -> dict[str, bool]:
        """
        Send SMS notifications to all configured phone numbers.

        Args:
            result: Indicator result to send

        Returns:
            Dict mapping phone numbers to success status
        """
        results: dict[str, bool] = {}

        if not self.should_notify(result):
            logger.debug(
                f"Skipping notification for {result.symbol} - "
                f"priority {result.priority} below threshold"
            )
            return results

        if not self.config.phone_numbers:
            logger.warning("No phone numbers configured for notifications")
            return results

        # Format the message
        message = self._format_message(result)

        # Send to all phone numbers
        for phone_number in self.config.phone_numbers:
            success = await self.send_sms(phone_number, message)
            results[phone_number] = success

        return results

    def _format_message(self, result: IndicatorResult) -> str:
        """Format indicator result into SMS message."""
        # Keep it concise for SMS
        priority_emoji = {
            AlertPriority.LOW: "📊",
            AlertPriority.MEDIUM: "📈",
            AlertPriority.HIGH: "🔔",
            AlertPriority.CRITICAL: "🚨",
        }
        emoji = priority_emoji.get(result.priority, "📊")
        return f"{emoji} {result.symbol}: {result.message}"

    async def notify(self, result: IndicatorResult) -> dict[str, bool]:
        """
        Send notifications via all configured channels.

        Args:
            result: Indicator result to send

        Returns:
            Dict mapping phone numbers to success status
        """
        return await self.send_notification(result)

    async def send_test_message(self, phone_number: str) -> bool:
        """
        Send a test SMS to verify configuration.

        Args:
            phone_number: Phone number to test

        Returns:
            True if test message was sent successfully
        """
        return await self.send_sms(
            phone_number,
            "🧪 StockStalk test message - your notifications are working!",
        )

    async def send_digest(self, results: list[IndicatorResult]) -> dict[str, bool]:
        """
        Send a consolidated digest of multiple alerts in one SMS.

        Args:
            results: List of indicator results to include in digest

        Returns:
            Dict mapping phone numbers to success status
        """
        # Filter to only triggered results that meet priority threshold
        triggered = [r for r in results if self.should_notify(r)]

        if not triggered:
            logger.debug("No alerts meet notification threshold for digest")
            return {}

        if not self.config.phone_numbers:
            logger.warning("No phone numbers configured for notifications")
            return {}

        # Format digest message
        message = self._format_digest(triggered)

        # Send to all phone numbers
        send_results: dict[str, bool] = {}
        for phone_number in self.config.phone_numbers:
            success = await self.send_sms(phone_number, message)
            send_results[phone_number] = success

        return send_results

    def _format_digest(self, results: list[IndicatorResult]) -> str:
        """Format multiple results into a single digest message."""
        # Group by symbol
        by_symbol: dict[str, list[IndicatorResult]] = {}
        for r in results:
            if r.symbol not in by_symbol:
                by_symbol[r.symbol] = []
            by_symbol[r.symbol].append(r)

        # Build compact message (SMS limit ~160 chars, but SNS can do longer)
        lines = ["📊 StockStalk Alert Summary:"]

        for symbol, symbol_results in by_symbol.items():
            # Get highest priority for this symbol
            priorities = [r.priority for r in symbol_results]
            if AlertPriority.CRITICAL in priorities:
                emoji = "🚨"
            elif AlertPriority.HIGH in priorities:
                emoji = "🔔"
            else:
                emoji = "📈"

            # Summarize indicators
            indicators = [r.indicator_name.replace("_", " ") for r in symbol_results]
            lines.append(f"{emoji} {symbol}: {', '.join(indicators)}")

        # Add count summary
        lines.append(f"Total: {len(results)} signals across {len(by_symbol)} stocks")

        return "\n".join(lines)
