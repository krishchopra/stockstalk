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

    def __init__(self) -> None:
        """Initialize settings from environment variables."""
        # Twilio settings (required for SMS)
        self.TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

        # OpenAI settings (for AI-powered assistant)
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-nano")

        # Notification settings
        self.MIN_PRIORITY: AlertPriority = AlertPriority(
            os.getenv("MIN_PRIORITY", "medium").lower()
        )
        self.COOLDOWN_MINUTES: int = int(os.getenv("COOLDOWN_MINUTES", "60"))
        self.MAX_ALERTS_PER_HOUR: int = int(os.getenv("MAX_ALERTS_PER_HOUR", "10"))

        # Scheduler settings
        self.CHECK_INTERVAL_MINUTES: int = int(
            os.getenv("CHECK_INTERVAL_MINUTES", "60")
        )

        # Daily digest settings
        self.DAILY_DIGEST_ENABLED: bool = (
            os.getenv("DAILY_DIGEST_ENABLED", "true").lower() == "true"
        )
        self.DAILY_DIGEST_HOUR: int = int(os.getenv("DAILY_DIGEST_HOUR", "8"))  # 8 AM
        self.DAILY_DIGEST_MINUTE: int = int(os.getenv("DAILY_DIGEST_MINUTE", "0"))
        self.DAILY_DIGEST_TIMEZONE: str = os.getenv(
            "DAILY_DIGEST_TIMEZONE", "America/New_York"
        )

        # Data settings
        self.DATA_LOOKBACK_DAYS: int = int(os.getenv("DATA_LOOKBACK_DAYS", "30"))

        # Database
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./stockstalk.db"
        )

        # Server settings
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("PORT", "8000"))

        # Default indicators for new watchlist items
        self.DEFAULT_INDICATORS: list[str] = [
            "RSI",
            "MACD",
            "Fundamental_Score",
            "Volume_Spike",
        ]

    def is_twilio_configured(self) -> bool:
        """Check if Twilio credentials are configured."""
        return all(
            [self.TWILIO_ACCOUNT_SID, self.TWILIO_AUTH_TOKEN, self.TWILIO_PHONE_NUMBER]
        )

    def is_openai_configured(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.OPENAI_API_KEY)


# Singleton instance
settings = Settings()
