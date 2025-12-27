"""Moving Average Crossover indicator implementation."""

import numpy as np

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData


class MovingAverageCrossoverIndicator(BaseIndicator):
    """
    Moving Average Crossover indicator.

    Compares short-term and long-term moving averages.
    A bullish crossover (golden cross) occurs when the short-term MA crosses above the long-term MA.
    A bearish crossover (death cross) occurs when the short-term MA crosses below the long-term MA.
    """

    @property
    def name(self) -> str:
        """Return the name of the indicator."""
        return "MA_Crossover"

    def analyze(
        self, current_data: StockData, historical_data: HistoricalData
    ) -> IndicatorResult:
        """Calculate moving average crossover and check for signals."""
        short_period = self.get_param("short_period", 10)
        long_period = self.get_param("long_period", 50)

        if len(historical_data.close_prices) < long_period:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"Insufficient data for MA calculation (need {long_period} days)",
                metadata={"short_ma": None, "long_ma": None},
            )

        prices = np.array(historical_data.close_prices)

        # Calculate moving averages
        short_ma = np.mean(prices[-short_period:])
        long_ma = np.mean(prices[-long_period:])

        # Check previous values to detect crossover
        if len(prices) > long_period:
            prev_short_ma = np.mean(prices[-(short_period + 1) : -1])
            prev_long_ma = np.mean(prices[-(long_period + 1) : -1])

            # Detect crossover
            bullish_crossover = prev_short_ma <= prev_long_ma and short_ma > long_ma
            bearish_crossover = prev_short_ma >= prev_long_ma and short_ma < long_ma
        else:
            bullish_crossover = False
            bearish_crossover = False

        is_triggered = bullish_crossover or bearish_crossover

        # Calculate signal strength based on percentage difference
        ma_diff_pct = abs(short_ma - long_ma) / long_ma
        signal_strength = min(ma_diff_pct * 10, 1.0)  # Scale to 0-1

        # Generate message
        if bullish_crossover:
            message = (
                f"{current_data.symbol} GOLDEN CROSS! "
                f"Short MA ({short_period}d: ${short_ma:.2f}) crossed above "
                f"Long MA ({long_period}d: ${long_ma:.2f}). "
                f"Strong BUY signal at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.HIGH
        elif bearish_crossover:
            message = (
                f"{current_data.symbol} DEATH CROSS! "
                f"Short MA ({short_period}d: ${short_ma:.2f}) crossed below "
                f"Long MA ({long_period}d: ${long_ma:.2f}). "
                f"Consider selling at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.MEDIUM
        elif short_ma > long_ma:
            message = (
                f"{current_data.symbol} in uptrend. "
                f"Short MA: ${short_ma:.2f}, Long MA: ${long_ma:.2f}"
            )
            priority = AlertPriority.LOW
        else:
            message = (
                f"{current_data.symbol} in downtrend. "
                f"Short MA: ${short_ma:.2f}, Long MA: ${long_ma:.2f}"
            )
            priority = AlertPriority.LOW

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={
                "short_ma": float(short_ma),
                "long_ma": float(long_ma),
                "short_period": short_period,
                "long_period": long_period,
                "bullish_crossover": bullish_crossover,
                "bearish_crossover": bearish_crossover,
            },
        )
