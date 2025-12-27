"""MACD (Moving Average Convergence Divergence) indicator implementation."""

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
class MACDIndicator(Indicator):
    """
    MACD (Moving Average Convergence Divergence) indicator.

    MACD shows the relationship between two EMAs of a security's price.
    It consists of:
    - MACD Line: 12-period EMA - 26-period EMA
    - Signal Line: 9-period EMA of MACD Line
    - Histogram: MACD Line - Signal Line

    Buy signals occur when MACD crosses above the signal line.
    Sell signals occur when MACD crosses below the signal line.
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ):
        """
        Initialize MACD indicator.

        Args:
            config: Indicator configuration
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line EMA period (default 9)
        """
        super().__init__(config)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "macd"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"MACD({self.fast_period},{self.slow_period},{self.signal_period}) - Trend following momentum"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return self.slow_period + self.signal_period + 5

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data using MACD."""
        closes = stock_data.closes

        if len(closes) < self.required_history_days:
            return None

        macd_line, signal_line, histogram = self._calculate_macd(closes)

        if macd_line is None or len(histogram) < 2:
            return None

        current_hist = histogram[-1]
        prev_hist = histogram[-2]

        # Detect crossovers
        bullish_crossover = prev_hist < 0 and current_hist > 0
        bearish_crossover = prev_hist > 0 and current_hist < 0

        # Also check for strong momentum
        strong_bullish = current_hist > 0 and current_hist > prev_hist * 1.5
        strong_bearish = current_hist < 0 and current_hist < prev_hist * 1.5

        if bullish_crossover:
            signal = SignalType.BUY
            message = f"MACD bullish crossover! Histogram: {current_hist:.4f}"
            should_alert = True
        elif bearish_crossover:
            signal = SignalType.SELL
            message = f"MACD bearish crossover! Histogram: {current_hist:.4f}"
            should_alert = True
        elif strong_bullish:
            signal = SignalType.BUY
            message = f"MACD showing strong bullish momentum. Histogram: {current_hist:.4f}"
            should_alert = False
        elif strong_bearish:
            signal = SignalType.SELL
            message = f"MACD showing strong bearish momentum. Histogram: {current_hist:.4f}"
            should_alert = False
        else:
            signal = SignalType.NEUTRAL
            message = f"MACD neutral. Histogram: {current_hist:.4f}"
            should_alert = False

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=current_hist,
            message=message,
            should_alert=should_alert,
            macd_line=macd_line[-1],
            signal_line=signal_line[-1],
            histogram=current_hist,
            bullish_crossover=bullish_crossover,
            bearish_crossover=bearish_crossover,
        )

    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        return ema

    def _calculate_macd(
        self, closes: list[float]
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
        """
        Calculate MACD, Signal line, and Histogram.

        Returns:
            Tuple of (macd_line, signal_line, histogram) or (None, None, None)
        """
        prices = np.array(closes)

        if len(prices) < self.slow_period:
            return None, None, None

        fast_ema = self._calculate_ema(prices, self.fast_period)
        slow_ema = self._calculate_ema(prices, self.slow_period)

        macd_line = fast_ema - slow_ema

        if len(macd_line) < self.signal_period:
            return None, None, None

        signal_line = self._calculate_ema(macd_line, self.signal_period)
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram
