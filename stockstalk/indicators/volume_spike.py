"""Volume Spike indicator implementation."""

import numpy as np

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData


class VolumeSpikeIndicator(BaseIndicator):
    """
    Volume Spike indicator.

    Detects unusual trading volume that could indicate significant market interest.
    High volume with price increase suggests strong buying pressure.
    """

    @property
    def name(self) -> str:
        """Return the name of the indicator."""
        return "Volume_Spike"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        """Detect volume spikes and assess their significance."""
        lookback_period = self.get_param("lookback_period", 20)
        spike_threshold = self.get_param("spike_threshold", 2.0)  # 2x average

        if len(historical_data.volumes) < lookback_period:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"Insufficient data for volume analysis (need {lookback_period} days)",
                metadata={"volume_ratio": None},
            )

        volumes = np.array(historical_data.volumes)
        avg_volume = np.mean(volumes[-lookback_period:])

        if avg_volume == 0:
            volume_ratio = 0.0
        else:
            volume_ratio = current_data.volume / avg_volume

        is_spike = volume_ratio >= spike_threshold

        # Check if price is also increasing
        price_change_pct = (
            (current_data.current_price - current_data.previous_close)
            / current_data.previous_close
            * 100
        )

        # Calculate signal strength based on volume ratio
        signal_strength = min((volume_ratio - 1) / spike_threshold, 1.0)

        # Generate message
        if is_spike:
            if price_change_pct > 2:
                message = (
                    f"{current_data.symbol} VOLUME SPIKE with PRICE SURGE! "
                    f"Volume is {volume_ratio:.1f}x average ({current_data.volume:,} vs {int(avg_volume):,}). "
                    f"Price up {price_change_pct:.2f}% to ${current_data.current_price:.2f}. "
                    f"Strong BUY signal!"
                )
                priority = AlertPriority.HIGH
            elif price_change_pct > 0:
                message = (
                    f"{current_data.symbol} VOLUME SPIKE detected! "
                    f"Volume is {volume_ratio:.1f}x average ({current_data.volume:,} vs {int(avg_volume):,}). "
                    f"Price up {price_change_pct:.2f}% to ${current_data.current_price:.2f}. "
                    f"Potential BUY opportunity."
                )
                priority = AlertPriority.MEDIUM
            else:
                message = (
                    f"{current_data.symbol} VOLUME SPIKE with price decline. "
                    f"Volume is {volume_ratio:.1f}x average. "
                    f"Price down {abs(price_change_pct):.2f}% to ${current_data.current_price:.2f}. "
                    f"Caution advised."
                )
                priority = AlertPriority.MEDIUM
        else:
            message = f"{current_data.symbol} volume is normal at {volume_ratio:.1f}x average"
            priority = AlertPriority.LOW

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_spike,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={
                "volume_ratio": float(volume_ratio),
                "avg_volume": int(avg_volume),
                "current_volume": current_data.volume,
                "price_change_pct": float(price_change_pct),
            },
        )
