"""Core data models for the stockstalk application."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlertPriority(str, Enum):
    """Priority levels for stock alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StockData(BaseModel):
    """Stock price and volume data."""

    symbol: str = Field(..., description="Stock ticker symbol")
    timestamp: datetime = Field(default_factory=datetime.now)
    current_price: float = Field(..., gt=0, description="Current stock price")
    open_price: float = Field(..., gt=0, description="Opening price")
    high_price: float = Field(..., gt=0, description="Highest price of the day")
    low_price: float = Field(..., gt=0, description="Lowest price of the day")
    volume: int = Field(..., ge=0, description="Trading volume")
    previous_close: float = Field(..., gt=0, description="Previous closing price")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate and normalize stock symbol."""
        return v.upper().strip()


class IndicatorResult(BaseModel):
    """Result from a stock indicator analysis."""

    indicator_name: str = Field(..., description="Name of the indicator")
    symbol: str = Field(..., description="Stock ticker symbol")
    timestamp: datetime = Field(default_factory=datetime.now)
    is_triggered: bool = Field(..., description="Whether the indicator triggered")
    priority: AlertPriority = Field(
        default=AlertPriority.MEDIUM, description="Alert priority"
    )
    signal_strength: float = Field(
        ..., ge=0, le=1, description="Signal strength (0-1)"
    )
    message: str = Field(..., description="Human-readable message")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional indicator-specific data"
    )


class NotificationConfig(BaseModel):
    """Configuration for notifications."""

    phone_numbers: list[str] = Field(
        default_factory=list, description="Phone numbers to notify"
    )
    beeper_webhook_url: str | None = Field(
        None, description="Beeper webhook URL"
    )
    min_priority: AlertPriority = Field(
        default=AlertPriority.MEDIUM,
        description="Minimum priority to trigger notification",
    )


class WatchlistItem(BaseModel):
    """A stock to watch with specific indicators."""

    symbol: str = Field(..., description="Stock ticker symbol")
    enabled_indicators: list[str] = Field(
        default_factory=list, description="List of indicator names to use"
    )
    custom_params: dict[str, Any] = Field(
        default_factory=dict, description="Custom parameters for indicators"
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate and normalize stock symbol."""
        return v.upper().strip()


class AppConfig(BaseModel):
    """Application configuration."""

    watchlist: list[WatchlistItem] = Field(
        default_factory=list, description="Stocks to monitor"
    )
    notification_config: NotificationConfig = Field(
        default_factory=NotificationConfig
    )
    check_interval_minutes: int = Field(
        default=15, ge=1, description="How often to check stocks (minutes)"
    )
    data_lookback_days: int = Field(
        default=30, ge=1, description="Days of historical data to analyze"
    )


@dataclass
class HistoricalData:
    """Historical stock data for analysis."""

    symbol: str
    dates: list[datetime]
    open_prices: list[float]
    high_prices: list[float]
    low_prices: list[float]
    close_prices: list[float]
    volumes: list[int]
