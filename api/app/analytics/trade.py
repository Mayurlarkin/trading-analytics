from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """One finished position, reduced to what the metrics need.

    Times must be timezone-aware. ``net`` is what the trade really made or cost the account:
    profit plus commission plus swap (commission and swap are normally negative).
    """

    ticket: int
    symbol: str
    direction: str
    open_time: datetime
    close_time: datetime
    profit: Decimal
    commission: Decimal = ZERO
    swap: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("trade times must be timezone-aware")

    @property
    def net(self) -> Decimal:
        return self.profit + self.commission + self.swap

    @property
    def holding_time(self) -> timedelta:
        return self.close_time - self.open_time
