"""Tests for settings module."""

import os
from unittest import mock


def test_settings_defaults() -> None:
    """Test that settings have sensible defaults."""
    # Import fresh settings
    from stockstalk.settings import Settings

    settings = Settings()

    assert settings.COOLDOWN_MINUTES == 60
    assert settings.MAX_ALERTS_PER_HOUR == 10
    assert settings.CHECK_INTERVAL_MINUTES == 60
    assert settings.DATA_LOOKBACK_DAYS == 30
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8000


def test_settings_from_environment() -> None:
    """Test that settings are read from environment variables."""
    env_vars = {
        "COOLDOWN_MINUTES": "30",
        "MAX_ALERTS_PER_HOUR": "5",
        "CHECK_INTERVAL_MINUTES": "15",
        "DATA_LOOKBACK_DAYS": "60",
        "MIN_PRIORITY": "high",
        "HOST": "127.0.0.1",
        "PORT": "9000",
    }

    with mock.patch.dict(os.environ, env_vars, clear=False):
        # Need to reimport to pick up new env vars
        from stockstalk.settings import AlertPriority, Settings

        settings = Settings()

        assert settings.COOLDOWN_MINUTES == 30
        assert settings.MAX_ALERTS_PER_HOUR == 5
        assert settings.CHECK_INTERVAL_MINUTES == 15
        assert settings.DATA_LOOKBACK_DAYS == 60
        assert settings.MIN_PRIORITY == AlertPriority.HIGH
        assert settings.HOST == "127.0.0.1"
        assert settings.PORT == 9000


def test_twilio_configured_check() -> None:
    """Test Twilio configuration check."""
    from stockstalk.settings import Settings

    # Without credentials
    settings = Settings()
    settings.TWILIO_ACCOUNT_SID = ""
    settings.TWILIO_AUTH_TOKEN = ""
    settings.TWILIO_PHONE_NUMBER = ""
    assert not settings.is_twilio_configured()

    # With credentials
    settings.TWILIO_ACCOUNT_SID = "test_sid"
    settings.TWILIO_AUTH_TOKEN = "test_token"
    settings.TWILIO_PHONE_NUMBER = "+1234567890"
    assert settings.is_twilio_configured()


def test_default_indicators() -> None:
    """Test default indicators list."""
    from stockstalk.settings import Settings

    settings = Settings()

    assert "RSI" in settings.DEFAULT_INDICATORS
    assert "MACD" in settings.DEFAULT_INDICATORS
    assert len(settings.DEFAULT_INDICATORS) >= 3
