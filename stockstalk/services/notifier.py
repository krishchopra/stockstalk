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
            logger.debug("No alerts meet notification threshold for digest")
            return {}

        if not self.config.phone_numbers:
            logger.warning("No phone numbers configured for notifications")
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

        # Group results by symbol while preserving priority order
        by_symbol: dict[str, list[IndicatorResult]] = {}
        symbol_order: list[str] = []
        for r in results:
            if r.symbol not in by_symbol:
                by_symbol[r.symbol] = []
                symbol_order.append(r.symbol)
            by_symbol[r.symbol].append(r)

        # Build message grouped by stock
        lines = ["📊 StockStalk Top Signals:"]

        for symbol in symbol_order[:10]:  # Limit to top 10 stocks
            symbol_results = by_symbol[symbol]
            triggered_count = len(symbol_results)

            # Get total indicators for this symbol if available
            if all_results_by_symbol and symbol in all_results_by_symbol:
                total_indicators = len(all_results_by_symbol[symbol])
            else:
                total_indicators = triggered_count

            # Get highest priority emoji
            priorities = [r.priority for r in symbol_results]
            if AlertPriority.CRITICAL in priorities:
                emoji = "🚨"
            elif AlertPriority.HIGH in priorities:
                emoji = "🔔"
            else:
                emoji = "📈"

            # Get short messages for top 3 indicators for this stock
            top_metrics = [self._get_short_message(r) for r in symbol_results[:3]]
            metrics_str = ", ".join(top_metrics)

            # Format: 🔔 NVDA (4/5): ROIC 107%, EPS +67%, Rev +63%
            lines.append(f"{emoji} {symbol} ({triggered_count}/{total_indicators}): {metrics_str}")

        # Add count summary
        if total_count > len(results):
            lines.append(f"\nTop {len(by_symbol)} stocks ({len(results)} signals)")

        return "\n".join(lines)

    def _get_short_message(self, result: IndicatorResult) -> str:
        """Extract a short message with key metrics from an indicator result."""
        meta = result.metadata
        name = result.indicator_name

        # Volume Spike - show ratio and price change
        if name == "Volume_Spike" and meta.get("volume_ratio"):
            ratio = meta["volume_ratio"]
            pct = meta.get("price_change_pct", 0)
            direction = "↑" if pct > 0 else "↓"
            return f"Vol {ratio:.1f}x avg, price {direction}{abs(pct):.1f}%"

        # RSI - show value and condition
        if name == "RSI" and meta.get("rsi"):
            rsi = meta["rsi"]
            if rsi >= 70:
                return f"RSI {rsi:.0f} OVERBOUGHT"
            elif rsi <= 30:
                return f"RSI {rsi:.0f} OVERSOLD"
            return f"RSI {rsi:.0f}"

        # ROIC
        if name == "ROIC" and meta.get("roic_estimate"):
            roic = meta["roic_estimate"] * 100
            return f"ROIC {roic:.0f}%"

        # Operating Margins
        if name == "Operating_Margins" and meta.get("operating_margins"):
            margin = meta["operating_margins"] * 100
            return f"Op Margin {margin:.0f}%"

        # Revenue Growth
        if name == "Revenue_Growth" and meta.get("revenue_growth"):
            growth = meta["revenue_growth"] * 100
            return f"Rev +{growth:.0f}%"

        # Earnings Growth
        if name == "Earnings_Growth" and meta.get("earnings_growth"):
            growth = meta["earnings_growth"] * 100
            return f"EPS +{growth:.0f}%"

        # Free Cash Flow
        if name == "Free_Cash_Flow" and meta.get("fcf"):
            fcf = meta["fcf"]
            if fcf >= 1e9:
                return f"FCF ${fcf / 1e9:.1f}B"
            elif fcf >= 1e6:
                return f"FCF ${fcf / 1e6:.0f}M"
            return f"FCF ${fcf:,.0f}"

        # Debt to Equity
        if name == "Debt_To_Equity" and meta.get("debt_to_equity") is not None:
            de = meta["debt_to_equity"]
            return f"D/E {de:.2f}"

        # Price Change
        if name == "Price_Change" and meta.get("price_change_pct"):
            pct = meta["price_change_pct"]
            direction = "↑" if pct > 0 else "↓"
            return f"Price {direction}{abs(pct):.1f}%"

        # Fundamental Score
        if name == "Fundamental_Score" and meta.get("score") is not None:
            score = meta["score"]
            max_score = meta.get("max_score", 7)
            return f"Score {score}/{max_score}"

        # MACD
        if name == "MACD":
            if "bullish" in result.message.lower():
                return "MACD bullish crossover"
            elif "bearish" in result.message.lower():
                return "MACD bearish crossover"
            return "MACD signal"

        # Fallback - use first part of message
        msg = result.message
        # Remove symbol prefix if present
        if msg.startswith(result.symbol):
            msg = msg[len(result.symbol) :].strip(" :-")
        # Truncate if too long
        if len(msg) > 40:
            msg = msg[:37] + "..."
        return msg
