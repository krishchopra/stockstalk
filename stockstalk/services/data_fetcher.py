"""Async stock data fetcher using Yahoo Finance API."""

import asyncio
from datetime import datetime, timedelta

import yfinance as yf

from stockstalk.models import HistoricalData, StockData


class StockDataFetcher:
    """Async fetcher for stock data from Yahoo Finance."""

    def _fetch_current_data_sync(self, symbol: str) -> StockData:
        """
        Synchronous implementation for fetching current stock data.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockData object with current stock information
        """
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
            raise ValueError(f"Could not fetch valid price data for {symbol}")

        return StockData(
            symbol=symbol,
            current_price=current_price,
            open_price=open_price if open_price > 0 else previous_close,
            high_price=high_price if high_price > 0 else current_price,
            low_price=low_price if low_price > 0 else current_price,
            volume=volume if volume > 0 else 0,
            previous_close=previous_close,
        )

    def _fetch_historical_data_sync(self, symbol: str, days: int) -> HistoricalData:
        """
        Synchronous implementation for fetching historical stock data.

        Args:
            symbol: Stock ticker symbol
            days: Number of days of historical data to fetch

        Returns:
            HistoricalData object with historical stock information
        """
        ticker = yf.Ticker(symbol)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # Extra buffer

        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            raise ValueError(f"No historical data available for {symbol}")

        # Convert to lists
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

    async def get_current_data(self, symbol: str) -> StockData:
        """
        Fetch current stock data for a symbol asynchronously.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockData object with current stock information

        Raises:
            ValueError: If symbol is invalid or data cannot be fetched
        """
        try:
            return await asyncio.to_thread(self._fetch_current_data_sync, symbol)
        except Exception as e:
            raise ValueError(f"Failed to fetch data for {symbol}: {str(e)}") from e

    async def get_historical_data(self, symbol: str, days: int = 30) -> HistoricalData:
        """
        Fetch historical stock data for a symbol asynchronously.

        Args:
            symbol: Stock ticker symbol
            days: Number of days of historical data to fetch

        Returns:
            HistoricalData object with historical stock information

        Raises:
            ValueError: If symbol is invalid or data cannot be fetched
        """
        try:
            return await asyncio.to_thread(self._fetch_historical_data_sync, symbol, days)
        except Exception as e:
            raise ValueError(f"Failed to fetch historical data for {symbol}: {str(e)}") from e

    async def get_stock_data(
        self, symbol: str, days: int = 30
    ) -> tuple[StockData, HistoricalData]:
        """
        Fetch both current and historical data for a symbol.

        Args:
            symbol: Stock ticker symbol
            days: Number of days of historical data to fetch

        Returns:
            Tuple of (StockData, HistoricalData)
        """
        # Fetch both in parallel
        current_task = self.get_current_data(symbol)
        historical_task = self.get_historical_data(symbol, days)

        current_data, historical_data = await asyncio.gather(
            current_task, historical_task
        )

        return current_data, historical_data
