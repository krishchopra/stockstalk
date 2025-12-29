"""Async stock data fetcher using Yahoo Finance API."""

import asyncio
import logging
from datetime import datetime, timedelta

import yfinance as yf

from stockstalk.models import HistoricalData, StockData

logger = logging.getLogger(__name__)

# Exchange suffixes to try when a symbol isn't found
# Order matters - most common first
EXCHANGE_SUFFIXES = [
    "",       # US (NYSE, NASDAQ) - no suffix
    ".TO",    # Toronto Stock Exchange
    ".V",     # TSX Venture Exchange
    ".L",     # London Stock Exchange
    ".AX",    # Australian Stock Exchange
    ".DE",    # Deutsche Börse (Frankfurt)
    ".PA",    # Euronext Paris
    ".MI",    # Borsa Italiana (Milan)
    ".AS",    # Euronext Amsterdam
    ".HK",    # Hong Kong Stock Exchange
    ".T",     # Tokyo Stock Exchange
    ".NS",    # National Stock Exchange of India
    ".BO",    # Bombay Stock Exchange
]


class StockDataFetcher:
    """Async fetcher for stock data from Yahoo Finance."""

    def _try_fetch_current_data_sync(self, symbol: str) -> StockData | None:
        """
        Try to fetch current data for a single symbol variant.
        Returns None if fetch fails.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Get current price from fast_info or info
            try:
                current_price = ticker.fast_info.last_price
            except (AttributeError, KeyError):
                current_price = info.get("currentPrice", info.get("regularMarketPrice", 0))

            # Get other data
            previous_close = info.get("previousClose", info.get("regularMarketPreviousClose", 0))
            open_price = info.get("open", info.get("regularMarketOpen", 0))
            high_price = info.get("dayHigh", info.get("regularMarketDayHigh", 0))
            low_price = info.get("dayLow", info.get("regularMarketDayLow", 0))
            volume = info.get("volume", info.get("regularMarketVolume", 0))

            # Validate we got meaningful data
            if current_price == 0 or previous_close == 0:
                return None

            return StockData(
                symbol=symbol,
                current_price=current_price,
                open_price=open_price if open_price > 0 else previous_close,
                high_price=high_price if high_price > 0 else current_price,
                low_price=low_price if low_price > 0 else current_price,
                volume=volume if volume > 0 else 0,
                previous_close=previous_close,
            )
        except Exception:
            return None

    def _try_fetch_historical_data_sync(self, symbol: str, days: int) -> HistoricalData | None:
        """
        Try to fetch historical data for a single symbol variant.
        Returns None if fetch fails.
        """
        try:
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days + 10)

            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                return None

            dates = [date.to_pydatetime() for date in hist.index]
            open_prices = hist["Open"].tolist()
            high_prices = hist["High"].tolist()
            low_prices = hist["Low"].tolist()
            close_prices = hist["Close"].tolist()
            volumes = hist["Volume"].astype(int).tolist()

            return HistoricalData(
                symbol=symbol,
                dates=dates,
                open_prices=open_prices,
                high_prices=high_prices,
                low_prices=low_prices,
                close_prices=close_prices,
                volumes=volumes,
            )
        except Exception:
            return None

    def _fetch_current_data_sync(self, symbol: str) -> StockData:
        """
        Fetch current stock data, trying multiple exchanges if needed.
        """
        base_symbol = symbol.upper().split(".")[0]  # Remove any existing suffix
        
        # Try each exchange suffix
        for suffix in EXCHANGE_SUFFIXES:
            full_symbol = f"{base_symbol}{suffix}"
            result = self._try_fetch_current_data_sync(full_symbol)
            if result is not None:
                if suffix:
                    logger.info(f"found {base_symbol} on exchange: {suffix.replace('.', '')}")
                return result
        
        raise ValueError(f"could not find {symbol} on any exchange")

    def _fetch_historical_data_sync(self, symbol: str, days: int) -> HistoricalData:
        """
        Fetch historical stock data, trying multiple exchanges if needed.
        """
        base_symbol = symbol.upper().split(".")[0]  # Remove any existing suffix
        
        # Try each exchange suffix
        for suffix in EXCHANGE_SUFFIXES:
            full_symbol = f"{base_symbol}{suffix}"
            result = self._try_fetch_historical_data_sync(full_symbol, days)
            if result is not None:
                return result
        
        raise ValueError(f"no historical data for {symbol} on any exchange")

    async def get_current_data(self, symbol: str) -> StockData:
        """
        Fetch current stock data for a symbol asynchronously.
        Tries multiple exchanges if the symbol isn't found.
        """
        try:
            return await asyncio.to_thread(self._fetch_current_data_sync, symbol)
        except Exception as e:
            raise ValueError(f"failed to fetch data for {symbol}: {str(e)}") from e

    async def get_historical_data(self, symbol: str, days: int = 30) -> HistoricalData:
        """
        Fetch historical stock data for a symbol asynchronously.
        Tries multiple exchanges if the symbol isn't found.
        """
        try:
            return await asyncio.to_thread(self._fetch_historical_data_sync, symbol, days)
        except Exception as e:
            raise ValueError(f"failed to fetch historical data for {symbol}: {str(e)}") from e

    async def get_stock_data(self, symbol: str, days: int = 30) -> tuple[StockData, HistoricalData]:
        """
        Fetch both current and historical data for a symbol.
        Tries multiple exchanges if the symbol isn't found.
        """
        # First find which exchange has the symbol
        base_symbol = symbol.upper().split(".")[0]
        
        # Try to find the symbol on any exchange
        found_symbol = None
        for suffix in EXCHANGE_SUFFIXES:
            full_symbol = f"{base_symbol}{suffix}"
            result = await asyncio.to_thread(self._try_fetch_current_data_sync, full_symbol)
            if result is not None:
                found_symbol = full_symbol
                if suffix:
                    logger.info(f"found {base_symbol} on exchange: {suffix.replace('.', '')}")
                break
        
        if not found_symbol:
            raise ValueError(f"could not find {symbol} on any exchange")
        
        # Now fetch both current and historical with the found symbol
        current_task = self.get_current_data(found_symbol)
        historical_task = self.get_historical_data(found_symbol, days)

        current_data, historical_data = await asyncio.gather(current_task, historical_task)

        return current_data, historical_data
