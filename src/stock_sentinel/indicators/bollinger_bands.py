"""Bollinger Bands indicator implementation."""

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
class BollingerBandsIndicator(Indicator):
    """
    Bollinger Bands indicator.

    Bollinger Bands consist of:
    - Middle Band: 20-period SMA
    - Upper Band: Middle Band + (2 * standard deviation)
    - Lower Band: Middle Band - (2 * standard deviation)

    Trading signals:
    - Price touching lower band: Potential buy (oversold)
    - Price touching upper band: Potential sell (overbought)
    - Squeeze (narrow bands): Volatility expansion coming
    - Breakout above/below bands: Strong momentum signal
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        period: int = 20,
        num_std: float = 2.0,
    ):
        """
        Initialize Bollinger Bands indicator.

        Args:
            config: Indicator configuration
            period: MA period for middle band (default 20)
            num_std: Number of standard deviations for bands (default 2.0)
        """
        super().__init__(config)
        self.period = period
        self.num_std = num_std

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "bollinger_bands"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"Bollinger Bands({self.period}, {self.num_std}) - Volatility and price extremes"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return self.period + 5

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data using Bollinger Bands."""
        closes = stock_data.closes

        if len(closes) < self.period:
            return None

        prices = np.array(closes[-self.period :])
        current_price = prices[-1]

        # Calculate bands
        middle_band = np.mean(prices)
        std_dev = np.std(prices)
        upper_band = middle_band + (self.num_std * std_dev)
        lower_band = middle_band - (self.num_std * std_dev)

        # Calculate %B (where price is relative to bands)
        band_width = upper_band - lower_band
        if band_width == 0:
            return None

        percent_b = (current_price - lower_band) / band_width

        # Calculate bandwidth (volatility indicator)
        bandwidth = (band_width / middle_band) * 100

        # Determine signal
        if current_price < lower_band:
            # Price below lower band - strong buy
            signal = SignalType.STRONG_BUY
            message = (
                f"Price BELOW lower Bollinger Band! "
                f"Oversold at ${current_price:.2f} (lower band: ${lower_band:.2f})"
            )
            should_alert = True
        elif current_price <= lower_band * 1.01:  # Within 1% of lower band
            signal = SignalType.BUY
            message = (
                f"Price touching lower Bollinger Band. " f"Potential bounce at ${current_price:.2f}"
            )
            should_alert = True
        elif current_price > upper_band:
            # Price above upper band - strong sell
            signal = SignalType.STRONG_SELL
            message = (
                f"Price ABOVE upper Bollinger Band! "
                f"Overbought at ${current_price:.2f} (upper band: ${upper_band:.2f})"
            )
            should_alert = True
        elif current_price >= upper_band * 0.99:  # Within 1% of upper band
            signal = SignalType.SELL
            message = (
                f"Price touching upper Bollinger Band. "
                f"Potential resistance at ${current_price:.2f}"
            )
            should_alert = True
        else:
            signal = SignalType.NEUTRAL
            message = f"Price within bands. %B: {percent_b:.2f}, Bandwidth: {bandwidth:.1f}%"
            should_alert = False

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=percent_b,
            message=message,
            should_alert=should_alert,
            upper_band=upper_band,
            middle_band=middle_band,
            lower_band=lower_band,
            percent_b=percent_b,
            bandwidth=bandwidth,
            current_price=current_price,
        )
