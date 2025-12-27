"""RSI (Relative Strength Index) indicator implementation."""

import numpy as np

from stock_sentinel.data.models import StockData
from stock_sentinel.indicators.base import (
    Indicator,
    IndicatorConfig,
    IndicatorResult,
    SignalType,
)
from stock_sentinel.indicators.registry import indicator_registry


@indicator_registry.register
class RSIIndicator(Indicator):
    """
    Relative Strength Index (RSI) indicator.

    RSI measures the speed and magnitude of recent price changes to evaluate
    overbought or oversold conditions. Traditional interpretation:
    - RSI < 30: Oversold (potential buy signal)
    - RSI > 70: Overbought (potential sell signal)

    This indicator generates STRONG_BUY when RSI is very oversold (< 25)
    and BUY when oversold (< 30).
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ):
        """
        Initialize RSI indicator.

        Args:
            config: Indicator configuration
            period: RSI calculation period (default 14)
            oversold: Oversold threshold (default 30)
            overbought: Overbought threshold (default 70)
        """
        super().__init__(config)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "rsi"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"RSI({self.period}) - Identifies overbought/oversold conditions"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return self.period + 5  # Need extra days for calculation

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data using RSI."""
        closes = stock_data.closes

        if len(closes) < self.period + 1:
            return None

        rsi_value = self._calculate_rsi(closes)

        if rsi_value is None:
            return None

        # Determine signal
        if rsi_value < 25:
            signal = SignalType.STRONG_BUY
            message = f"RSI at {rsi_value:.1f} - Extremely oversold! Strong buying opportunity"
            should_alert = True
        elif rsi_value < self.oversold:
            signal = SignalType.BUY
            message = f"RSI at {rsi_value:.1f} - Oversold, potential buy signal"
            should_alert = True
        elif rsi_value > 80:
            signal = SignalType.STRONG_SELL
            message = f"RSI at {rsi_value:.1f} - Extremely overbought! Consider selling"
            should_alert = True
        elif rsi_value > self.overbought:
            signal = SignalType.SELL
            message = f"RSI at {rsi_value:.1f} - Overbought, potential sell signal"
            should_alert = True
        else:
            signal = SignalType.NEUTRAL
            message = f"RSI at {rsi_value:.1f} - Neutral zone"
            should_alert = False

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=rsi_value,
            message=message,
            should_alert=should_alert,
            period=self.period,
            oversold_threshold=self.oversold,
            overbought_threshold=self.overbought,
        )

    def _calculate_rsi(self, closes: list[float]) -> float | None:
        """
        Calculate RSI using exponential moving average method.

        Args:
            closes: List of closing prices

        Returns:
            RSI value between 0 and 100, or None if insufficient data
        """
        if len(closes) < self.period + 1:
            return None

        # Calculate price changes
        prices = np.array(closes)
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gains and losses using EMA
        alpha = 1 / self.period

        avg_gain = np.mean(gains[: self.period])
        avg_loss = np.mean(losses[: self.period])

        for i in range(self.period, len(gains)):
            avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
            avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)
