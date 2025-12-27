"""Webhook server for receiving SMS messages and providing API."""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from stock_sentinel import __version__
from stock_sentinel.config.settings import get_settings
from stock_sentinel.data.providers.yahoo import YahooFinanceProvider
from stock_sentinel.indicators import indicator_registry
from stock_sentinel.notifications.base import Notification, NotificationPriority
from stock_sentinel.notifications.beeper import BeeperProvider
from stock_sentinel.storage.database import get_database, init_database

logger = logging.getLogger(__name__)


# Request/Response Models
class IncomingMessage(BaseModel):
    """Incoming SMS/message from Beeper webhook."""

    sender: str = Field(..., description="Sender phone number")
    message: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.now)
    message_id: str | None = None


class WebhookResponse(BaseModel):
    """Response for webhook requests."""

    status: str
    message: str | None = None


class StockCheckRequest(BaseModel):
    """Request to check a stock."""

    symbol: str = Field(..., description="Stock symbol to check")


class StockCheckResponse(BaseModel):
    """Response for stock check."""

    symbol: str
    price: float
    change_percent: float
    signals: list[dict]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime


# Command handlers
class CommandHandler:
    """Handle incoming text commands."""

    def __init__(self):
        self.data_provider = YahooFinanceProvider()
        self.notification_provider = BeeperProvider()

    async def handle_message(self, message: IncomingMessage) -> str:
        """
        Process an incoming message and return a response.

        Supported commands:
        - QUOTE <symbol>: Get stock quote
        - CHECK <symbol>: Run indicators on stock
        - WATCH <symbol>: Add to watchlist
        - UNWATCH <symbol>: Remove from watchlist
        - LIST: Show watchlist
        - HELP: Show help
        """
        text = message.message.strip().upper()
        parts = text.split()

        if not parts:
            return "Empty message. Send HELP for commands."

        command = parts[0]

        try:
            if command == "HELP":
                return self._help()
            elif command == "QUOTE" and len(parts) >= 2:
                return await self._quote(parts[1])
            elif command == "CHECK" and len(parts) >= 2:
                return await self._check(parts[1])
            elif command == "WATCH" and len(parts) >= 2:
                return await self._watch(parts[1])
            elif command == "UNWATCH" and len(parts) >= 2:
                return await self._unwatch(parts[1])
            elif command == "LIST":
                return await self._list()
            elif command == "STATUS":
                return await self._status()
            else:
                # Try to interpret as a stock symbol
                if re.match(r"^[A-Z]{1,5}$", command):
                    return await self._quote(command)
                return f"Unknown command: {command}. Send HELP for commands."

        except Exception as e:
            logger.error(f"Error handling command: {e}")
            return f"Error: {e!s}"

    def _help(self) -> str:
        """Return help text."""
        return (
            "📊 Stock Sentinel Commands:\n\n"
            "QUOTE <symbol> - Get stock quote\n"
            "CHECK <symbol> - Run all indicators\n"
            "WATCH <symbol> - Add to watchlist\n"
            "UNWATCH <symbol> - Remove from watchlist\n"
            "LIST - Show watchlist\n"
            "STATUS - System status\n"
            "<symbol> - Quick quote\n"
        )

    async def _quote(self, symbol: str) -> str:
        """Get stock quote."""
        stock_data = await self.data_provider.get_stock_data(symbol)
        quote = stock_data.quote

        return (
            f"📈 {symbol}\n"
            f"Price: ${quote.price:.2f}\n"
            f"Change: {quote.change_percent:+.2f}%\n"
            f"Volume: {quote.volume:,}\n"
            f"52W: ${quote.week_52_low:.2f}-${quote.week_52_high:.2f}"
        )

    async def _check(self, symbol: str) -> str:
        """Run indicators on a stock."""
        stock_data = await self.data_provider.get_stock_data(symbol)
        results = await indicator_registry.analyze_all(stock_data)

        lines = [f"📊 {symbol} Analysis:"]
        for result in results:
            lines.append(f"{result.signal.emoji} {result.indicator_name}: {result.message}")

        return "\n".join(lines) if len(lines) > 1 else f"No signals for {symbol}"

    async def _watch(self, symbol: str) -> str:
        """Add symbol to watchlist."""
        db = get_database()
        await db.add_to_watchlist(symbol)
        return f"✅ Added {symbol} to watchlist"

    async def _unwatch(self, symbol: str) -> str:
        """Remove symbol from watchlist."""
        db = get_database()
        if await db.remove_from_watchlist(symbol):
            return f"❌ Removed {symbol} from watchlist"
        return f"Symbol {symbol} not in watchlist"

    async def _list(self) -> str:
        """List watchlist."""
        db = get_database()
        items = await db.get_watchlist()

        if not items:
            return "Watchlist is empty. Use WATCH <symbol> to add stocks."

        symbols = [item.symbol for item in items]
        return f"📋 Watchlist ({len(symbols)}):\n" + ", ".join(symbols)

    async def _status(self) -> str:
        """Get system status."""
        db = get_database()
        watchlist = await db.get_watchlist()
        phones = await db.get_phone_numbers()

        is_open = await self.data_provider.is_market_open()
        market_status = "🟢 Open" if is_open else "🔴 Closed"

        return (
            f"📊 Stock Sentinel v{__version__}\n"
            f"Market: {market_status}\n"
            f"Watching: {len(watchlist)} stocks\n"
            f"Phones: {len(phones)} configured\n"
            f"Indicators: {len(indicator_registry)} active"
        )


