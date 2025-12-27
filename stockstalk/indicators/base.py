"""Base indicator interface for stock analysis."""

from abc import ABC, abstractmethod
from typing import Any

from stockstalk.models import HistoricalData, IndicatorResult, StockData


class BaseIndicator(ABC):
    """Abstract base class for stock indicators."""

    def __init__(self, **params: Any) -> None:
        """Initialize indicator with custom parameters."""
        self.params = params

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the indicator."""
        pass

    @abstractmethod
    def analyze(
        self, current_data: StockData, historical_data: HistoricalData
    ) -> IndicatorResult:
        """
        Analyze stock data and return indicator result.

        Args:
            current_data: Current stock data
            historical_data: Historical stock data for analysis

        Returns:
            IndicatorResult with analysis results
        """
        pass

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter value with optional default."""
        return self.params.get(key, default)
