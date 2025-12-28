"""Stock indicators package."""

from stockstalk.indicators.base import BaseIndicator
from stockstalk.indicators.macd import MACDIndicator
from stockstalk.indicators.moving_average import MovingAverageCrossoverIndicator
from stockstalk.indicators.price_change import PriceChangeIndicator
from stockstalk.indicators.rsi import RSIIndicator
from stockstalk.indicators.volume_spike import VolumeSpikeIndicator

# Fundamental indicators
from stockstalk.indicators.fundamentals import (
    DebtToEquityIndicator,
    EarningsGrowthIndicator,
    FreeCashFlowIndicator,
    FundamentalScoreIndicator,
    OperatingMarginsIndicator,
    PEGRatioIndicator,
    RevenueGrowthIndicator,
    ROICIndicator,
)

__all__ = [
    "BaseIndicator",
    # Technical indicators
    "RSIIndicator",
    "MovingAverageCrossoverIndicator",
    "VolumeSpikeIndicator",
    "PriceChangeIndicator",
    "MACDIndicator",
    # Fundamental indicators
    "PEGRatioIndicator",
    "DebtToEquityIndicator",
    "OperatingMarginsIndicator",
    "ROICIndicator",
    "FreeCashFlowIndicator",
    "RevenueGrowthIndicator",
    "EarningsGrowthIndicator",
    "FundamentalScoreIndicator",
]
