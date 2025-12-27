"""Extensible indicator system for stock analysis."""

# Import all built-in indicators to register them
from stock_sentinel.indicators import (
    bollinger_bands,
    golden_cross,
    macd,
    price_change,
    rsi,
    volume_spike,
)
from stock_sentinel.indicators.base import Indicator, IndicatorResult, SignalType
from stock_sentinel.indicators.registry import IndicatorRegistry, indicator_registry

__all__ = [
    "Indicator",
    "IndicatorResult",
    "SignalType",
    "IndicatorRegistry",
    "indicator_registry",
    # Built-in indicators
    "rsi",
    "macd",
    "volume_spike",
    "golden_cross",
    "bollinger_bands",
    "price_change",
]
