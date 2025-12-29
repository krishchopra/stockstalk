"""Notification service for sending alerts via Twilio SMS."""

import logging
import os

import httpx

from stockstalk.models import AlertPriority, IndicatorResult, NotificationConfig

logger = logging.getLogger(__name__)


class NotificationService:
    """Async service for sending SMS notifications via Twilio."""

    TWILIO_API_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    def __init__(self, config: NotificationConfig) -> None:
        """
        Initialize notification service.

        Args:
            config: Notification configuration
        """
        self.config = config
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER", "")

        if not all([self.account_sid, self.auth_token, self.from_number]):
            logger.warning(
                "Twilio credentials not fully configured. "
                "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER"
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
            logger.debug(f"  {result.symbol}/{result.indicator_name}: not triggered")
            return False

        # Check if priority meets minimum threshold
        priority_order = {
            AlertPriority.LOW: 0,
            AlertPriority.MEDIUM: 1,
            AlertPriority.HIGH: 2,
            AlertPriority.CRITICAL: 3,
        }

        meets_threshold = (
            priority_order[result.priority] >= priority_order[self.config.min_priority]
        )
        if not meets_threshold:
            logger.info(
                f"  {result.symbol}/{result.indicator_name}: priority {result.priority.value} "
                f"< min threshold {self.config.min_priority.value}"
            )
        return meets_threshold

    async def send_sms(self, phone_number: str, message: str) -> bool:
        """
        Send a single SMS via Twilio.

        Args:
            phone_number: Phone number in E.164 format (e.g., +14155551234)
            message: Message to send

        Returns:
            True if message was sent successfully
        """
        if not all([self.account_sid, self.auth_token, self.from_number]):
            logger.error("twilio credentials not configured")
            return False

        url = self.TWILIO_API_URL.format(account_sid=self.account_sid)

        # Clean up phone number format (remove dashes)
        clean_to_number = phone_number.replace("-", "")
        clean_from_number = self.from_number.replace("-", "")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    auth=(self.account_sid, self.auth_token),
                    data={
                        "To": clean_to_number,
                        "From": clean_from_number,
                        "Body": message,
                    },
                )

                if response.status_code == 201:
                    data = response.json()
                    sid = data.get("sid", "unknown")
                    logger.info(f"sms sent to {phone_number}, sid: {sid}")
                    return True
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("message", response.text)
                    logger.error(f"twilio error ({response.status_code}): {error_msg}")
                    return False

        except Exception as e:
            logger.error(f"failed to send sms to {phone_number}: {e}", exc_info=True)
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
                f"skipping notification for {result.symbol} - "
                f"priority {result.priority} below threshold"
            )
            return results

        if not self.config.phone_numbers:
            logger.warning("no phone numbers configured for notifications")
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
        priority_label = {
            AlertPriority.LOW: "",
            AlertPriority.MEDIUM: "",
            AlertPriority.HIGH: "[!] ",
            AlertPriority.CRITICAL: "[!!] ",
        }
        prefix = priority_label.get(result.priority, "")
        return f"{prefix}{result.symbol}: {result.message}".lower()

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
            "stockstalk test - notifications are working",
        )

    async def send_digest(
        self,
        results: list[IndicatorResult],
        max_alerts: int = 10,
        all_results_by_symbol: dict[str, list[IndicatorResult]] | None = None,
    ) -> dict[str, bool]:
        """
        Send a consolidated digest of top alerts in one SMS.

        Args:
            results: List of indicator results to include in digest
            max_alerts: Maximum number of alerts to include (default: 10)
            all_results_by_symbol: All results grouped by symbol (for showing triggered/total)

        Returns:
            Dict mapping phone numbers to success status
        """
        # Filter to only triggered results that meet priority threshold
        triggered = [r for r in results if self.should_notify(r)]

        if not triggered:
            logger.info("no alerts meet notification threshold for digest")
            return {}

        if not self.config.phone_numbers:
            logger.warning("no phone numbers configured for notifications")
            return {}

        # Sort by priority (CRITICAL > HIGH > MEDIUM) and signal strength
        priority_order = {
            AlertPriority.CRITICAL: 4,
            AlertPriority.HIGH: 3,
            AlertPriority.MEDIUM: 2,
            AlertPriority.LOW: 1,
        }
        triggered.sort(
            key=lambda r: (priority_order[r.priority], r.signal_strength),
            reverse=True,
        )

        # Take only top N alerts
        top_alerts = triggered[:max_alerts]
        total_count = len(triggered)

        # Format digest message with triggered/total counts
        message = self._format_digest(top_alerts, total_count, all_results_by_symbol)

        # Send to all phone numbers
        send_results: dict[str, bool] = {}
        for phone_number in self.config.phone_numbers:
            success = await self.send_sms(phone_number, message)
            send_results[phone_number] = success

        return send_results

    def _format_digest(
        self,
        results: list[IndicatorResult],
        total_count: int | None = None,
        all_results_by_symbol: dict[str, list[IndicatorResult]] | None = None,
    ) -> str:
        """Format top results into a single digest message with key metrics."""
        if total_count is None:
            total_count = len(results)

        # Build compact message
        lines = ["stockstalk alerts:"]

        for symbol, symbol_results in all_results_by_symbol.items():
            # Get highest priority for this symbol
            priorities = [r.priority for r in symbol_results]
            if AlertPriority.CRITICAL in priorities:
                prefix = "[!!] "
            elif AlertPriority.HIGH in priorities:
                prefix = "[!] "
            else:
                prefix = ""

            # Summarize indicators
            indicators = [r.indicator_name.replace("_", " ") for r in symbol_results]
            lines.append(f"{prefix}{symbol}: {', '.join(indicators)}")

        # Add count summary
        lines.append(f"total: {len(results)} signals, {len(all_results_by_symbol)} stocks")

        return "\n".join(lines).lower()
