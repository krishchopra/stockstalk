"""Database storage for Stock Sentinel."""

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from stock_sentinel.config.settings import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


class AlertRecordORM(Base):
    """ORM model for alert records."""

    __tablename__ = "alert_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), index=True)
    indicator: Mapped[str] = mapped_column(String(50), index=True)
    signal: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    sent_to: Mapped[str] = mapped_column(Text)  # Comma-separated phone numbers
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WatchlistItemORM(Base):
    """ORM model for watchlist items."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PhoneNumberORM(Base):
    """ORM model for phone numbers to notify."""

    __tablename__ = "phone_numbers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Pydantic models for API/business logic
class AlertRecord(BaseModel):
    """Alert record data model."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    symbol: str
    indicator: str
    signal: str
    value: float
    message: str
    sent_to: str
    created_at: datetime = datetime.now()


class WatchlistItem(BaseModel):
    """Watchlist item data model."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    symbol: str
    enabled: bool = True
    notes: str | None = None
    added_at: datetime = datetime.now()


class PhoneNumber(BaseModel):
    """Phone number data model."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    phone_number: str
    label: str | None = None
    enabled: bool = True
    added_at: datetime = datetime.now()


class Database:
    """Async database manager for Stock Sentinel."""

    def __init__(self, database_url: str | None = None):
        """
        Initialize database.

        Args:
            database_url: Database connection URL
        """
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.engine = create_async_engine(self.database_url, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init(self) -> None:
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()

    # Alert Records
    async def add_alert(self, alert: AlertRecord) -> AlertRecord:
        """Add an alert record."""
        async with self.session_factory() as session:
            orm_obj = AlertRecordORM(
                symbol=alert.symbol,
                indicator=alert.indicator,
                signal=alert.signal,
                value=alert.value,
                message=alert.message,
                sent_to=alert.sent_to,
                created_at=alert.created_at,
            )
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)
            return AlertRecord.model_validate(orm_obj)

    async def get_recent_alerts(
        self, symbol: str, indicator: str, minutes: int = 60
    ) -> list[AlertRecord]:
        """Get recent alerts for a symbol/indicator combo."""
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            result = await session.execute(
                select(AlertRecordORM)
                .where(AlertRecordORM.symbol == symbol)
                .where(AlertRecordORM.indicator == indicator)
                .where(AlertRecordORM.created_at >= cutoff)
                .order_by(AlertRecordORM.created_at.desc())
            )
            return [AlertRecord.model_validate(row) for row in result.scalars().all()]

    async def get_alerts_count_in_hour(self) -> int:
        """Get count of alerts in the last hour."""
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(hours=1)
            result = await session.execute(
                select(AlertRecordORM).where(AlertRecordORM.created_at >= cutoff)
            )
            return len(result.scalars().all())

    # Watchlist
    async def add_to_watchlist(self, symbol: str, notes: str | None = None) -> WatchlistItem:
        """Add a symbol to the watchlist."""
        async with self.session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(WatchlistItemORM).where(WatchlistItemORM.symbol == symbol.upper())
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.enabled = True
                if notes:
                    existing.notes = notes
                await session.commit()
                await session.refresh(existing)
                return WatchlistItem.model_validate(existing)

            orm_obj = WatchlistItemORM(
                symbol=symbol.upper(),
                enabled=True,
                notes=notes,
            )
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)
            return WatchlistItem.model_validate(orm_obj)

    async def remove_from_watchlist(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist (disable it)."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(WatchlistItemORM).where(WatchlistItemORM.symbol == symbol.upper())
            )
            item = result.scalar_one_or_none()
            if item:
                item.enabled = False
                await session.commit()
                return True
            return False

    async def get_watchlist(self, enabled_only: bool = True) -> list[WatchlistItem]:
        """Get all watchlist items."""
        async with self.session_factory() as session:
            query = select(WatchlistItemORM)
            if enabled_only:
                query = query.where(WatchlistItemORM.enabled.is_(True))
            result = await session.execute(query.order_by(WatchlistItemORM.symbol))
            return [WatchlistItem.model_validate(row) for row in result.scalars().all()]

    # Phone Numbers
    async def add_phone_number(self, phone_number: str, label: str | None = None) -> PhoneNumber:
        """Add a phone number for notifications."""
        async with self.session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(PhoneNumberORM).where(PhoneNumberORM.phone_number == phone_number)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.enabled = True
                if label:
                    existing.label = label
                await session.commit()
                await session.refresh(existing)
                return PhoneNumber.model_validate(existing)

            orm_obj = PhoneNumberORM(
                phone_number=phone_number,
                label=label,
                enabled=True,
            )
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)
            return PhoneNumber.model_validate(orm_obj)

    async def remove_phone_number(self, phone_number: str) -> bool:
        """Remove a phone number (disable it)."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(PhoneNumberORM).where(PhoneNumberORM.phone_number == phone_number)
            )
            item = result.scalar_one_or_none()
            if item:
                item.enabled = False
                await session.commit()
                return True
            return False

    async def get_phone_numbers(self, enabled_only: bool = True) -> list[PhoneNumber]:
        """Get all phone numbers."""
        async with self.session_factory() as session:
            query = select(PhoneNumberORM)
            if enabled_only:
                query = query.where(PhoneNumberORM.enabled.is_(True))
            result = await session.execute(query.order_by(PhoneNumberORM.phone_number))
            return [PhoneNumber.model_validate(row) for row in result.scalars().all()]


# Global database instance
_database: Database | None = None


async def init_database(database_url: str | None = None) -> Database:
    """Initialize the global database instance."""
    global _database
    _database = Database(database_url)
    await _database.init()
    return _database


def get_database() -> Database:
    """Get the global database instance."""
    if _database is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _database
