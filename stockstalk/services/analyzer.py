"""Async stock analyzer service that coordinates indicators and notifications."""

import logging
from typing import Any

from stockstalk.indicators import (
    BaseIndicator,
    # Technical indicators
    MACDIndicator,
    MovingAverageCrossoverIndicator,
    PriceChangeIndicator,
    RSIIndicator,
    VolumeSpikeIndicator,
    # Fundamental indicators
    DebtToEquityIndicator,
    EarningsGrowthIndicator,
    FreeCashFlowIndicator,
    FundamentalScoreIndicator,
    OperatingMarginsIndicator,
    PEGRatioIndicator,
    RevenueGrowthIndicator,
    ROICIndicator,
)
from stockstalk.models import IndicatorResult, WatchlistItem
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.notifier import NotificationService
from stockstalk.settings import settings
from stockstalk.storage import get_database

logger = logging.getLogger(__name__)


class IndicatorRegistry:
    """Registry of available stock indicators."""

    _indicators: dict[str, type[BaseIndicator]] = {
        # Technical indicators
        "RSI": RSIIndicator,
        "MA_Crossover": MovingAverageCrossoverIndicator,
        "Volume_Spike": VolumeSpikeIndicator,
        "Price_Change": PriceChangeIndicator,
        "MACD": MACDIndicator,
        # Fundamental indicators
        "PEG_Ratio": PEGRatioIndicator,
        "Debt_To_Equity": DebtToEquityIndicator,
        "Operating_Margins": OperatingMarginsIndicator,
        "ROIC": ROICIndicator,
        "Free_Cash_Flow": FreeCashFlowIndicator,
        "Revenue_Growth": RevenueGrowthIndicator,
        "Earnings_Growth": EarningsGrowthIndicator,
        "Fundamental_Score": FundamentalScoreIndicator,
    }

    @classmethod
    def get_indicator(cls, name: str, **params: Any) -> BaseIndicator:
        """
        Get an indicator instance by name.

        Args:
            name: Name of the indicator
            **params: Parameters to pass to the indicator

        Returns:
            Indicator instance

        Raises:
            ValueError: If indicator name is not found
        """
        if name not in cls._indicators:
            available = ", ".join(cls._indicators.keys())
            raise ValueError(f"Indicator '{name}' not found. Available: {available}")

        return cls._indicators[name](**params)

    @classmethod
    def list_indicators(cls) -> list[str]:
        """Get list of available indicator names."""
        return list(cls._indicators.keys())

    @classmethod
    def register_indicator(cls, name: str, indicator_class: type[BaseIndicator]) -> None:
        """
        Register a custom indicator.

        Args:
            name: Name for the indicator
            indicator_class: Indicator class to register
        """
        cls._indicators[name] = indicator_class
        logger.info(f"Registered custom indicator: {name}")


