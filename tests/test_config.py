"""Tests for configuration management."""

import json
from pathlib import Path

import pytest

from stockstalk.models import AppConfig, WatchlistItem
from stockstalk.utils.config import ConfigManager


def test_config_manager_default_config(tmp_path: Path) -> None:
    """Test creating default configuration."""
    config_path = tmp_path / "config.json"
    manager = ConfigManager(config_path)

    config = manager.load_config()

    assert isinstance(config, AppConfig)
    assert config_path.exists()


def test_config_manager_save_and_load(tmp_path: Path) -> None:
    """Test saving and loading configuration."""
    config_path = tmp_path / "config.json"
    manager = ConfigManager(config_path)

    # Create config
    config = AppConfig(
        watchlist=[
            WatchlistItem(symbol="AAPL", enabled_indicators=["RSI"]),
        ],
        check_interval_minutes=20,
    )

    # Save
    manager.save_config(config)

    # Load
    loaded_config = manager.load_config()

    assert len(loaded_config.watchlist) == 1
    assert loaded_config.watchlist[0].symbol == "AAPL"
    assert loaded_config.check_interval_minutes == 20


def test_config_manager_validation(tmp_path: Path) -> None:
    """Test that invalid config raises validation error."""
    config_path = tmp_path / "config.json"

    # Write invalid config
    with open(config_path, "w") as f:
        json.dump({"check_interval_minutes": -5}, f)  # Invalid negative

    manager = ConfigManager(config_path)

    with pytest.raises(Exception):  # Pydantic ValidationError
        manager.load_config()
