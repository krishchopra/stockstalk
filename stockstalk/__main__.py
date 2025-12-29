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


async def send_daily_digest_to_all_users() -> None:
    """
    Send AI-powered daily digest to all users with watchlists.

    This runs as a cron job at the configured time each day.
    """
    from stockstalk.services.ai_assistant import AIAssistant
    from stockstalk.services.notifier import NotificationService
    from stockstalk.storage import get_database

    logger.info("=" * 60)
    logger.info("Starting daily digest generation")
    logger.info("=" * 60)

    try:
        db = get_database()
        ai_assistant = AIAssistant()
        notifier = NotificationService()

        # Get all phone numbers with watchlists
        all_phones = await db.get_phone_numbers(enabled_only=True)

        if not all_phones:
            logger.info("No users to send daily digest to")
            return

        for phone_record in all_phones:
            phone_number = phone_record.phone_number
            try:
                # Get user's watchlist
                user_watchlist = await db.get_user_watchlist(phone_number)

                if not user_watchlist:
                    logger.debug(f"Skipping {phone_number} - empty watchlist")
                    continue

                logger.info(
                    f"Generating digest for {phone_number} "
                    f"({len(user_watchlist)} stocks)"
                )

                # Generate personalized digest
                digest = await ai_assistant.generate_daily_digest(
                    user_watchlist,
                    include_discoveries=True,
                    max_discoveries=2,
                )

                # Format and send SMS
                message = ai_assistant.format_digest_sms(digest)

                # Truncate if too long for SMS (160 chars per segment, max ~3 segments)
                if len(message) > 450:
                    message = message[:447] + "..."

                success = await notifier.send_sms(phone_number, message)

                if success:
                    logger.info(f"Daily digest sent to {phone_number}")
                else:
                    logger.error(f"Failed to send digest to {phone_number}")

            except Exception as e:
                logger.error(f"Error generating digest for {phone_number}: {e}")
                continue

        logger.info("=" * 60)
        logger.info("Daily digest generation completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in daily digest job: {e}", exc_info=True)


async def run_scheduler_async() -> None:
    """Run the async scheduler for periodic stock analysis and daily digests."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
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

    # Add periodic analysis job
    scheduler.add_job(
        scheduled_analysis,
        IntervalTrigger(minutes=interval_minutes),
        id="stock_analysis",
        name="Stock Analysis",
        max_instances=1,
    )

    # Add daily digest job (runs at configured time)
    if settings.DAILY_DIGEST_ENABLED:
        logger.info(
            f"Daily digest enabled at {settings.DAILY_DIGEST_HOUR:02d}:"
            f"{settings.DAILY_DIGEST_MINUTE:02d} {settings.DAILY_DIGEST_TIMEZONE}"
        )

        scheduler.add_job(
            send_daily_digest_to_all_users,
            CronTrigger(
                hour=settings.DAILY_DIGEST_HOUR,
                minute=settings.DAILY_DIGEST_MINUTE,
                timezone=settings.DAILY_DIGEST_TIMEZONE,
            ),
            id="daily_digest",
            name="Daily Digest",
            max_instances=1,
        )
    else:
        logger.info("Daily digest disabled (set DAILY_DIGEST_ENABLED=true to enable)")

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


async def run_digest_async(phone_number: str | None = None) -> None:
    """
    Run daily digest manually for testing.

    Args:
        phone_number: Optional specific phone number. If None, sends to all users.
    """
    from stockstalk.services.ai_assistant import AIAssistant
    from stockstalk.services.notifier import NotificationService
    from stockstalk.settings import settings
    from stockstalk.storage import get_database, init_database

    logger.info("=" * 60)
    logger.info("Running manual daily digest")
    logger.info("=" * 60)

    await init_database(settings.DATABASE_URL)
    db = get_database()
    ai_assistant = AIAssistant()
    notifier = NotificationService()

    if phone_number:
        # Send to specific user
        phone_numbers = [phone_number]
    else:
        # Send to all enabled users
        all_phones = await db.get_phone_numbers(enabled_only=True)
        phone_numbers = [p.phone_number for p in all_phones]

    if not phone_numbers:
        logger.warning("No phone numbers to send digest to")
        return

    for phone in phone_numbers:
        try:
            user_watchlist = await db.get_user_watchlist(phone)

            if not user_watchlist:
                logger.info(f"Skipping {phone} - empty watchlist")
                continue

            logger.info(f"Generating digest for {phone} ({len(user_watchlist)} stocks)")

            digest = await ai_assistant.generate_daily_digest(
                user_watchlist,
                include_discoveries=True,
                max_discoveries=3,
            )

            message = ai_assistant.format_digest_sms(digest)

            print("\n" + "=" * 60)
            print(f"DIGEST FOR {phone}:")
            print("=" * 60)
            print(message)
            print("=" * 60)

            # Actually send unless it's a dry run (no phone specified = test mode)
            if phone_number:
                success = await notifier.send_sms(phone, message)
                if success:
                    logger.info(f"Digest sent to {phone}")
                else:
                    logger.error(f"Failed to send to {phone}")

        except Exception as e:
            logger.error(f"Error with {phone}: {e}", exc_info=True)


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="StockStalk - Async Stock Monitoring App"
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
        "--dry-run",
        action="store_true",
        help="Analyze stocks but don't send SMS (shows what would be sent)",
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Generate and send daily digest to all users (or use --phone for specific user)",
    )
    parser.add_argument(
        "--phone",
        type=str,
        help="Phone number to send digest to (use with --digest)",
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

    elif args.digest:
        # Run daily digest manually
        asyncio.run(run_digest_async(phone_number=args.phone))

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
