"""Async SQLite database layer using SQLAlchemy."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class AlertRecord(Base):
    """Record of sent alerts for cooldown tracking."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    indicator = Column(String(50), nullable=False, index=True)
    message = Column(Text)
    priority = Column(String(20))
    sent_to = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class WatchlistRecord(Base):
    """Runtime watchlist additions (overlays config.json)."""

    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), unique=True, nullable=False)
    enabled_indicators = Column(Text)  # JSON array
    custom_params = Column(Text)  # JSON object
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PhoneNumberRecord(Base):
    """Phone numbers for notifications."""

    __tablename__ = "phone_numbers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False)
    label = Column(String(100))
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Database:
    """Async database interface."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./stockstalk.db") -> None:
        """
        Initialize database connection.

        Args:
            database_url: SQLAlchemy async database URL
        """
        self.database_url = database_url
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def init(self) -> None:
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()

    # Alert methods
    async def add_alert(
        self,
        symbol: str,
        indicator: str,
        message: str,
        priority: str,
        sent_to: str,
    ) -> AlertRecord:
        """Record a sent alert."""
        async with self.async_session() as session:
            alert = AlertRecord(
                symbol=symbol.upper(),
                indicator=indicator,
                message=message,
                priority=priority,
                sent_to=sent_to,
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)
            return alert

    async def get_recent_alert(
        self,
        symbol: str,
        indicator: str,
        cooldown_minutes: int,
    ) -> AlertRecord | None:
        """Check if a recent alert exists within cooldown period."""
        cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRecord)
                .where(AlertRecord.symbol == symbol.upper())
                .where(AlertRecord.indicator == indicator)
                .where(AlertRecord.created_at >= cutoff)
                .order_by(AlertRecord.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_alerts_count_since(self, minutes: int) -> int:
        """Get count of alerts sent in the last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRecord).where(AlertRecord.created_at >= cutoff)
            )
            return len(result.scalars().all())

    # Watchlist methods
    async def add_to_watchlist(
        self,
        symbol: str,
        enabled_indicators: list[str] | None = None,
        custom_params: dict[str, Any] | None = None,
    ) -> WatchlistRecord:
        """Add a symbol to the watchlist."""
        async with self.async_session() as session:
            record = WatchlistRecord(
                symbol=symbol.upper(),
                enabled_indicators=json.dumps(enabled_indicators) if enabled_indicators else None,
                custom_params=json.dumps(custom_params) if custom_params else None,
                enabled=True,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_watchlist(self, enabled_only: bool = True) -> list[WatchlistRecord]:
        """Get all watchlist items."""
        async with self.async_session() as session:
            query = select(WatchlistRecord)
            if enabled_only:
                query = query.where(WatchlistRecord.enabled == True)  # noqa: E712
            result = await session.execute(query.order_by(WatchlistRecord.symbol))
            return list(result.scalars().all())

    async def remove_from_watchlist(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WatchlistRecord).where(WatchlistRecord.symbol == symbol.upper())
            )
            record = result.scalar_one_or_none()
            if record:
                await session.delete(record)
                await session.commit()
                return True
            return False

    # Phone number methods
    async def add_phone_number(self, phone_number: str, label: str | None = None) -> PhoneNumberRecord:
        """Add a phone number for notifications."""
        async with self.async_session() as session:
            record = PhoneNumberRecord(
                phone_number=phone_number,
                label=label,
                enabled=True,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_phone_numbers(self, enabled_only: bool = True) -> list[PhoneNumberRecord]:
        """Get all phone numbers."""
        async with self.async_session() as session:
            query = select(PhoneNumberRecord)
            if enabled_only:
                query = query.where(PhoneNumberRecord.enabled == True)  # noqa: E712
            result = await session.execute(query)
            return list(result.scalars().all())

    async def remove_phone_number(self, phone_number: str) -> bool:
        """Remove a phone number."""
        async with self.async_session() as session:
            result = await session.execute(
                select(PhoneNumberRecord).where(PhoneNumberRecord.phone_number == phone_number)
            )
            record = result.scalar_one_or_none()
            if record:
                await session.delete(record)
                await session.commit()
                return True
            return False


# Global database instance
_database: Database | None = None


async def init_database(database_url: str = "sqlite+aiosqlite:///./stockstalk.db") -> Database:
    """Initialize and return the global database instance."""
    global _database
    _database = Database(database_url)
    await _database.init()
    return _database


def get_database() -> Database:
    """Get the global database instance."""
    if _database is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _database

