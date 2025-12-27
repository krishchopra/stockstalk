"""Main entry point for the stockstalk application."""

import logging
import os
import sys
from pathlib import Path

import schedule

from stockstalk.services.analyzer import StockAnalyzer
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.notifier import NotificationService
from stockstalk.utils.config import ConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("stockstalk.log"),
    ],
)

logger = logging.getLogger(__name__)


def run_analysis(config_manager: ConfigManager) -> None:
    """
    Run stock analysis for all watchlist items.

    Args:
        config_manager: Configuration manager
    """
    try:
        logger.info("=" * 60)
        logger.info("Starting stock analysis run")
        logger.info("=" * 60)

        # Load config
        config = config_manager.load_config()

        if not config.watchlist:
            logger.warning("Watchlist is empty. Add stocks to analyze.")
            return

        # Initialize services
        data_fetcher = StockDataFetcher()
        notifier = NotificationService(config.notification_config)
        analyzer = StockAnalyzer(
            data_fetcher=data_fetcher,
            notifier=notifier,
            lookback_days=config.data_lookback_days,
        )

        # Analyze each stock in watchlist
        for watchlist_item in config.watchlist:
            results = analyzer.analyze_stock(watchlist_item)

            # Log summary
            triggered_count = sum(1 for r in results if r.is_triggered)
            logger.info(
                f"{watchlist_item.symbol}: {triggered_count}/{len(results)} indicators triggered"
            )

        logger.info("=" * 60)
        logger.info("Analysis run completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during analysis run: {e}", exc_info=True)


def schedule_analysis(config_manager: ConfigManager) -> None:
    """
    Schedule periodic stock analysis.

    Args:
        config_manager: Configuration manager
    """
    config = config_manager.load_config()
    interval_minutes = config.check_interval_minutes

    logger.info(f"Scheduling analysis every {interval_minutes} minutes")

    # Run immediately
    run_analysis(config_manager)

    # Schedule periodic runs
    schedule.every(interval_minutes).minutes.do(run_analysis, config_manager)

    # Keep running
    import time

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="StockStalk - Stock Monitoring App")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to configuration file",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        help="Run configuration UI",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run API server",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run analysis once and exit",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for API server (default: 5000)",
    )

    args = parser.parse_args()

    # Initialize config manager
    config_manager = ConfigManager(args.config)

    if args.configure:
        # Run configuration UI
        from stockstalk.utils.terminal_ui import TerminalUI

        ui = TerminalUI(config_manager)
        ui.run()

    elif args.server:
        # Run API server
        from stockstalk.api.server import init_app, run_server

        config = config_manager.load_config()
        data_fetcher = StockDataFetcher()
        notifier = NotificationService(config.notification_config)
        analyzer = StockAnalyzer(
            data_fetcher=data_fetcher,
            notifier=notifier,
            lookback_days=config.data_lookback_days,
        )

        init_app(config_manager, analyzer)
        logger.info(f"Starting API server on port {args.port}")
        run_server(port=args.port)

    elif args.once:
        # Run analysis once
        run_analysis(config_manager)

    else:
        # Run scheduled analysis
        schedule_analysis(config_manager)


if __name__ == "__main__":
    main()
