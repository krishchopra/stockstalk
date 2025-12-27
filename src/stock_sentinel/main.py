"""Main entry point for Stock Sentinel."""

import asyncio
import logging
import sys

from stock_sentinel.config.settings import get_settings
from stock_sentinel.scheduler.jobs import run_scheduler
from stock_sentinel.storage.database import init_database


def setup_logging() -> None:
    """Configure logging for the application."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


async def main() -> None:
    """Main entry point."""
    setup_logging()

    logger = logging.getLogger(__name__)
    settings = get_settings()

    logger.info("Starting Stock Sentinel...")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Check interval: {settings.check_interval_minutes} minutes")
    logger.info(f"Market hours only: {settings.market_hours_only}")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Run scheduler
    await run_scheduler()


def run() -> None:
    """Run the application."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    run()
