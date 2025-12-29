"""Configuration management utilities."""

import json
import logging
import os
from pathlib import Path

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
            logger.warning(f"Config file {self.config_path} not found. Creating default config.")
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
        Get default configuration with VTI top 1000 holdings.

        Returns:
            Default AppConfig with VTI watchlist
        """
        from stockstalk.models import NotificationConfig, WatchlistItem
        from stockstalk.services.etf_holdings import (
            DEFAULT_VTI_INDICATORS,
            ETFHoldingsFetcher,
        )

        # Load phone numbers from environment if available
        phone_numbers = os.getenv("PHONE_NUMBERS", "").split(",")
        phone_numbers = [p.strip() for p in phone_numbers if p.strip()]

        # Get default number of stocks from env, default to 500
        default_top_n = int(os.getenv("VTI_TOP_N", "500"))

        # Generate watchlist from VTI top holdings (uses curated list)
        logger.info(f"Generating default watchlist from VTI top {default_top_n} holdings...")
        fetcher = ETFHoldingsFetcher("VTI")
        holdings = fetcher._get_curated_vti_holdings()[:default_top_n]

        # Remove duplicates
        seen = set()
        watchlist = []
        for holding in holdings:
            symbol = holding["symbol"]
            if symbol in seen or not symbol or len(symbol) > 10:
                continue
            seen.add(symbol)

            watchlist.append(
                WatchlistItem(
                    symbol=symbol,
                    enabled_indicators=list(set(DEFAULT_VTI_INDICATORS)),
                    custom_params={},
                )
            )

        logger.info(f"Default watchlist: {len(watchlist)} stocks with all indicators enabled")

        return AppConfig(
            watchlist=watchlist,
            notification_config=NotificationConfig(
                phone_numbers=phone_numbers,
                cooldown_minutes=60,
                max_alerts_per_hour=10,  # Higher limit for more stocks
            ),
            check_interval_minutes=60,  # Hourly for large watchlist
            data_lookback_days=30,
        )
