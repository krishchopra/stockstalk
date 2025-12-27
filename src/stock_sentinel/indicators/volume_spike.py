"""Volume Spike indicator implementation."""

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
class VolumeSpikeIndicator(Indicator):
    """
    Volume Spike indicator.

    Detects unusual trading volume which often precedes significant price moves.
    High volume on up days is bullish; high volume on down days is bearish.

    A volume spike is identified when current volume exceeds the average
    volume by a specified multiplier (default 2x).
    """

    def __init__(
        self,
        config: IndicatorConfig | None = None,
        lookback_period: int = 20,
        spike_multiplier: float = 2.0,
        extreme_multiplier: float = 3.0,
    ):
        """
        Initialize Volume Spike indicator.

        Args:
            config: Indicator configuration
            lookback_period: Period for calculating average volume (default 20)
            spike_multiplier: Multiplier for volume spike detection (default 2.0)
            extreme_multiplier: Multiplier for extreme volume detection (default 3.0)
        """
        super().__init__(config)
        self.lookback_period = lookback_period
        self.spike_multiplier = spike_multiplier
        self.extreme_multiplier = extreme_multiplier

    @property
    def name(self) -> str:
        """Get indicator name."""
        return "volume_spike"

    @property
    def description(self) -> str:
        """Get indicator description."""
        return f"Volume Spike({self.lookback_period}) - Detects unusual trading activity"

    @property
    def required_history_days(self) -> int:
        """Minimum history required."""
        return self.lookback_period + 1

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        """Analyze stock data for volume spikes."""
        history = stock_data.history

        if len(history) < self.lookback_period + 1:
            return None

        # Get recent volume data
        volumes = np.array([h.volume for h in history])
        closes = np.array([h.close for h in history])

        # Calculate average volume (excluding current day)
        avg_volume = np.mean(volumes[-self.lookback_period - 1 : -1])

        current_volume = volumes[-1]
        current_close = closes[-1]
        prev_close = closes[-2]

        if avg_volume == 0:
            return None

        volume_ratio = current_volume / avg_volume
        price_change_pct = ((current_close - prev_close) / prev_close) * 100

        # Determine if this is a spike
        is_spike = volume_ratio >= self.spike_multiplier
        is_extreme = volume_ratio >= self.extreme_multiplier

        if not is_spike:
            return self._create_result(
                symbol=stock_data.symbol,
                signal=SignalType.NEUTRAL,
                value=volume_ratio,
                message=f"Normal volume ({volume_ratio:.1f}x average)",
                should_alert=False,
                volume_ratio=volume_ratio,
                avg_volume=avg_volume,
                current_volume=current_volume,
            )

        # Determine signal direction based on price movement
        if price_change_pct > 0:
            # High volume on up day = bullish
            if is_extreme:
                signal = SignalType.STRONG_BUY
                message = (
                    f"EXTREME volume spike! {volume_ratio:.1f}x average "
                    f"with +{price_change_pct:.1f}% price gain - Strong accumulation!"
                )
            else:
                signal = SignalType.BUY
                message = (
                    f"Volume spike {volume_ratio:.1f}x average "
                    f"with +{price_change_pct:.1f}% price gain - Bullish accumulation"
                )
        else:
            # High volume on down day = bearish
            if is_extreme:
                signal = SignalType.STRONG_SELL
                message = (
                    f"EXTREME volume spike! {volume_ratio:.1f}x average "
                    f"with {price_change_pct:.1f}% price drop - Heavy distribution!"
                )
            else:
                signal = SignalType.SELL
                message = (
                    f"Volume spike {volume_ratio:.1f}x average "
                    f"with {price_change_pct:.1f}% price drop - Distribution"
                )

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=volume_ratio,
            message=message,
            should_alert=True,
            volume_ratio=volume_ratio,
            avg_volume=avg_volume,
            current_volume=current_volume,
            price_change_pct=price_change_pct,
            is_extreme=is_extreme,
        )
