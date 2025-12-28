"""FastAPI server for stock analysis API."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
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
                        indicators=json.loads(item.enabled_indicators) if item.enabled_indicators else [],
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