class StockAnalyzer:
    """Async analyzer for stocks using configured indicators."""

    def __init__(
        self,
        data_fetcher: StockDataFetcher,
        notifier: NotificationService,
        lookback_days: int = 30,
    ) -> None:
        """
        Initialize stock analyzer.

        Args:
            data_fetcher: Service for fetching stock data
            notifier: Service for sending notifications
            lookback_days: Days of historical data to analyze
        """
        self.data_fetcher = data_fetcher
        self.notifier = notifier
        self.lookback_days = lookback_days
        # Get settings from environment
        self.cooldown_minutes = settings.COOLDOWN_MINUTES
        self.max_alerts_per_hour = settings.MAX_ALERTS_PER_HOUR

    async def _should_send_alert(self, result: IndicatorResult) -> bool:
        """
        Check if an alert should be sent (respecting cooldowns and rate limits).

        Args:
            result: The indicator result to check

        Returns:
            True if alert should be sent
        """
        if not result.is_triggered:
            return False

        try:
            db = get_database()

            # Check cooldown for this symbol/indicator combination
            recent_alert = await db.get_recent_alert(
                symbol=result.symbol,
                indicator=result.indicator_name,
                cooldown_minutes=self.cooldown_minutes,
            )

            if recent_alert is not None:
                logger.debug(
                    f"Skipping alert for {result.symbol}/{result.indicator_name} - "
                    f"recent alert exists (cooldown: {self.cooldown_minutes}m)"
                )
                return False

            # Check hourly rate limit
            alerts_count = await db.get_alerts_count_since(minutes=60)
            if alerts_count >= self.max_alerts_per_hour:
                logger.warning(
                    f"Hourly alert limit reached ({alerts_count}/{self.max_alerts_per_hour}), "
                    f"skipping alert for {result.symbol}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking alert eligibility: {e}")
            # If DB is unavailable, allow the alert
            return True

    async def _send_alert_to_watchers(self, result: IndicatorResult) -> bool:
        """
        Send an alert to all users watching this symbol and record it.

        Args:
            result: The indicator result to send

        Returns:
            True if alert was sent successfully
        """
        try:
            db = get_database()

            # Get all users watching this symbol
            watchers = await db.get_users_watching_symbol(result.symbol)

            if not watchers:
                logger.debug(f"No users watching {result.symbol}")
                return False

            # Send notifications
            send_results = await self.notifier.send_notification_to_users(result, watchers)

            if not send_results:
                logger.warning(f"No notifications sent for {result.symbol}")
                return False

            # Record the alert in the database
            sent_to = ",".join(send_results.keys())

            await db.add_alert(
                symbol=result.symbol,
                indicator=result.indicator_name,
                message=result.message,
                priority=result.priority.value,
                sent_to=sent_to,
            )

            success_count = sum(1 for success in send_results.values() if success)
            logger.info(
                f"Alert sent for {result.symbol}/{result.indicator_name}: "
                f"{success_count}/{len(send_results)} delivered"
            )

            return success_count > 0

        except Exception as e:
            logger.error(f"Error sending alert for {result.symbol}: {e}")
            return False

    async def analyze_stock(
        self, watchlist_item: WatchlistItem, send_alerts: bool = False
    ) -> list[IndicatorResult]:
        """
        Analyze a stock using configured indicators.

        Args:
            watchlist_item: Stock to analyze with indicator configuration
            send_alerts: If True, send individual alerts (default: False for digest mode)

        Returns:
            List of indicator results
        """
        results: list[IndicatorResult] = []

        try:
            logger.info(f"Analyzing {watchlist_item.symbol}...")

            # Fetch current and historical data in parallel
            current_data, historical_data = await self.data_fetcher.get_stock_data(
                watchlist_item.symbol, self.lookback_days
            )

            # Run each enabled indicator
            for indicator_name in watchlist_item.enabled_indicators:
                try:
                    # Get custom parameters for this indicator
                    params = watchlist_item.custom_params.get(indicator_name, {})
                    indicator = IndicatorRegistry.get_indicator(indicator_name, **params)

                    # Analyze
                    result = indicator.analyze(current_data, historical_data)
                    results.append(result)

                    logger.info(
                        f"  {indicator_name}: triggered={result.is_triggered}, "
                        f"priority={result.priority}, strength={result.signal_strength:.2f}"
                    )

                    # Only send individual alerts if explicitly requested
                    if send_alerts and await self._should_send_alert(result):
                        await self._send_alert_to_watchers(result)

                except Exception as e:
                    logger.error(
                        f"Error running indicator {indicator_name} on {watchlist_item.symbol}: {e}"
                    )

        except Exception as e:
            logger.error(f"Error analyzing {watchlist_item.symbol}: {e}")

        return results

    async def analyze_watchlist(
        self, watchlist: list[WatchlistItem], digest_mode: bool = True
    ) -> dict[str, list[IndicatorResult]]:
        """
        Analyze all stocks in a watchlist.

        Args:
            watchlist: List of watchlist items to analyze
            digest_mode: If True, send one consolidated SMS with all alerts (default)

        Returns:
            Dict mapping symbols to their indicator results
        """
        results: dict[str, list[IndicatorResult]] = {}
        alerts_to_send: list[IndicatorResult] = []

        for item in watchlist:
            item_results = await self.analyze_stock(item, send_alerts=False)
            results[item.symbol] = item_results

            # Collect alerts that pass cooldown check
            for result in item_results:
                if await self._should_send_alert(result):
                    alerts_to_send.append(result)

        # Send consolidated digest or individual alerts
        if alerts_to_send:
            if digest_mode:
                await self._send_digest(alerts_to_send, results)
            else:
                for alert in alerts_to_send:
                    await self._send_alert_to_watchers(alert)

        return results

    async def _send_digest(
        self,
        results: list[IndicatorResult],
        all_results_by_symbol: dict[str, list[IndicatorResult]] | None = None,
    ) -> bool:
        """
        Send a consolidated digest of alerts to all relevant users.

        Args:
            results: List of triggered indicator results
            all_results_by_symbol: All results grouped by symbol (for showing triggered/total)

        Returns:
            True if digest was sent successfully
        """
        try:
            db = get_database()

            # Get all unique symbols in the digest
            symbols = set(r.symbol for r in results)

            # Build a map of symbol -> users watching
            symbol_to_users: dict[str, set[str]] = {}
            for symbol in symbols:
                watchers = await db.get_users_watching_symbol(symbol)
                symbol_to_users[symbol] = set(watchers)

            # Get all users who should receive the digest (anyone watching any symbol)
            all_watchers = set()
            for watchers in symbol_to_users.values():
                all_watchers.update(watchers)

            if not all_watchers:
                logger.warning("No users watching any of the triggered symbols")
                return False

            # For each user, filter to only alerts for symbols they're watching
            for phone_number in all_watchers:
                user_symbols = set()
                for symbol, watchers in symbol_to_users.items():
                    if phone_number in watchers:
                        user_symbols.add(symbol)

                # Filter results to this user's watched symbols
                user_results = [r for r in results if r.symbol in user_symbols]

                if not user_results:
                    continue

                # Build filtered all_results_by_symbol for this user
                user_all_results = {
                    sym: res
                    for sym, res in (all_results_by_symbol or {}).items()
                    if sym in user_symbols
                }

                # Send digest to this user
                send_results = await self.notifier.send_digest_to_users(
                    user_results,
                    [phone_number],
                    all_results_by_symbol=user_all_results,
                )

                if send_results.get(phone_number):
                    logger.info(f"Digest sent to {phone_number} with {len(user_results)} alerts")

            # Record all alerts in database
            for result in results:
                # Get watchers for this specific symbol
                watchers = symbol_to_users.get(result.symbol, set())
                sent_to = ",".join(watchers)

                await db.add_alert(
                    symbol=result.symbol,
                    indicator=result.indicator_name,
                    message=result.message,
                    priority=result.priority.value,
                    sent_to=sent_to,
                )

            return True

        except Exception as e:
            logger.error(f"Error sending digest: {e}")
            return False
