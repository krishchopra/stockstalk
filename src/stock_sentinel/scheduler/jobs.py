"""Scheduled jobs for stock monitoring."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from stock_sentinel.config.settings import get_settings
from stock_sentinel.data.providers.yahoo import YahooFinanceProvider
from stock_sentinel.indicators import indicator_registry
from stock_sentinel.indicators.base import IndicatorResult
from stock_sentinel.notifications.base import Notification, NotificationPriority
from stock_sentinel.notifications.beeper import BeeperProvider
from stock_sentinel.storage.database import (
    AlertRecord,
    Database,
    get_database,
    init_database,
)

logger = logging.getLogger(__name__)


class StockMonitor:
    """
    Main stock monitoring engine.

    Coordinates data fetching, indicator analysis, and alert notifications.
    """

    def __init__(
        self,
        data_provider: YahooFinanceProvider | None = None,
        notification_provider: BeeperProvider | None = None,
        database: Database | None = None,
    ):
        """
        Initialize stock monitor.

        Args:
            data_provider: Stock data provider
            notification_provider: Notification provider
            database: Database instance
        """
        self.data_provider = data_provider or YahooFinanceProvider()
        self.notification_provider = notification_provider or BeeperProvider()
        self.database = database
        self.settings = get_settings()
        self._alert_callbacks: list[Callable[[IndicatorResult], None]] = []

    def add_alert_callback(self, callback: Callable[[IndicatorResult], None]) -> None:
        """Add a callback to be called when an alert is triggered."""
        self._alert_callbacks.append(callback)

    async def _get_database(self) -> Database:
        """Get database instance."""
        if self.database is None:
            self.database = get_database()
        return self.database

    async def check_stock(self, symbol: str) -> list[IndicatorResult]:
        """
        Check a single stock with all indicators.

        Args:
            symbol: Stock symbol to check

        Returns:
            List of indicator results that triggered alerts
        """
        try:
            # Fetch stock data
            stock_data = await self.data_provider.get_stock_data(
                symbol, period="3mo", interval="1d"
            )

            # Run all indicators
            results = await indicator_registry.analyze_all(stock_data)

            # Filter for alerts
            alerts = [r for r in results if r.should_alert]

            return alerts

        except Exception as e:
            logger.error(f"Error checking stock {symbol}: {e}")
            return []

    async def check_watchlist(self) -> list[IndicatorResult]:
        """
        Check all stocks in the watchlist.

        Returns:
            List of all indicator results that triggered alerts
        """
        db = await self._get_database()
        watchlist = await db.get_watchlist(enabled_only=True)

        # Use default watchlist from settings if empty
        symbols = self.settings.watchlist if not watchlist else [item.symbol for item in watchlist]

        logger.info(f"Checking {len(symbols)} stocks: {', '.join(symbols)}")

        all_alerts: list[IndicatorResult] = []

        for symbol in symbols:
            alerts = await self.check_stock(symbol)
            all_alerts.extend(alerts)

        return all_alerts

    async def _should_send_alert(self, result: IndicatorResult) -> bool:
        """Check if alert should be sent (respecting cooldowns)."""
        db = await self._get_database()

        # Check cooldown
        recent = await db.get_recent_alerts(
            symbol=result.symbol,
            indicator=result.indicator_name,
            minutes=self.settings.cooldown_minutes,
        )

        if recent:
            logger.debug(
                f"Skipping alert for {result.symbol}/{result.indicator_name} - "
                f"recent alert exists"
            )
            return False

        # Check hourly limit
        count = await db.get_alerts_count_in_hour()
        if count >= self.settings.max_alerts_per_hour:
            logger.warning("Hourly alert limit reached, skipping alert")
            return False

        return True

    async def _send_alert(self, result: IndicatorResult) -> bool:
        """Send alert notification for an indicator result."""
        db = await self._get_database()
        phone_numbers = await db.get_phone_numbers(enabled_only=True)

        if not phone_numbers:
            logger.warning("No phone numbers configured for notifications")
            return False

        # Create notifications for each phone number
        notifications = [
            Notification(
                recipient=phone.phone_number,
                message=result.alert_message,
                priority=(
                    NotificationPriority.HIGH
                    if result.signal.is_bullish
                    else NotificationPriority.NORMAL
                ),
                metadata={"symbol": result.symbol, "indicator": result.indicator_name},
            )
            for phone in phone_numbers
        ]

        # Send notifications
        results = await self.notification_provider.send_batch(notifications)

        # Record alert
        sent_to = ",".join(phone.phone_number for phone in phone_numbers)
        alert_record = AlertRecord(
            symbol=result.symbol,
            indicator=result.indicator_name,
            signal=result.signal.value,
            value=result.value,
            message=result.message,
            sent_to=sent_to,
        )
        await db.add_alert(alert_record)

        # Call callbacks
        for callback in self._alert_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"Alert sent for {result.symbol}: {result.message} "
            f"({success_count}/{len(results)} delivered)"
        )

        return success_count > 0

    async def run_check(self) -> None:
        """
        Run a complete check cycle.

        This is the main entry point for scheduled checks.
        """
        # Check if market is open (if configured)
        if self.settings.market_hours_only:
            is_open = await self.data_provider.is_market_open()
            if not is_open:
                logger.debug("Market is closed, skipping check")
                return

        logger.info(f"Starting stock check at {datetime.now()}")

        try:
            alerts = await self.check_watchlist()

            for alert in alerts:
                if await self._should_send_alert(alert):
                    await self._send_alert(alert)

            logger.info(f"Check complete. {len(alerts)} alerts triggered.")

        except Exception as e:
            logger.error(f"Error during stock check: {e}")
            raise


async def run_scheduler() -> None:
    """Run the stock monitoring scheduler."""
    settings = get_settings()

    # Initialize database
    await init_database()

    # Create monitor
    monitor = StockMonitor()

    # Create scheduler
    scheduler = AsyncIOScheduler()

    # Add job based on settings
    if settings.market_hours_only:
        # Run every N minutes during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
        scheduler.add_job(
            monitor.run_check,
            CronTrigger(
                day_of_week="mon-fri",
                hour="9-16",
                minute=f"*/{settings.check_interval_minutes}",
                timezone="America/New_York",
            ),
            id="stock_check_market_hours",
            name="Stock Check (Market Hours)",
        )
    else:
        # Run every N minutes continuously
        scheduler.add_job(
            monitor.run_check,
            IntervalTrigger(minutes=settings.check_interval_minutes),
            id="stock_check_continuous",
            name="Stock Check (Continuous)",
        )

    logger.info(f"Scheduler started. Checking every {settings.check_interval_minutes} minutes.")
    logger.info(f"Market hours only: {settings.market_hours_only}")

    scheduler.start()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()
