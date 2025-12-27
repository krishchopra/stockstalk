"""Stock analyzer service that coordinates indicators and notifications."""

import logging
from typing import Any

from stockstalk.indicators import (
    BaseIndicator,
    MACDIndicator,
    MovingAverageCrossoverIndicator,
    PriceChangeIndicator,
    RSIIndicator,
    VolumeSpikeIndicator,
)
from stockstalk.models import IndicatorResult, WatchlistItem
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.notifier import NotificationService

logger = logging.getLogger(__name__)


class IndicatorRegistry:
    """Registry of available stock indicators."""

    _indicators: dict[str, type[BaseIndicator]] = {
        "RSI": RSIIndicator,
        "MA_Crossover": MovingAverageCrossoverIndicator,
        "Volume_Spike": VolumeSpikeIndicator,
        "Price_Change": PriceChangeIndicator,
        "MACD": MACDIndicator,
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
            raise ValueError(
                f"Indicator '{name}' not found. Available: {available}"
            )

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
    """Analyzes stocks using configured indicators."""

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

    def analyze_stock(self, watchlist_item: WatchlistItem) -> list[IndicatorResult]:
        """
        Analyze a stock using configured indicators.

        Args:
            watchlist_item: Stock to analyze with indicator configuration

        Returns:
            List of indicator results
        """
        results: list[IndicatorResult] = []

        try:
            # Fetch current and historical data
            logger.info(f"Analyzing {watchlist_item.symbol}...")
            current_data = self.data_fetcher.get_current_data(watchlist_item.symbol)
            historical_data = self.data_fetcher.get_historical_data(
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

                    # Send notification if triggered
                    if result.is_triggered:
                        self.notifier.notify(result)

                except Exception as e:
                    logger.error(
                        f"Error running indicator {indicator_name} on {watchlist_item.symbol}: {e}"
                    )

        except Exception as e:
            logger.error(f"Error analyzing {watchlist_item.symbol}: {e}")

        return results
