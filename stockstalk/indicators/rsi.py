"""RSI (Relative Strength Index) indicator implementation."""

import numpy as np

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData


class RSIIndicator(BaseIndicator):
    """
    RSI (Relative Strength Index) indicator.

    RSI measures the speed and magnitude of price changes.
    Values below 30 indicate oversold (potential buy).
    Values above 70 indicate overbought (potential sell).
    """

    @property
    def name(self) -> str:
        """Return the name of the indicator."""
        return "RSI"

    def analyze(
        self, current_data: StockData, historical_data: HistoricalData
    ) -> IndicatorResult:
        """Calculate RSI and check for buy signals."""
        period = self.get_param("period", 14)
        oversold_threshold = self.get_param("oversold_threshold", 30)
        overbought_threshold = self.get_param("overbought_threshold", 70)

        if len(historical_data.close_prices) < period + 1:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"Insufficient data for RSI calculation (need {period + 1} days)",
                metadata={"rsi": None},
            )

        # Calculate price changes
        prices = np.array(historical_data.close_prices)
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gains and losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        # Calculate RSI
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # Determine if triggered
        is_oversold = rsi < oversold_threshold
        is_overbought = rsi > overbought_threshold
        is_triggered = is_oversold or is_overbought

        # Calculate signal strength (how far from neutral 50)
        signal_strength = abs(rsi - 50) / 50

        # Generate message
        if is_oversold:
            message = (
                f"{current_data.symbol} is OVERSOLD (RSI: {rsi:.2f}). "
                f"Potential BUY opportunity at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.HIGH if rsi < 25 else AlertPriority.MEDIUM
        elif is_overbought:
            message = (
                f"{current_data.symbol} is OVERBOUGHT (RSI: {rsi:.2f}). "
                f"Consider taking profits at ${current_data.current_price:.2f}"
            )
            priority = AlertPriority.MEDIUM
        else:
            message = f"{current_data.symbol} RSI is neutral at {rsi:.2f}"
            priority = AlertPriority.LOW

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={
                "rsi": float(rsi),
                "oversold_threshold": oversold_threshold,
                "overbought_threshold": overbought_threshold,
            },
        )
