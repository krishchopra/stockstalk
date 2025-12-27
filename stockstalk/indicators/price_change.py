"""Price Change Percentage indicator implementation."""

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData


class PriceChangeIndicator(BaseIndicator):
    """
    Price Change Percentage indicator.

    Detects significant price movements that could indicate buying opportunities.
    """

    @property
    def name(self) -> str:
        """Return the name of the indicator."""
        return "Price_Change"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        """Calculate price change and check for significant movements."""
        significant_drop_pct = self.get_param("significant_drop_pct", -5.0)
        significant_gain_pct = self.get_param("significant_gain_pct", 5.0)

        # Calculate percentage change from previous close
        price_change_pct = (
            (current_data.current_price - current_data.previous_close)
            / current_data.previous_close
            * 100
        )

        # Calculate intraday change
        intraday_change_pct = (
            (current_data.current_price - current_data.open_price) / current_data.open_price * 100
        )

        # Determine if triggered
        significant_drop = price_change_pct <= significant_drop_pct
        significant_gain = price_change_pct >= significant_gain_pct
        is_triggered = significant_drop or significant_gain

        # Calculate signal strength
        if significant_drop:
            signal_strength = min(abs(price_change_pct) / abs(significant_drop_pct), 1.0)
        elif significant_gain:
            signal_strength = min(price_change_pct / significant_gain_pct, 1.0)
        else:
            signal_strength = 0.0

        # Generate message
        if significant_drop:
            message = (
                f"{current_data.symbol} SIGNIFICANT DROP! "
                f"Down {abs(price_change_pct):.2f}% to ${current_data.current_price:.2f}. "
                f"Potential BUY opportunity on dip!"
            )
            priority = AlertPriority.HIGH if price_change_pct <= -8 else AlertPriority.MEDIUM
        elif significant_gain:
            message = (
                f"{current_data.symbol} SIGNIFICANT GAIN! "
                f"Up {price_change_pct:.2f}% to ${current_data.current_price:.2f}. "
                f"Momentum building!"
            )
            priority = AlertPriority.MEDIUM
        else:
            message = (
                f"{current_data.symbol} price change: {price_change_pct:+.2f}% "
                f"to ${current_data.current_price:.2f}"
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
                "price_change_pct": float(price_change_pct),
                "intraday_change_pct": float(intraday_change_pct),
                "previous_close": current_data.previous_close,
                "current_price": current_data.current_price,
            },
        )
