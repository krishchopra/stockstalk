"""Main entry point for the stockstalk application."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("stockstalk.log"),
    ],
)

# Reduce noise from third-party libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


async def run_analysis_async(config_path: Path) -> None:
    """
    Run stock analysis for all watchlist items asynchronously.

    Args:
        config_path: Path to configuration file
    """
    from stockstalk.services.analyzer import StockAnalyzer
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService
    from stockstalk.storage import init_database
    from stockstalk.utils.config import ConfigManager

    try:
        logger.info("=" * 60)
        logger.info("Starting stock analysis run")
        logger.info("=" * 60)

        # Initialize database
        await init_database()

        # Load config
        config_manager = ConfigManager(config_path)
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
            notification_config=config.notification_config,
            lookback_days=config.data_lookback_days,
        )

        # Analyze all stocks in watchlist
        results = await analyzer.analyze_watchlist(config.watchlist)

        # Log summary
        for symbol, indicator_results in results.items():
            triggered_count = sum(1 for r in indicator_results if r.is_triggered)
            logger.info(
                f"{symbol}: {triggered_count}/{len(indicator_results)} indicators triggered"
            )

        logger.info("=" * 60)
        logger.info("Analysis run completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during analysis run: {e}", exc_info=True)


async def run_scheduler_async(config_path: Path) -> None:
    """
    Run the async scheduler for periodic stock analysis.

    Args:
        config_path: Path to configuration file
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    from stockstalk.services.analyzer import StockAnalyzer
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService
    from stockstalk.storage import init_database
    from stockstalk.utils.config import ConfigManager

    # Initialize database
    await init_database()

    # Load config
    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()
    interval_minutes = config.check_interval_minutes

    logger.info(f"Starting scheduler - checking every {interval_minutes} minutes")

    # Create scheduler
    scheduler = AsyncIOScheduler()

    async def scheduled_analysis() -> None:
        """Run a scheduled analysis."""
        await run_analysis_async(config_path)

    # Add job
    scheduler.add_job(
        scheduled_analysis,
        IntervalTrigger(minutes=interval_minutes),
        id="stock_analysis",
        name="Stock Analysis",
        max_instances=1,
    )

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")

    # Run initial analysis
    await run_analysis_async(config_path)

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()


def run_server(config_path: Path, host: str, port: int) -> None:
    """
    Run the FastAPI server with uvicorn.

    Args:
        config_path: Path to configuration file
        host: Host to bind to
        port: Port to bind to
    """
    import uvicorn

    from stockstalk.api.server import app, init_app
    from stockstalk.services.analyzer import StockAnalyzer
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService
    from stockstalk.utils.config import ConfigManager

    # Load config and initialize services
    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()

    data_fetcher = StockDataFetcher()
    notifier = NotificationService(config.notification_config)
    analyzer = StockAnalyzer(
        data_fetcher=data_fetcher,
        notifier=notifier,
        notification_config=config.notification_config,
        lookback_days=config.data_lookback_days,
    )

    init_app(config_manager, analyzer)

    logger.info(f"Starting API server on {host}:{port}")
    logger.info(f"API docs available at http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="StockStalk - Async Stock Monitoring App")
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
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for API server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for API server (default: 8000)",
    )

    args = parser.parse_args()

    if args.configure:
        # Run configuration UI
        from stockstalk.utils.terminal_ui import TerminalUI
        from stockstalk.utils.config import ConfigManager

        config_manager = ConfigManager(args.config)
        ui = TerminalUI(config_manager)
        ui.run()

    elif args.server:
        # Run API server
        run_server(args.config, args.host, args.port)

    elif args.once:
        # Run analysis once
        asyncio.run(run_analysis_async(args.config))

    else:
        # Run scheduled analysis
        try:
            asyncio.run(run_scheduler_async(args.config))
        except KeyboardInterrupt:
            logger.info("Shutting down...")


if __name__ == "__main__":
    main()
