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
from stockstalk.storage import get_database, init_database
from stockstalk.utils.config import ConfigManager

logger = logging.getLogger(__name__)

# Global services
_config_manager: ConfigManager | None = None
_stock_analyzer: StockAnalyzer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting StockStalk API server...")
    await init_database()
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down StockStalk API server...")


app = FastAPI(
    title="StockStalk API",
    description="Stock monitoring and analysis API with AWS SNS notifications",
    version="0.2.0",
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


def init_app(config_mgr: ConfigManager, analyzer: StockAnalyzer) -> None:
    """
    Initialize the FastAPI app with dependencies.

    Args:
        config_mgr: Configuration manager
        analyzer: Stock analyzer
    """
    global _config_manager, _stock_analyzer
    _config_manager = config_mgr
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
        current_data, historical_data = await data_fetcher.get_stock_data(symbol.upper(), days=30)

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
    """Get current watchlist from config and database."""
    try:
        config_manager = _config_manager or ConfigManager()
        config = config_manager.load_config()

        # Get config-based watchlist
        watchlist = [
            WatchlistItemResponse(
                symbol=item.symbol,
                indicators=item.enabled_indicators,
                custom_params=item.custom_params,
            )
            for item in config.watchlist
        ]

        # Add database-based watchlist items
        try:
            db = get_database()
            db_items = await db.get_watchlist(enabled_only=True)
            for item in db_items:
                # Skip if already in config watchlist
                if any(w.symbol == item.symbol for w in watchlist):
                    continue
                import json

                watchlist.append(
                    WatchlistItemResponse(
                        symbol=item.symbol,
                        indicators=(
                            json.loads(item.enabled_indicators) if item.enabled_indicators else []
                        ),
                        custom_params=json.loads(item.custom_params) if item.custom_params else {},
                    )
                )
        except Exception as e:
            logger.warning(f"Could not fetch DB watchlist: {e}")

        return WatchlistResponse(watchlist=watchlist)

    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/watchlist", response_model=MessageResponse)
async def add_to_watchlist(request: AddWatchlistRequest) -> MessageResponse:
    """Add a symbol to the watchlist (stored in database)."""
    try:
        db = get_database()
        await db.add_to_watchlist(
            symbol=request.symbol.upper(),
            enabled_indicators=request.enabled_indicators or IndicatorRegistry.list_indicators(),
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
            raise HTTPException(status_code=404, detail=f"{symbol.upper()} not found in watchlist")

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
    """Send a test SMS to verify AWS SNS configuration."""
    try:
        config_manager = _config_manager or ConfigManager()
        config = config_manager.load_config()
        notifier = NotificationService(config.notification_config)

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
    Debug endpoint to check notification status, recent alerts, and config.
    Useful for diagnosing why texts aren't being sent.
    """
    from datetime import datetime, timedelta

    try:
        db = get_database()
        config_manager = _config_manager or ConfigManager()
        config = config_manager.load_config()

        # Get recent alerts
        recent_alerts = await db.get_alerts(limit=20)
        alerts_last_hour = await db.get_alerts_count_since(minutes=60)

        # Check config
        notif_config = config.notification_config

        return {
            "notification_config": {
                "phone_numbers": notif_config.phone_numbers,
                "min_priority": notif_config.min_priority.value,
                "cooldown_minutes": notif_config.cooldown_minutes,
                "max_alerts_per_hour": notif_config.max_alerts_per_hour,
            },
            "rate_limits": {
                "alerts_last_hour": alerts_last_hour,
                "max_per_hour": notif_config.max_alerts_per_hour,
                "rate_limited": alerts_last_hour >= notif_config.max_alerts_per_hour,
            },
            "recent_alerts": [
                {
                    "symbol": a.symbol,
                    "indicator": a.indicator,
                    "message": a.message,
                    "priority": a.priority,
                    "sent_to": a.sent_to,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "cooldown_expires": (
                        (a.created_at + timedelta(minutes=notif_config.cooldown_minutes)).isoformat()
                        if a.created_at
                        else None
                    ),
                }
                for a in recent_alerts
            ],
            "now": datetime.now().isoformat(),
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
        <SYMBOL>     - Get current price and quick analysis (e.g., "AAPL")
        ADD <SYMBOL> - Add stock to watchlist
        REMOVE <SYMBOL> - Remove stock from watchlist
        LIST         - Show current watchlist
        STATUS       - Get alert status summary
        HELP         - Show available commands
    """
    logger.info(f"incoming sms from {From}: {Body}")
    
    # Parse the command
    text = Body.strip().upper()
    parts = text.split()
    
    if not parts:
        return twiml_response("empty message. text 'tutorial' for help.")
    
    command = parts[0].lower()
    
    try:
        # HELP/TUTORIAL command
        if command in ("tutorial", "help"):
            return twiml_response(
                "stockstalk commands:\n"
                "aapl - get stock info\n"
                "add aapl - add to watchlist\n"
                "remove aapl - remove from list\n"
                "list - show watchlist\n"
                "status - alert summary"
            )
        
        # LIST command
        if command == "list":
            config_manager = _config_manager or ConfigManager()
            config = config_manager.load_config()
            symbols = [item.symbol.lower() for item in config.watchlist]
            if symbols:
                return twiml_response(f"watchlist ({len(symbols)}):\n" + ", ".join(symbols))
            else:
                return twiml_response("watchlist is empty. text 'add <symbol>' to add stocks.")
        
        # STATUS command
        if command == "status":
            db = get_database()
            alerts_last_hour = await db.get_alerts_count_since(minutes=60)
            recent_alerts = await db.get_alerts(limit=5)
            
            msg = f"alerts (1hr): {alerts_last_hour}\n"
            if recent_alerts:
                msg += "recent:\n"
                for a in recent_alerts[:3]:
                    msg += f"- {a.symbol.lower()}/{a.indicator.lower()}\n"
            return twiml_response(msg)
        
        # ADD command
        if command == "add" and len(parts) >= 2:
            symbol = parts[1].upper()
            config_manager = _config_manager or ConfigManager()
            config = config_manager.load_config()
            
            # Check if already in watchlist
            existing = [item for item in config.watchlist if item.symbol == symbol]
            if existing:
                return twiml_response(f"{symbol.lower()} is already in your watchlist.")
            
            # Add with default indicators
            new_item = WatchlistItem(
                symbol=symbol,
                enabled_indicators=["RSI", "MACD", "Fundamental_Score"],
            )
            config.watchlist.append(new_item)
            config_manager.save_config(config)
            return twiml_response(f"added {symbol.lower()} to watchlist")
        
        # REMOVE command
        if command in ("remove", "delete", "rm") and len(parts) >= 2:
            symbol = parts[1].upper()
            config_manager = _config_manager or ConfigManager()
            config = config_manager.load_config()
            
            original_len = len(config.watchlist)
            config.watchlist = [item for item in config.watchlist if item.symbol != symbol]
            
            if len(config.watchlist) < original_len:
                config_manager.save_config(config)
                return twiml_response(f"removed {symbol.lower()} from watchlist")
            else:
                return twiml_response(f"{symbol.lower()} not found in watchlist")
        
        # Assume it's a stock symbol - run full analysis
        symbol = command.upper()
        data_fetcher = StockDataFetcher()
        
        try:
            # Fetch stock data
            stock_data, historical_data = await data_fetcher.get_stock_data(symbol, days=30)
            
            price = stock_data.current_price
            prev_close = stock_data.previous_close
            change = ((price - prev_close) / prev_close) * 100 if prev_close else 0
            
            # Direction indicator
            if change > 0:
                direction = "up"
            elif change < 0:
                direction = "down"
            else:
                direction = "flat"
            
            # Start building message with price info
            msg = f"{symbol.lower()}\n"
            msg += f"${price:.2f} ({change:+.2f}%) {direction}\n"
            if stock_data.volume:
                msg += f"vol: {stock_data.volume:,.0f}\n"
            msg += "\n"
            
            # Run all available indicators
            all_indicators = IndicatorRegistry.list_indicators()
            
            triggered_signals = []
            metrics = []
            
            for indicator_name in all_indicators:
                try:
                    indicator = IndicatorRegistry.get_indicator(indicator_name)
                    result = indicator.analyze(stock_data, historical_data)
                    
                    if result.is_triggered:
                        priority_prefix = "[!] " if result.priority.value in ("high", "critical") else ""
                        triggered_signals.append(f"{priority_prefix}{indicator_name.lower().replace('_', ' ')}")
                    
                    # Extract all available metrics from metadata
                    meta = result.metadata
                    
                    # Technical indicators
                    if "rsi" in meta and meta["rsi"]:
                        metrics.append(f"rsi: {meta['rsi']:.1f}")
                    if "macd" in meta:
                        metrics.append(f"macd: {meta['macd']:.2f}")
                    if "signal_line" in meta:
                        metrics.append(f"macd signal: {meta['signal_line']:.2f}")
                    if "volume_ratio" in meta and meta["volume_ratio"]:
                        metrics.append(f"vol ratio: {meta['volume_ratio']:.1f}x")
                    if "price_change_pct" in meta:
                        metrics.append(f"price chg: {meta['price_change_pct']:.1f}%")
                    if "sma_short" in meta and "sma_long" in meta:
                        metrics.append(f"sma 20/50: {meta['sma_short']:.2f}/{meta['sma_long']:.2f}")
                    
                    # Fundamental indicators
                    if "score" in meta and indicator_name == "Fundamental_Score":
                        metrics.append(f"fundamental: {meta['score']:.0f}/100")
                    if "peg_ratio" in meta and meta["peg_ratio"] and meta["peg_ratio"] > 0:
                        metrics.append(f"peg: {meta['peg_ratio']:.2f}")
                    if "pe_ratio" in meta and meta["pe_ratio"]:
                        metrics.append(f"p/e: {meta['pe_ratio']:.1f}")
                    if "roic" in meta and meta["roic"]:
                        metrics.append(f"roic: {meta['roic']:.1f}%")
                    if "debt_to_equity" in meta and meta["debt_to_equity"]:
                        metrics.append(f"d/e: {meta['debt_to_equity']:.2f}")
                    if "operating_margin" in meta and meta["operating_margin"]:
                        metrics.append(f"op margin: {meta['operating_margin']:.1f}%")
                    if "free_cash_flow" in meta and meta["free_cash_flow"]:
                        fcf = meta["free_cash_flow"]
                        if abs(fcf) >= 1e9:
                            metrics.append(f"fcf: ${fcf/1e9:.1f}b")
                        elif abs(fcf) >= 1e6:
                            metrics.append(f"fcf: ${fcf/1e6:.1f}m")
                    if "revenue_growth" in meta and meta["revenue_growth"]:
                        metrics.append(f"rev growth: {meta['revenue_growth']:.1f}%")
                    if "earnings_growth" in meta and meta["earnings_growth"]:
                        metrics.append(f"earnings growth: {meta['earnings_growth']:.1f}%")
                        
                except Exception as e:
                    logger.debug(f"indicator {indicator_name} failed for {symbol}: {e}")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_metrics = []
            for m in metrics:
                if m not in seen:
                    seen.add(m)
                    unique_metrics.append(m)
            
            # Add metrics
            if unique_metrics:
                msg += "metrics:\n"
                msg += "\n".join(unique_metrics)
                msg += "\n\n"
            
            # Add triggered signals
            if triggered_signals:
                msg += "signals:\n"
                msg += "\n".join(triggered_signals)
            else:
                msg += "no signals triggered"
            
            return twiml_response(msg)
            
        except Exception as e:
            logger.error(f"error fetching {symbol}: {e}", exc_info=True)
            return twiml_response(f"could not find stock: {symbol.lower()}")
    
    except Exception as e:
        logger.error(f"error processing sms command: {e}", exc_info=True)
        return twiml_response("error processing command. try again or text 'tutorial'.")