# FastAPI app
command_handler = CommandHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    await init_database()
    logger.info("Stock Sentinel webhook server started")
    yield
    # Shutdown
    logger.info("Stock Sentinel webhook server stopped")


app = FastAPI(
    title="Stock Sentinel",
    description="Real-time stock monitoring with SMS alerts",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.now(),
    )


@app.post("/webhook/incoming", response_model=WebhookResponse)
async def incoming_message(
    message: IncomingMessage,
    background_tasks: BackgroundTasks,
):
    """
    Handle incoming SMS messages from Beeper.

    This endpoint receives messages and responds with stock information
    or executes commands.
    """
    logger.info(f"Received message from {message.sender}: {message.message}")

    # Process the message
    response_text = await command_handler.handle_message(message)

    # Send response back asynchronously
    async def send_response():
        notification = Notification(
            recipient=message.sender,
            message=response_text,
            priority=NotificationPriority.NORMAL,
        )
        beeper = BeeperProvider()
        await beeper.send(notification)

    background_tasks.add_task(send_response)

    return WebhookResponse(status="ok", message="Response queued")


@app.post("/api/check", response_model=StockCheckResponse)
async def check_stock(request: StockCheckRequest):
    """Check a stock with all indicators via API."""
    provider = YahooFinanceProvider()

    try:
        stock_data = await provider.get_stock_data(request.symbol.upper())
        results = await indicator_registry.analyze_all(stock_data)

        signals = [
            {
                "indicator": r.indicator_name,
                "signal": r.signal.value,
                "value": r.value,
                "message": r.message,
                "should_alert": r.should_alert,
            }
            for r in results
        ]

        return StockCheckResponse(
            symbol=stock_data.symbol,
            price=stock_data.quote.price,
            change_percent=stock_data.quote.change_percent,
            signals=signals,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/watchlist")
async def get_watchlist():
    """Get current watchlist."""
    db = get_database()
    items = await db.get_watchlist()
    return {"watchlist": [item.model_dump() for item in items]}


@app.post("/api/watchlist/{symbol}")
async def add_to_watchlist(symbol: str):
    """Add a symbol to watchlist."""
    db = get_database()
    item = await db.add_to_watchlist(symbol.upper())
    return {"status": "ok", "item": item.model_dump()}


@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str):
    """Remove a symbol from watchlist."""
    db = get_database()
    removed = await db.remove_from_watchlist(symbol.upper())
    return {"status": "ok", "removed": removed}


@app.get("/api/indicators")
async def list_indicators():
    """List all available indicators."""
    indicators = []
    for name in indicator_registry.list_indicators():
        ind = indicator_registry.get(name)
        indicators.append(
            {
                "name": ind.name,
                "description": ind.description,
                "required_history_days": ind.required_history_days,
            }
        )
    return {"indicators": indicators}


def run_server():
    """Run the webhook server."""
    settings = get_settings()
    uvicorn.run(
        "stock_sentinel.server.webhook:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=False,
    )


if __name__ == "__main__":
    run_server()
