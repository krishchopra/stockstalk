"""MACD (Moving Average Convergence Divergence) indicator implementation."""

import numpy as np

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData


class MACDIndicator(BaseIndicator):
    """
    MACD (Moving Average Convergence Divergence) indicator.

    MACD shows the relationship between two moving averages.
    A bullish signal occurs when MACD crosses above the signal line.
    A bearish signal occurs when MACD crosses below the signal line.
    """

    @property
    def name(self) -> str:
        """Return the name of the indicator."""
        return "MACD"

    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average."""
        multiplier = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return float(ema)

    def analyze(
        self, current_data: StockData, historical_data: HistoricalData
    ) -> IndicatorResult:
        """Calculate MACD and check for crossover signals."""
        fast_period = self.get_param("fast_period", 12)
        slow_period = self.get_param("slow_period", 26)
        signal_period = self.get_param("signal_period", 9)

        min_required = slow_period + signal_period

        if len(historical_data.close_prices) < min_required:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"Insufficient data for MACD calculation (need {min_required} days)",
                metadata={"macd": None, "signal": None},
            )

        prices = np.array(historical_data.close_prices)

        # Calculate EMAs
        fast_ema = self._calculate_ema(prices[-fast_period:], fast_period)
        slow_ema = self._calculate_ema(prices[-slow_period:], slow_period)

        # Calculate MACD line
        macd = fast_ema - slow_ema

        # Calculate signal line (EMA of MACD)
        # For simplicity, we'll use a moving average of recent MACD values
        # In a real implementation, you'd calculate MACD for each historical point
        macd_values = []
        for i in range(signal_period, len(prices) + 1):
            f_ema = self._calculate_ema(prices[i - fast_period : i], fast_period)
            s_ema = self._calculate_ema(prices[i - slow_period : i], slow_period)
            macd_values.append(f_ema - s_ema)

        signal_line = np.mean(macd_values[-signal_period:])

        # Check for crossover
        if len(macd_values) > 1:
            prev_macd = macd_values[-2]
            prev_signal = np.mean(macd_values[-signal_period - 1 : -1])

            bullish_crossover = prev_macd <= prev_signal and macd > signal_line
            bearish_crossover = prev_macd >= prev_signal and macd < signal_line
        else:
            bullish_crossover = False
            bearish_crossover = False

        is_triggered = bullish_crossover or bearish_crossover

        # Calculate signal strength
        macd_diff = abs(macd - signal_line)
        signal_strength = min(macd_diff / current_data.current_price * 100, 1.0)

        # Generate message
        if bullish_crossover:
            message = (
                f"{current_data.symbol} MACD BULLISH CROSSOVER! "
                f"MACD ({macd:.2f}) crossed above Signal ({signal_line:.2f}). "
                f"Strong BUY signal at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.HIGH
        elif bearish_crossover:
            message = (
                f"{current_data.symbol} MACD BEARISH CROSSOVER! "
                f"MACD ({macd:.2f}) crossed below Signal ({signal_line:.2f}). "
                f"Consider selling at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.MEDIUM
        elif macd > signal_line:
            message = f"{current_data.symbol} MACD is bullish (MACD: {macd:.2f}, Signal: {signal_line:.2f})"
            priority = AlertPriority.LOW
        else:
            message = f"{current_data.symbol} MACD is bearish (MACD: {macd:.2f}, Signal: {signal_line:.2f})"
            priority = AlertPriority.LOW

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={
                "macd": float(macd),
                "signal_line": float(signal_line),
                "histogram": float(macd - signal_line),
                "bullish_crossover": bullish_crossover,
                "bearish_crossover": bearish_crossover,
            },
        )
