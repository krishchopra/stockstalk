"""Environment-based configuration settings.

All configuration is done via environment variables with sensible defaults.
No config.json needed!
"""

import os
from enum import Enum


class AlertPriority(str, Enum):
    """Priority levels for stock alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Settings:
    """Application settings from environment variables."""

    # Twilio settings (required for SMS)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

    # Notification settings
    MIN_PRIORITY: AlertPriority = AlertPriority(
        os.getenv("MIN_PRIORITY", "medium").lower()
    )
    COOLDOWN_MINUTES: int = int(os.getenv("COOLDOWN_MINUTES", "60"))
    MAX_ALERTS_PER_HOUR: int = int(os.getenv("MAX_ALERTS_PER_HOUR", "10"))

    # Scheduler settings
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

    # Data settings
    DATA_LOOKBACK_DAYS: int = int(os.getenv("DATA_LOOKBACK_DAYS", "30"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./stockstalk.db")

    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Default indicators for new watchlist items
    DEFAULT_INDICATORS: list[str] = [
        "RSI",
        "MACD",
        "Fundamental_Score",
        "Volume_Spike",
    ]

    @classmethod
    def is_twilio_configured(cls) -> bool:
        """Check if Twilio credentials are configured."""
        return all([cls.TWILIO_ACCOUNT_SID, cls.TWILIO_AUTH_TOKEN, cls.TWILIO_PHONE_NUMBER])


# Singleton instance
settings = Settings()

