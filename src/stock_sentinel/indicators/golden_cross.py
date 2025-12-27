"""Golden Cross / Death Cross indicator implementation."""

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
class GoldenCrossIndicator(Indicator):
    """
    Golden Cross / Death Cross indicator.

    A Golden Cross occurs when a short-term moving average crosses above
    a long-term moving average - traditionally the 50-day SMA crossing
    above the 200-day SMA. This is considered a bullish signal.

    A Death Cross is the opposite - short-term MA crossing below long-term MA,
    which is considered bearish.

    For shorter-term trading, we use 10-day and 50-day MAs by default.
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        short_period: int = 10,
        long_period: int = 50,
    ):
        """
        Initialize Golden Cross indicator.

        Args:
            config: Indicator configuration
            short_period: Short-term MA period (default 10)
            long_period: Long-term MA period (default 50)
        """
        super().__init__(config)
        self.short_period = short_period
        self.long_period = long_period

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "golden_cross"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"Golden/Death Cross({self.short_period}/{self.long_period}) - MA crossover signals"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return self.long_period + 5

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data for golden/death cross signals."""
        closes = stock_data.closes

        if len(closes) < self.long_period + 2:
            return None

        prices = np.array(closes)

        # Calculate moving averages for last 2 days
        short_ma_today = np.mean(prices[-self.short_period :])
        short_ma_yesterday = np.mean(prices[-self.short_period - 1 : -1])

        long_ma_today = np.mean(prices[-self.long_period :])
        long_ma_yesterday = np.mean(prices[-self.long_period - 1 : -1])

        # Check for crossovers
        golden_cross = short_ma_yesterday < long_ma_yesterday and short_ma_today > long_ma_today
        death_cross = short_ma_yesterday > long_ma_yesterday and short_ma_today < long_ma_today

        # Calculate the difference between MAs as a percentage
        ma_diff_pct = ((short_ma_today - long_ma_today) / long_ma_today) * 100

        if golden_cross:
            signal = SignalType.STRONG_BUY
            message = (
                f"🌟 GOLDEN CROSS! {self.short_period}-day MA crossed above "
                f"{self.long_period}-day MA - Major bullish signal!"
            )
            should_alert = True
        elif death_cross:
            signal = SignalType.STRONG_SELL
            message = (
                f"💀 DEATH CROSS! {self.short_period}-day MA crossed below "
                f"{self.long_period}-day MA - Major bearish signal!"
            )
            should_alert = True
        elif short_ma_today > long_ma_today:
            # Short MA above long MA = bullish trend
            signal = SignalType.BUY
            message = (
                f"Bullish trend: {self.short_period}-day MA {ma_diff_pct:.1f}% above "
                f"{self.long_period}-day MA"
            )
            should_alert = False
        else:
            # Short MA below long MA = bearish trend
            signal = SignalType.SELL
            message = (
                f"Bearish trend: {self.short_period}-day MA {abs(ma_diff_pct):.1f}% below "
                f"{self.long_period}-day MA"
            )
            should_alert = False

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=ma_diff_pct,
            message=message,
            should_alert=should_alert,
            short_ma=short_ma_today,
            long_ma=long_ma_today,
            golden_cross=golden_cross,
            death_cross=death_cross,
            ma_diff_pct=ma_diff_pct,
        )
