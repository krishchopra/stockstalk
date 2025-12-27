"""Configuration management utilities."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from stockstalk.models import AppConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration."""

    DEFAULT_CONFIG_PATH = Path("config.json")

    def __init__(self, config_path: Path | None = None) -> None:
        """
        Initialize config manager.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH

    def load_config(self) -> AppConfig:
        """
        Load configuration from file.

        Returns:
            AppConfig object

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        if not self.config_path.exists():
            logger.warning(
                f"Config file {self.config_path} not found. Creating default config."
            )
            default_config = self._get_default_config()
            self.save_config(default_config)
            return default_config

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
            return AppConfig.model_validate(data)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    def save_config(self, config: AppConfig) -> None:
        """
        Save configuration to file.

        Args:
            config: AppConfig object to save
        """
        try:
            with open(self.config_path, "w") as f:
                json.dump(config.model_dump(), f, indent=2, default=str)
            logger.info(f"Config saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            raise

    def _get_default_config(self) -> AppConfig:
        """
        Get default configuration.

        Returns:
            Default AppConfig
        """
        from stockstalk.models import NotificationConfig, WatchlistItem

        # Load from environment variables if available
        beeper_webhook = os.getenv("BEEPER_WEBHOOK_URL")
        phone_numbers = os.getenv("PHONE_NUMBERS", "").split(",")
        phone_numbers = [p.strip() for p in phone_numbers if p.strip()]

        return AppConfig(
            watchlist=[
                WatchlistItem(
                    symbol="AAPL",
                    enabled_indicators=[
                        "RSI",
                        "MA_Crossover",
                        "Volume_Spike",
                        "Price_Change",
                        "MACD",
                    ],
                ),
                WatchlistItem(
                    symbol="MSFT",
                    enabled_indicators=["RSI", "MA_Crossover", "MACD"],
                ),
                WatchlistItem(
                    symbol="GOOGL",
                    enabled_indicators=["RSI", "Volume_Spike", "Price_Change"],
                ),
            ],
            notification_config=NotificationConfig(
                beeper_webhook_url=beeper_webhook,
                phone_numbers=phone_numbers,
            ),
            check_interval_minutes=15,
            data_lookback_days=30,
        )
