"""Terminal UI for configuration management."""

import logging
import sys
from typing import Any

from stockstalk.models import AlertPriority, WatchlistItem
from stockstalk.services.analyzer import IndicatorRegistry
from stockstalk.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class TerminalUI:
    """Simple terminal interface for configuration."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize terminal UI.

        Args:
            config_manager: Configuration manager
        """
        self.config_manager = config_manager
        self.config = config_manager.load_config()

    def run(self) -> None:
        """Run the terminal UI."""
        while True:
            self._print_menu()
            choice = input("\nEnter choice: ").strip()

            if choice == "1":
                self._view_watchlist()
            elif choice == "2":
                self._add_stock()
            elif choice == "3":
                self._remove_stock()
            elif choice == "4":
                self._configure_notifications()
            elif choice == "5":
                self._configure_settings()
            elif choice == "6":
                self._save_and_exit()
                break
            elif choice == "7":
                print("\nExiting without saving...")
                break
            else:
                print("\nInvalid choice. Please try again.")

    def _print_menu(self) -> None:
        """Print main menu."""
        print("\n" + "=" * 50)
        print("StockStalk Configuration")
        print("=" * 50)
        print("1. View Watchlist")
        print("2. Add Stock to Watchlist")
        print("3. Remove Stock from Watchlist")
        print("4. Configure Notifications")
        print("5. Configure Settings")
        print("6. Save and Exit")
        print("7. Exit without Saving")

    def _view_watchlist(self) -> None:
        """Display current watchlist."""
        print("\n" + "=" * 50)
        print("Current Watchlist")
        print("=" * 50)

        if not self.config.watchlist:
            print("Watchlist is empty.")
            return

        for i, item in enumerate(self.config.watchlist, 1):
            print(f"\n{i}. {item.symbol}")
            print(f"   Indicators: {', '.join(item.enabled_indicators)}")
            if item.custom_params:
                print(f"   Custom params: {item.custom_params}")

    def _add_stock(self) -> None:
        """Add a stock to the watchlist."""
        print("\n" + "=" * 50)
        print("Add Stock to Watchlist")
        print("=" * 50)

        symbol = input("Enter stock symbol (e.g., AAPL): ").strip().upper()
        if not symbol:
            print("Invalid symbol.")
            return

        # Check if already exists
        if any(item.symbol == symbol for item in self.config.watchlist):
            print(f"{symbol} is already in the watchlist.")
            return

        # Select indicators
        available_indicators = IndicatorRegistry.list_indicators()
        print(f"\nAvailable indicators: {', '.join(available_indicators)}")
        print("Enter indicator names separated by commas (or press Enter for all):")
        indicators_input = input().strip()

        if indicators_input:
            indicators = [i.strip() for i in indicators_input.split(",")]
        else:
            indicators = available_indicators

        # Validate indicators
        valid_indicators = [i for i in indicators if i in available_indicators]
        if not valid_indicators:
            print("No valid indicators selected.")
            return

        # Create watchlist item
        watchlist_item = WatchlistItem(
            symbol=symbol,
            enabled_indicators=valid_indicators,
        )

        self.config.watchlist.append(watchlist_item)
        print(f"\n✓ Added {symbol} to watchlist with {len(valid_indicators)} indicators.")

    def _remove_stock(self) -> None:
        """Remove a stock from the watchlist."""
        self._view_watchlist()

        if not self.config.watchlist:
            return

        try:
            index = int(input("\nEnter number to remove (0 to cancel): "))
            if index == 0:
                return
            if 1 <= index <= len(self.config.watchlist):
                removed = self.config.watchlist.pop(index - 1)
                print(f"\n✓ Removed {removed.symbol} from watchlist.")
            else:
                print("Invalid number.")
        except ValueError:
            print("Invalid input.")

    def _configure_notifications(self) -> None:
        """Configure notification settings."""
        print("\n" + "=" * 50)
        print("Configure Notifications")
        print("=" * 50)

        print(
            f"\nCurrent Beeper Webhook URL: {self.config.notification_config.beeper_webhook_url or 'Not set'}"
        )
        update_webhook = input("Update webhook URL? (y/n): ").strip().lower()
        if update_webhook == "y":
            webhook = input("Enter Beeper webhook URL: ").strip()
            if webhook:
                self.config.notification_config.beeper_webhook_url = webhook
                print("✓ Webhook URL updated.")

        print(
            f"\nCurrent phone numbers: {', '.join(self.config.notification_config.phone_numbers) or 'None'}"
        )
        update_phones = input("Update phone numbers? (y/n): ").strip().lower()
        if update_phones == "y":
            phones = input("Enter phone numbers (comma-separated): ").strip()
            if phones:
                phone_list = [p.strip() for p in phones.split(",")]
                self.config.notification_config.phone_numbers = phone_list
                print(f"✓ Updated {len(phone_list)} phone numbers.")

        print(f"\nCurrent minimum priority: {self.config.notification_config.min_priority.value}")
        print("Options: low, medium, high, critical")
        update_priority = input("Update minimum priority? (y/n): ").strip().lower()
        if update_priority == "y":
            priority = input("Enter priority: ").strip().lower()
            if priority in ["low", "medium", "high", "critical"]:
                self.config.notification_config.min_priority = AlertPriority(priority)
                print("✓ Priority updated.")

    def _configure_settings(self) -> None:
        """Configure general settings."""
        print("\n" + "=" * 50)
        print("Configure Settings")
        print("=" * 50)

        print(f"\nCurrent check interval: {self.config.check_interval_minutes} minutes")
        update_interval = input("Update check interval? (y/n): ").strip().lower()
        if update_interval == "y":
            try:
                minutes = int(input("Enter interval in minutes: "))
                if minutes > 0:
                    self.config.check_interval_minutes = minutes
                    print("✓ Check interval updated.")
            except ValueError:
                print("Invalid input.")

        print(f"\nCurrent data lookback: {self.config.data_lookback_days} days")
        update_lookback = input("Update lookback period? (y/n): ").strip().lower()
        if update_lookback == "y":
            try:
                days = int(input("Enter days: "))
                if days > 0:
                    self.config.data_lookback_days = days
                    print("✓ Lookback period updated.")
            except ValueError:
                print("Invalid input.")

    def _save_and_exit(self) -> None:
        """Save configuration and exit."""
        try:
            self.config_manager.save_config(self.config)
            print("\n✓ Configuration saved successfully!")
        except Exception as e:
            print(f"\n✗ Error saving configuration: {e}")
