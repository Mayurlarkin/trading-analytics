from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.types import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


# BIGINT AUTO_INCREMENT on MySQL; plain INTEGER on SQLite (which only auto-increments INTEGER).
BigIntPk = BigInteger().with_variant(Integer(), "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    # Nullable: seeded/demo users have no login. Real sign-up arrives in Phase 3.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_accounts_user_id_label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100))
    broker: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    starting_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="account")


class ApiKey(Base):
    """Credential used by an EA/script to post trades to one account.

    Only a SHA-256 hash is stored; the plaintext key is shown once at creation.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    # First characters of the key, so a human can tell keys apart (and revoke one).
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    account: Mapped[Account] = relationship(back_populates="api_keys")


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    asset_class: Mapped[str | None] = mapped_column(String(20))


class Trade(Base):
    """One closed trade (a position that has been fully closed)."""

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("account_id", "ticket", name="uq_trades_account_id_ticket"),
        CheckConstraint("direction IN ('buy', 'sell')", name="direction_valid"),
        CheckConstraint("volume > 0", name="volume_positive"),
        CheckConstraint("close_time >= open_time", name="close_not_before_open"),
        Index("ix_trades_account_id_close_time", "account_id", "close_time"),
        Index("ix_trades_account_id_instrument_id", "account_id", "instrument_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    # The broker/platform's own trade identifier (MT5 position ticket).
    ticket: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(4))
    volume: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    open_time: Mapped[datetime] = mapped_column(UTCDateTime())
    close_time: Mapped[datetime] = mapped_column(UTCDateTime())
    open_price: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    sl: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    tp: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    swap: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    profit: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    strategy_tag: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    instrument: Mapped[Instrument] = relationship()
