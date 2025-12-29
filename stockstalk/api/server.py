"""FastAPI server for stock analysis API."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from stockstalk.models import WatchlistItem
from stockstalk.services.analyzer import IndicatorRegistry, StockAnalyzer
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.notifier import NotificationService
from stockstalk.settings import settings
from stockstalk.storage import get_database, init_database

logger = logging.getLogger(__name__)

# Global services
_stock_analyzer: StockAnalyzer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting StockStalk API server...")
    await init_database(settings.DATABASE_URL)
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down StockStalk API server...")


app = FastAPI(
    title="StockStalk API",
    description="Stock monitoring and analysis API with Twilio SMS notifications",
    version="0.3.0",
    lifespan=lifespan,
)


# Response models
class HealthResponse(BaseModel):
    status: str


class IndicatorResultResponse(BaseModel):
    indicator: str
    triggered: bool
    priority: str
    signal_strength: float
    message: str
    metadata: dict[str, Any]


class StockAnalysisResponse(BaseModel):
    symbol: str
    current_price: float
    change_percent: float
    results: list[IndicatorResultResponse]


class WatchlistItemResponse(BaseModel):
    symbol: str
    indicators: list[str]
    custom_params: dict[str, Any]


class WatchlistResponse(BaseModel):
    watchlist: list[WatchlistItemResponse]


class AddWatchlistRequest(BaseModel):
    symbol: str
    enabled_indicators: list[str] | None = None


class AddPhoneRequest(BaseModel):
    phone_number: str
    label: str | None = None


class MessageResponse(BaseModel):
    message: str


def init_app(analyzer: StockAnalyzer) -> None:
    """
    Initialize the FastAPI app with dependencies.

    Args:
        analyzer: Stock analyzer
    """
    global _stock_analyzer
    _stock_analyzer = analyzer


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@app.get("/api/stock/{symbol}", response_model=StockAnalysisResponse)
async def get_stock_analysis(symbol: str) -> StockAnalysisResponse:
    """
    Get current stock information and full analysis.

    Args:
        symbol: Stock ticker symbol
    """
    try:
        # Create analyzer with temporary config if not initialized
        data_fetcher = StockDataFetcher()

        # Create a watchlist item with all indicators
        watchlist_item = WatchlistItem(
            symbol=symbol.upper(),
            enabled_indicators=IndicatorRegistry.list_indicators(),
        )

        # Fetch stock data
        current_data, historical_data = await data_fetcher.get_stock_data(
            symbol.upper(), days=30
        )

        # Run indicators (without sending notifications for API requests)
        results = []
        for indicator_name in watchlist_item.enabled_indicators:
            try:
                params = watchlist_item.custom_params.get(indicator_name, {})
                indicator = IndicatorRegistry.get_indicator(indicator_name, **params)
                result = indicator.analyze(current_data, historical_data)
                results.append(result)
            except Exception as e:
                logger.error(f"Error running indicator {indicator_name}: {e}")

        # Calculate change percent
        change_percent = 0.0
        if current_data.previous_close > 0:
            change_percent = (
                (current_data.current_price - current_data.previous_close)
                / current_data.previous_close
                * 100
            )

        return StockAnalysisResponse(
            symbol=symbol.upper(),
            current_price=current_data.current_price,
            change_percent=round(change_percent, 2),
            results=[
                IndicatorResultResponse(
                    indicator=r.indicator_name,
                    triggered=r.is_triggered,
                    priority=r.priority.value,
                    signal_strength=r.signal_strength,
                    message=r.message,
                    metadata=r.metadata,
                )
                for r in results
            ],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing stock {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str) -> dict[str, Any]:
    """Get a quick quote for a stock."""
    try:
        data_fetcher = StockDataFetcher()
        stock_data = await data_fetcher.get_current_data(symbol.upper())

        change_percent = 0.0
        if stock_data.previous_close > 0:
            change_percent = (
                (stock_data.current_price - stock_data.previous_close)
                / stock_data.previous_close
                * 100
            )

        return {
            "symbol": stock_data.symbol,
            "price": stock_data.current_price,
            "open": stock_data.open_price,
            "high": stock_data.high_price,
            "low": stock_data.low_price,
            "previous_close": stock_data.previous_close,
            "change_percent": round(change_percent, 2),
            "volume": stock_data.volume,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/watchlist", response_model=WatchlistResponse)
async def get_watchlist() -> WatchlistResponse:
    """Get all watched symbols from the database (union of all user watchlists)."""
    try:
        db = get_database()
        watched_symbols = await db.get_all_watched_symbols()

        watchlist = [
            WatchlistItemResponse(
                symbol=item["symbol"],
                indicators=item["enabled_indicators"],
                custom_params={},
            )
            for item in watched_symbols
        ]

        return WatchlistResponse(watchlist=watchlist)

    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/watchlist", response_model=MessageResponse)
async def add_to_watchlist(request: AddWatchlistRequest) -> MessageResponse:
    """Add a symbol to the global watchlist (stored in database)."""
    try:
        db = get_database()
        await db.add_to_watchlist(
            symbol=request.symbol.upper(),
            enabled_indicators=request.enabled_indicators
            or IndicatorRegistry.list_indicators(),
        )
        return MessageResponse(message=f"Added {request.symbol.upper()} to watchlist")

    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/watchlist/{symbol}", response_model=MessageResponse)
async def remove_from_watchlist(symbol: str) -> MessageResponse:
    """Remove a symbol from the database watchlist."""
    try:
        db = get_database()
        removed = await db.remove_from_watchlist(symbol.upper())
        if removed:
            return MessageResponse(message=f"Removed {symbol.upper()} from watchlist")
        else:
            raise HTTPException(
                status_code=404, detail=f"{symbol.upper()} not found in watchlist"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/phones")
async def get_phone_numbers() -> dict[str, Any]:
    """Get configured phone numbers."""
    try:
        db = get_database()
        phones = await db.get_phone_numbers(enabled_only=False)
        return {
            "phone_numbers": [
                {
                    "phone_number": p.phone_number,
                    "label": p.label,
                    "enabled": p.enabled,
                }
                for p in phones
            ]
        }
    except Exception as e:
        logger.error(f"Error getting phone numbers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/phones", response_model=MessageResponse)
async def add_phone_number(request: AddPhoneRequest) -> MessageResponse:
    """Add a phone number for notifications."""
    try:
        db = get_database()
        await db.add_phone_number(request.phone_number, request.label)
        return MessageResponse(message=f"Added phone number {request.phone_number}")

    except Exception as e:
        logger.error(f"Error adding phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/phones/{phone_number}", response_model=MessageResponse)
async def remove_phone_number(phone_number: str) -> MessageResponse:
    """Remove a phone number."""
    try:
        db = get_database()
        removed = await db.remove_phone_number(phone_number)
        if removed:
            return MessageResponse(message=f"Removed phone number {phone_number}")
        else:
            raise HTTPException(status_code=404, detail="Phone number not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/indicators")
async def list_indicators() -> dict[str, list[str]]:
    """List all available indicators."""
    return {"indicators": IndicatorRegistry.list_indicators()}


@app.post("/api/test-sms/{phone_number}", response_model=MessageResponse)
async def test_sms(phone_number: str) -> MessageResponse:
    """Send a test SMS to verify Twilio configuration."""
    try:
        notifier = NotificationService()
        success = await notifier.send_test_message(phone_number)
        if success:
            return MessageResponse(message=f"Test SMS sent to {phone_number}")
        else:
            raise HTTPException(status_code=500, detail="Failed to send test SMS")

    except Exception as e:
        logger.error(f"Error sending test SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/status")
async def debug_status() -> dict:
    """
    Debug endpoint to check notification status, recent alerts, and settings.
    Useful for diagnosing why texts aren't being sent.
    """
    try:
        db = get_database()

        # Get recent alerts
        alerts_last_hour = await db.get_alerts_count_since(minutes=60)

        # Get watched symbols count
        watched_symbols = await db.get_all_watched_symbols()

        # Get phone numbers count
        phones = await db.get_phone_numbers(enabled_only=True)

        return {
            "settings": {
                "min_priority": settings.MIN_PRIORITY.value,
                "cooldown_minutes": settings.COOLDOWN_MINUTES,
                "max_alerts_per_hour": settings.MAX_ALERTS_PER_HOUR,
                "check_interval_minutes": settings.CHECK_INTERVAL_MINUTES,
                "twilio_configured": settings.is_twilio_configured(),
            },
            "rate_limits": {
                "alerts_last_hour": alerts_last_hour,
                "max_per_hour": settings.MAX_ALERTS_PER_HOUR,
                "rate_limited": alerts_last_hour >= settings.MAX_ALERTS_PER_HOUR,
            },
            "database": {
                "watched_symbols": len(watched_symbols),
                "phone_numbers": len(phones),
            },
        }

    except Exception as e:
        logger.error(f"Error in debug status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Twilio SMS Webhook - Receive and respond to incoming texts
# ============================================================================


def twiml_response(message: str) -> PlainTextResponse:
    """Create a TwiML response to reply to an SMS."""
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{message}</Message>
</Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")


@app.post("/api/sms/webhook", response_class=PlainTextResponse)
async def sms_webhook(
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
) -> PlainTextResponse:
    """
    Twilio webhook endpoint for incoming SMS.

    Commands:
        <SYMBOL>     - Get current price and full analysis (e.g., "AAPL")
        ADD <SYMBOL> - Add stock to your personal watchlist
        REMOVE <SYMBOL> - Remove stock from your watchlist
        LIST         - Show your watchlist
        STATUS       - Get alert status summary
        TUTORIAL     - Show available commands
    """
    logger.info(f"incoming sms from {From}: {Body}")

    # Parse the command
    text = Body.strip().upper()
    parts = text.split()

    if not parts:
        return twiml_response("empty message. text 'tutorial' for help.")

    command = parts[0].lower()
    user_phone = From  # Use sender's phone as user ID

    try:
        db = get_database()

        # Ensure user exists in phone_numbers table
        try:
            await db.add_phone_number(user_phone)
        except Exception:
            pass  # Already exists, ignore

        # HELP/TUTORIAL command
        if command in ("tutorial", "help"):
            return twiml_response(
                "stockstalk commands:\n"
                "aapl - get stock info\n"
                "add aapl - add to watchlist\n"
                "remove aapl - remove from list\n"
                "list - show your watchlist\n"
                "status - alert summary"
            )

        # LIST command - show user's personal watchlist
        if command == "list":
            user_watchlist = await db.get_user_watchlist(user_phone)
            symbols = [item.symbol.lower() for item in user_watchlist]
            if symbols:
                return twiml_response(
                    f"your watchlist ({len(symbols)}):\n" + ", ".join(symbols)
                )
            else:
                return twiml_response(
                    "your watchlist is empty. text 'add <symbol>' to add stocks."
                )

        # STATUS command
        if command == "status":
            alerts_last_hour = await db.get_alerts_count_since(minutes=60)
            user_watchlist = await db.get_user_watchlist(user_phone)

            msg = f"alerts (1hr): {alerts_last_hour}\n"
            msg += f"your stocks: {len(user_watchlist)}\n"
            if user_watchlist:
                symbols = [item.symbol.lower() for item in user_watchlist[:5]]
                msg += f"watching: {', '.join(symbols)}"
            return twiml_response(msg)

        # ADD command - add to user's personal watchlist
        if command == "add" and len(parts) >= 2:
            symbol = parts[1].upper()

            # Check if already in user's watchlist
            if await db.user_has_symbol(user_phone, symbol):
                return twiml_response(f"{symbol.lower()} is already in your watchlist.")

            # Add to user's watchlist with default indicators
            await db.add_to_user_watchlist(
                user_phone,
                symbol,
                enabled_indicators=settings.DEFAULT_INDICATORS,
            )
            return twiml_response(f"added {symbol.lower()} to your watchlist")

        # REMOVE command - remove from user's personal watchlist
        if command in ("remove", "delete", "rm") and len(parts) >= 2:
            symbol = parts[1].upper()

            removed = await db.remove_from_user_watchlist(user_phone, symbol)
            if removed:
                return twiml_response(f"removed {symbol.lower()} from your watchlist")
            else:
                return twiml_response(f"{symbol.lower()} not in your watchlist")

        # Assume it's a stock symbol - run full analysis
        symbol = command.upper()
        data_fetcher = StockDataFetcher()

        try:
            # Fetch stock data
            stock_data, historical_data = await data_fetcher.get_stock_data(
                symbol, days=30
            )

            price = stock_data.current_price
            prev_close = stock_data.previous_close
            change_day = ((price - prev_close) / prev_close) * 100 if prev_close else 0

            # Calculate weekly and monthly changes from historical data
            closes = historical_data.close_prices
            change_week = 0.0
            change_month = 0.0
            if len(closes) >= 5:
                week_ago_price = closes[-5]
                change_week = ((price - week_ago_price) / week_ago_price) * 100
            if len(closes) >= 21:
                month_ago_price = closes[-21]
                change_month = ((price - month_ago_price) / month_ago_price) * 100
            elif len(closes) >= 1:
                # Use oldest available if less than 21 days
                month_ago_price = closes[0]
                change_month = ((price - month_ago_price) / month_ago_price) * 100

            # Direction indicator
            if change_day > 0:
                direction = "📈"
            elif change_day < 0:
                direction = "📉"
            else:
                direction = "➡️"

            # Start building message with price info
            msg = f"{symbol.lower()}\n"
            msg += f"${price:.2f} ({change_day:+.1f}% today) {direction}\n"
            msg += f"week: {change_week:+.1f}% | month: {change_month:+.1f}%\n"
            if stock_data.volume:
                msg += f"vol: {stock_data.volume:,.0f}\n"

            # Run all available indicators
            all_indicators = IndicatorRegistry.list_indicators()

            triggered_signals = []
            all_results = []
            metrics = []
            fundamental_score = 0
            fundamental_max = 7

            for indicator_name in all_indicators:
                try:
                    indicator = IndicatorRegistry.get_indicator(indicator_name)
                    result = indicator.analyze(stock_data, historical_data)
                    all_results.append(result)

                    if result.is_triggered:
                        priority_prefix = (
                            "[!] "
                            if result.priority.value in ("high", "critical")
                            else ""
                        )
                        triggered_signals.append(
                            f"{priority_prefix}{indicator_name.lower().replace('_', ' ')}"
                        )

                    # Extract all available metrics from metadata
                    meta = result.metadata

                    # Technical indicators
                    if "rsi" in meta and meta["rsi"]:
                        metrics.append(f"rsi: {meta['rsi']:.1f}")
                    if "volume_ratio" in meta and meta["volume_ratio"]:
                        metrics.append(f"vol ratio: {meta['volume_ratio']:.1f}x")

                    # Fundamental indicators
                    if "score" in meta and indicator_name == "Fundamental_Score":
                        fundamental_score = meta.get("score", 0)
                        fundamental_max = meta.get("max_score", 7)
                    if "debt_to_equity" in meta and meta["debt_to_equity"]:
                        metrics.append(f"d/e: {meta['debt_to_equity']:.2f}")
                    if "revenue_growth" in meta and meta["revenue_growth"]:
                        metrics.append(f"rev growth: {meta['revenue_growth']:.1f}%")
                    if "earnings_growth" in meta and meta["earnings_growth"]:
                        metrics.append(
                            f"earnings growth: {meta['earnings_growth']:.1f}%"
                        )

                except Exception as e:
                    logger.debug(f"indicator {indicator_name} failed for {symbol}: {e}")

            # Calculate composite score (0-100)
            # Based on: signals triggered, signal strength, and fundamental score
            total_indicators = len(all_results)
            triggered_count = len(triggered_signals)
            avg_signal_strength = (
                sum(r.signal_strength for r in all_results) / total_indicators
                if total_indicators > 0
                else 0
            )

            # Composite score formula:
            # - 40% from triggered signals ratio
            # - 30% from average signal strength
            # - 30% from fundamental score
            signal_component = (triggered_count / max(total_indicators, 1)) * 40
            strength_component = avg_signal_strength * 30
            fundamental_component = (
                (fundamental_score / fundamental_max) * 30 if fundamental_max > 0 else 0
            )
            composite_score = (
                signal_component + strength_component + fundamental_component
            )

            # Remove duplicates while preserving order
            seen = set()
            unique_metrics = []
            for m in metrics:
                if m not in seen:
                    seen.add(m)
                    unique_metrics.append(m)

            # Add composite score prominently
            msg += f"\n⭐ score: {composite_score:.0f}/100\n"
            msg += f"fundamental: {fundamental_score}/{fundamental_max}\n"

            # Add key metrics
            if unique_metrics:
                msg += "\nmetrics:\n"
                msg += "\n".join(unique_metrics)

            # Add triggered signals
            msg += f"\n\nsignals ({triggered_count}):\n"
            if triggered_signals:
                msg += "\n".join(triggered_signals)
            else:
                msg += "none triggered"

            return twiml_response(msg)

        except Exception as e:
            logger.error(f"error fetching {symbol}: {e}", exc_info=True)
            return twiml_response(f"could not find stock: {symbol.lower()}")

    except Exception as e:
        logger.error(f"error processing sms command: {e}", exc_info=True)
        return twiml_response("error processing command. try again or text 'tutorial'.")
