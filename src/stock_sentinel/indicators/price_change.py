"""Price Change indicator implementation."""

from stock_sentinel.data.models import StockData
from stock_sentinel.indicators.base import (
    Indicator,
    IndicatorConfig,
    IndicatorResult,
    SignalType,
)
from stock_sentinel.indicators.registry import indicator_registry


@indicator_registry.register
class PriceChangeIndicator(Indicator):
    """
    Price Change indicator.

    Monitors significant price movements and generates alerts when
    price changes exceed specified thresholds. This is useful for
    catching sudden moves that might indicate news or momentum.
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        threshold_pct: float = 5.0,
        extreme_threshold_pct: float = 10.0,
    ):
        """
        Initialize Price Change indicator.

        Args:
            config: Indicator configuration
            threshold_pct: Price change percentage to trigger alert (default 5%)
            extreme_threshold_pct: Extreme price change threshold (default 10%)
        """
        super().__init__(config)
        self.threshold_pct = threshold_pct
        self.extreme_threshold_pct = extreme_threshold_pct

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "price_change"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"Price Change({self.threshold_pct}%) - Monitors significant price movements"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return 2

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data for significant price changes."""
        quote = stock_data.quote
        change_pct = quote.change_percent

        abs_change = abs(change_pct)
        is_significant = abs_change >= self.threshold_pct
        is_extreme = abs_change >= self.extreme_threshold_pct

        if change_pct >= self.extreme_threshold_pct:
            signal = SignalType.STRONG_BUY
            message = (
                f"🔥 EXTREME price surge! +{change_pct:.1f}% "
                f"(${quote.price:.2f}) - Major momentum!"
            )
            should_alert = True
        elif change_pct >= self.threshold_pct:
            signal = SignalType.BUY
            message = (
                f"Significant price gain: +{change_pct:.1f}% "
                f"(${quote.price:.2f}) - Bullish momentum"
            )
            should_alert = True
        elif change_pct <= -self.extreme_threshold_pct:
            signal = SignalType.STRONG_SELL
            message = (
                f"⚠️ EXTREME price drop! {change_pct:.1f}% " f"(${quote.price:.2f}) - Major selloff!"
            )
            should_alert = True
        elif change_pct <= -self.threshold_pct:
            signal = SignalType.SELL
            message = (
                f"Significant price drop: {change_pct:.1f}% "
                f"(${quote.price:.2f}) - Bearish pressure"
            )
            should_alert = True
        else:
            signal = SignalType.NEUTRAL
            message = f"Normal trading: {change_pct:+.1f}% (${quote.price:.2f})"
            should_alert = False

        # Add 52-week context if available
        extra_context = ""
        if quote.is_at_52_week_high:
            extra_context = " 📊 At 52-week HIGH!"
            if signal == SignalType.BUY:
                signal = SignalType.STRONG_BUY
            should_alert = True
        elif quote.is_at_52_week_low:
            extra_context = " 📊 At 52-week LOW!"
            should_alert = True

        if extra_context:
            message += extra_context

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=change_pct,
            message=message,
            should_alert=should_alert,
            price=quote.price,
            change=quote.change,
            change_pct=change_pct,
            is_significant=is_significant,
            is_extreme=is_extreme,
            at_52_week_high=quote.is_at_52_week_high,
            at_52_week_low=quote.is_at_52_week_low,
        )
