from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_BATCH_SIZE = 500


class TradeIn(BaseModel):
    """A closed trade as sent by an EA or script.

    Datetimes must carry a timezone offset (e.g. "2026-11-02T14:30:00+00:00"); they are
    stored as UTC. Prices have at most 5 decimals, money at most 2.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticket: int = Field(gt=0, description="Broker position ticket; unique per account")
    symbol: str = Field(min_length=1, max_length=32)
    direction: Literal["buy", "sell"]
    volume: Decimal = Field(gt=0, max_digits=12, decimal_places=4, description="Lots")
    open_time: AwareDatetime
    close_time: AwareDatetime
    open_price: Decimal = Field(gt=0, max_digits=18, decimal_places=5)
    close_price: Decimal = Field(gt=0, max_digits=18, decimal_places=5)
    sl: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=5)
    tp: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=5)
    commission: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    swap: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    profit: Decimal = Field(max_digits=18, decimal_places=2)
    strategy_tag: str | None = Field(default=None, max_length=64)

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalise_symbol(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("direction", mode="before")
    @classmethod
    def _normalise_direction(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("open_time", "close_time")
    @classmethod
    def _drop_microseconds(cls, value: datetime) -> datetime:
        # MySQL DATETIME has second resolution here; normalising keeps re-sends comparable.
        return value.replace(microsecond=0)

    @field_validator("sl", "tp")
    @classmethod
    def _zero_means_unset(cls, value: Decimal | None) -> Decimal | None:
        # MT5 reports "no stop loss / take profit" as 0.
        return None if value is not None and value == 0 else value

    @model_validator(mode="after")
    def _close_not_before_open(self) -> "TradeIn":
        if self.close_time < self.open_time:
            raise ValueError("close_time must not be before open_time")
        return self


class TradesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trades: list[TradeIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    @model_validator(mode="after")
    def _unique_tickets(self) -> "TradesIn":
        tickets = [t.ticket for t in self.trades]
        if len(tickets) != len(set(tickets)):
            raise ValueError("duplicate ticket numbers in one batch")
        return self


class IngestResult(BaseModel):
    received: int
    created: int
    updated: int
    unchanged: int
