"""FastAPI server for stock analysis API."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from stockstalk.models import WatchlistItem
from stockstalk.services.ai_assistant import AIAssistant
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


@app.post("/api/digest/{phone_number}")
async def send_digest(phone_number: str) -> dict[str, Any]:
    """
    Generate and send an AI-powered daily digest to a specific user.

    Args:
        phone_number: Phone number to send digest to
    """
    try:
        db = get_database()
        ai_assistant = AIAssistant()
        notifier = NotificationService()

        # Get user's watchlist
        user_watchlist = await db.get_user_watchlist(phone_number)

        if not user_watchlist:
            raise HTTPException(
                status_code=400,
                detail="User has no watchlist. Add stocks first.",
            )

        # Generate digest
        digest = await ai_assistant.generate_daily_digest(
            user_watchlist,
            include_discoveries=True,
            max_discoveries=3,
        )

        # Format message
        message = ai_assistant.format_digest_sms(digest)

        # Send SMS
        success = await notifier.send_sms(phone_number, message)

        return {
            "success": success,
            "message": message,
            "watchlist_count": len(digest.watchlist_insights),
            "discoveries_count": len(digest.discovery_insights),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending digest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opportunities")
async def get_opportunities(
    top_n: int = 50,
    min_score: float = 50.0,
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Scan VTI holdings for investment opportunities.

    Args:
        top_n: Number of top VTI holdings to scan
        min_score: Minimum composite score threshold
        max_results: Maximum opportunities to return
    """
    try:
        ai_assistant = AIAssistant()
        opportunities = await ai_assistant.scan_for_opportunities(
            top_n=top_n,
            min_score=min_score,
            max_results=max_results,
        )

        return {
            "opportunities": [
                {
                    "symbol": opp.symbol,
                    "price": opp.price,
                    "change_percent": opp.change_percent,
                    "composite_score": opp.composite_score,
                    "recommendation": opp.recommendation,
                    "triggered_signals": opp.triggered_signals,
                    "key_metrics": opp.key_metrics,
                }
                for opp in opportunities
            ],
            "scanned_count": top_n,
        }

    except Exception as e:
        logger.error(f"Error finding opportunities: {e}", exc_info=True)
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
                "openai_configured": settings.is_openai_configured(),
                "openai_model": settings.OPENAI_MODEL
                if settings.is_openai_configured()
                else None,
                "daily_digest_enabled": settings.DAILY_DIGEST_ENABLED,
                "daily_digest_time": f"{settings.DAILY_DIGEST_HOUR:02d}:{settings.DAILY_DIGEST_MINUTE:02d}",
                "daily_digest_timezone": settings.DAILY_DIGEST_TIMEZONE,
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
    Twilio webhook endpoint for incoming SMS with AI-powered natural language understanding.

    Commands:
        <SYMBOL>     - Get current price and full analysis (e.g., "AAPL")
        ADD <SYMBOL> - Add stock to your personal watchlist
        REMOVE <SYMBOL> - Remove stock from your watchlist
        LIST         - Show your watchlist
        STATUS       - Get alert status summary
        DIGEST       - Get AI-powered daily digest of your watchlist
        OPPORTUNITIES - Find investment opportunities from VTI
        TUTORIAL     - Show available commands

    Natural Language:
        "What should I invest in?" - Get personalized recommendations
        "How's my portfolio doing?" - Get watchlist summary
        "Tell me about AAPL" - Detailed stock analysis with AI insights
    """
    logger.info(f"incoming sms from {From}: {Body}")

    # Parse the command
    text = Body.strip()
    text_upper = text.upper()
    parts = text_upper.split()

    if not parts:
        return twiml_response("empty message. text 'tutorial' for help.")

    command = parts[0].lower()
    user_phone = From  # Use sender's phone as user ID

    try:
        db = get_database()
        ai_assistant = AIAssistant()

        # Ensure user exists in phone_numbers table
        try:
            await db.add_phone_number(user_phone)
        except Exception:
            pass  # Already exists, ignore

        # Get user's watchlist for context
        user_watchlist = await db.get_user_watchlist(user_phone)

        # HELP/TUTORIAL command - quick response without AI
        if command in ("tutorial", "help", "?"):
            return twiml_response(
                "hey! i'm your stock buddy 📈\n\n"
                "just text me like you'd text a friend:\n"
                "• 'how's apple doing?'\n"
                "• 'add tesla to my list'\n"
                "• 'what should i invest in?'\n"
                "• 'compare aapl and msft'\n"
                "• 'how's my watchlist?'\n"
                "\nor just send a ticker like 'aapl'"
            )

        # Route everything through the AI agent
        # The agent will decide what tools to use based on the message
        logger.info(f"Processing with AI agent: {text}")
        try:
            response = await ai_assistant.chat(
                user_message=text,
                user_phone=user_phone,
                user_watchlist=user_watchlist,
                db=db,
            )
            if not response or not response.strip():
                logger.warning("AI assistant returned empty response, using fallback")
                response = "sorry, i didn't get that. try again?"
            logger.info(f"AI response: {response[:100]}...")  # Log first 100 chars
            return twiml_response(response.lower())
        except Exception as e:
            logger.error(f"Error in AI chat: {e}", exc_info=True)
            return twiml_response(
                "error processing command. try again or text 'tutorial'."
            )

    except Exception as e:
        logger.error(f"error processing sms command: {e}", exc_info=True)
        return twiml_response("error processing command. try again or text 'tutorial'.")
