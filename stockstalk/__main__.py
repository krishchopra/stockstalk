"""Main entry point for the stockstalk application."""

import asyncio
import logging
import sys

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


async def run_analysis_async(dry_run: bool = False) -> None:
    """
    Run stock analysis for all watched symbols asynchronously.

    Args:
        dry_run: If True, analyze but don't send SMS notifications
    """
    from stockstalk.models import WatchlistItem
    from stockstalk.services.analyzer import StockAnalyzer
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService
    from stockstalk.settings import settings
    from stockstalk.storage import get_database, init_database

    try:
        mode_str = "DRY-RUN (no SMS)" if dry_run else "LIVE"
        logger.info("=" * 60)
        logger.info(f"Starting stock analysis run [{mode_str}]")
        logger.info("=" * 60)

        # Initialize database
        await init_database(settings.DATABASE_URL)
        db = get_database()

        # Get all watched symbols from database (union of all users' watchlists)
        watched_symbols = await db.get_all_watched_symbols()

        if not watched_symbols:
            logger.warning("No symbols being watched. Users can add stocks via SMS.")
            return

        logger.info(f"Analyzing {len(watched_symbols)} symbols from user watchlists")

        # Convert to WatchlistItem format for analyzer
        watchlist = [
            WatchlistItem(
                symbol=item["symbol"],
                enabled_indicators=item["enabled_indicators"],
            )
            for item in watched_symbols
        ]

        # Initialize services
        data_fetcher = StockDataFetcher()
        notifier = NotificationService()
        analyzer = StockAnalyzer(
            data_fetcher=data_fetcher,
            notifier=notifier,
            lookback_days=settings.DATA_LOOKBACK_DAYS,
        )

        # Analyze all stocks
        if dry_run:
            # Analyze without sending notifications
            all_results = {}
            all_alerts = []
            for item in watchlist:
                item_results = await analyzer.analyze_stock(item, send_alerts=False)
                all_results[item.symbol] = item_results
                for r in item_results:
                    if r.is_triggered:
                        all_alerts.append(r)
            results = all_results
        else:
            results = await analyzer.analyze_watchlist(watchlist)
            all_alerts = []

        # Log summary
        for symbol, indicator_results in results.items():
            triggered_count = sum(1 for r in indicator_results if r.is_triggered)
            logger.info(
                f"{symbol}: {triggered_count}/{len(indicator_results)} indicators triggered"
            )

        # In dry-run mode, print what would be sent as SMS
        if dry_run and all_alerts:
            print("\n" + "=" * 60)
            print("SMS DIGEST (what would be sent):")
            print("=" * 60)

            temp_notifier = NotificationService()
            digest_msg = temp_notifier._format_digest(
                all_alerts[:10], len(all_alerts), all_results_by_symbol=all_results
            )
            print(digest_msg)
            print("=" * 60)

        logger.info("=" * 60)
        logger.info("Analysis run completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during analysis run: {e}", exc_info=True)


async def run_scheduler_async() -> None:
    """Run the async scheduler for periodic stock analysis."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    from stockstalk.settings import settings
    from stockstalk.storage import init_database

    # Initialize database
    await init_database(settings.DATABASE_URL)

    interval_minutes = settings.CHECK_INTERVAL_MINUTES
    logger.info(f"Starting scheduler - checking every {interval_minutes} minutes")

    # Create scheduler
    scheduler = AsyncIOScheduler()

    async def scheduled_analysis() -> None:
        """Run a scheduled analysis."""
        await run_analysis_async()

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
    await run_analysis_async()

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()


def run_server() -> None:
    """Run the FastAPI server with uvicorn."""
    import uvicorn

    from stockstalk.api.server import app, init_app
    from stockstalk.services.analyzer import StockAnalyzer
    from stockstalk.services.data_fetcher import StockDataFetcher
    from stockstalk.services.notifier import NotificationService
    from stockstalk.settings import settings

    # Initialize services
    data_fetcher = StockDataFetcher()
    notifier = NotificationService()
    analyzer = StockAnalyzer(
        data_fetcher=data_fetcher,
        notifier=notifier,
        lookback_days=settings.DATA_LOOKBACK_DAYS,
    )

    init_app(analyzer)

    logger.info(f"Starting API server on {settings.HOST}:{settings.PORT}")
    logger.info(f"API docs available at http://{settings.HOST}:{settings.PORT}/docs")

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="StockStalk - Async Stock Monitoring App")
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
        "--dry-run",
        action="store_true",
        help="Analyze stocks but don't send SMS (shows what would be sent)",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host for API server (default: from env or 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port for API server (default: from env or 8000)",
    )

    args = parser.parse_args()

    # Override settings from CLI args if provided
    from stockstalk.settings import settings
    if args.host:
        settings.HOST = args.host
    if args.port:
        settings.PORT = args.port

    if args.server:
        # Run API server
        run_server()

    elif args.once or args.dry_run:
        # Run analysis once (with optional dry-run mode)
        asyncio.run(run_analysis_async(dry_run=args.dry_run))

    else:
        # Run scheduled analysis
        try:
            asyncio.run(run_scheduler_async())
        except KeyboardInterrupt:
            logger.info("Shutting down...")


if __name__ == "__main__":
    main()
