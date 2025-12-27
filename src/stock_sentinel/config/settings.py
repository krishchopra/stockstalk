"""Application settings and configuration management."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STOCK_SENTINEL_",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = "Stock Sentinel"
    debug: bool = False
    log_level: str = "INFO"

    # Database settings
    database_url: str = Field(
        default="sqlite+aiosqlite:///./stock_sentinel.db",
        description="Database connection URL",
    )

    # Beeper API settings for SMS notifications
    beeper_api_url: str = Field(
        default="https://api.beeper.com/v1",
        description="Beeper API base URL",
    )
    beeper_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Beeper API key for authentication",
    )
    beeper_sender_id: str = Field(
        default="",
        description="Beeper sender ID or phone number",
    )

    # Webhook server settings
    webhook_host: str = Field(default="0.0.0.0", description="Webhook server host")
    webhook_port: int = Field(default=8080, description="Webhook server port")
    webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Secret for webhook verification",
    )

    # Stock monitoring settings
    watchlist: Annotated[list[str], Field(default_factory=list)] = Field(
        default_factory=lambda: ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
        description="Default stock symbols to monitor",
    )
    check_interval_minutes: int = Field(
        default=15,
        description="Interval between stock checks in minutes",
    )
    market_hours_only: bool = Field(
        default=True,
        description="Only check during market hours (9:30 AM - 4:00 PM ET)",
    )

    # Alert settings
    cooldown_minutes: int = Field(
        default=60,
        description="Minimum time between alerts for the same stock/indicator",
    )
    max_alerts_per_hour: int = Field(
        default=10,
        description="Maximum number of alerts per hour",
    )

    # Indicator thresholds (defaults, can be overridden per-indicator)
    rsi_oversold: float = Field(default=30.0, description="RSI oversold threshold")
    rsi_overbought: float = Field(default=70.0, description="RSI overbought threshold")
    volume_spike_multiplier: float = Field(
        default=2.0,
        description="Volume spike threshold multiplier vs average",
    )
    price_change_threshold: float = Field(
        default=5.0,
        description="Price change percentage to trigger alert",
    )

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        path = Path("./data")
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
