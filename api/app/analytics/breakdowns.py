from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.analytics.stats import TradeStats, trade_stats
from app.analytics.trade import ClosedTrade

DEFAULT_TIMEZONE = "America/New_York"  # the clock ICT/SMC session ideas are written in
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True, slots=True)
class Group:
    key: str
    stats: TradeStats


@dataclass(frozen=True, slots=True)
class Session:
    """A named part of the day, as hours on the chosen clock: start inclusive, end exclusive.
    A session may wrap past midnight (start 19, end 2 covers 19:00 to 02:00)."""

    name: str
    start_hour: int
    end_hour: int

    def contains(self, hour: int) -> bool:
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


# Default sessions in New York time. They are a starting point; pass your own to match the
# windows your strategy cares about.
DEFAULT_SESSIONS = (
    Session("Asia", 19, 2),
    Session("London", 2, 7),
    Session("New York AM", 7, 12),
    Session("New York PM", 12, 17),
    Session("After hours", 17, 19),
)


def _group_by(
    trades: Iterable[ClosedTrade], key_of: Callable[[ClosedTrade], str]
) -> dict[str, list[ClosedTrade]]:
    groups: dict[str, list[ClosedTrade]] = {}
    for trade in trades:
        groups.setdefault(key_of(trade), []).append(trade)
    return groups


def _in_order(groups: dict[str, list[ClosedTrade]], keys: Sequence[str]) -> list[Group]:
    """Every key in ``keys`` (empty ones included, so charts have no gaps), then any others."""
    ordered = [*keys, *(k for k in groups if k not in keys)]
    return [Group(key, trade_stats(groups.get(key, []))) for key in ordered]


def by_instrument(trades: Iterable[ClosedTrade]) -> list[Group]:
    """One group per symbol, best net result first. Symbols are used as given; pass trades
    through ``canonical_symbol`` first to merge broker spellings (the DB adapter does)."""
    groups = _group_by(trades, lambda t: t.symbol)
    result = [Group(key, trade_stats(items)) for key, items in groups.items()]
    return sorted(result, key=lambda g: (-g.stats.net_profit, g.key))


def by_weekday(trades: Iterable[ClosedTrade], tz: str = DEFAULT_TIMEZONE) -> list[Group]:
    """Grouped by the weekday the trade was opened, on the ``tz`` clock. Always Monday..Sunday."""
    zone = ZoneInfo(tz)
    groups = _group_by(trades, lambda t: WEEKDAYS[t.open_time.astimezone(zone).weekday()])
    return _in_order(groups, WEEKDAYS)


def by_hour(trades: Iterable[ClosedTrade], tz: str = DEFAULT_TIMEZONE) -> list[Group]:
    """Grouped by the hour the trade was opened ("00".."23"), on the ``tz`` clock."""
    zone = ZoneInfo(tz)
    groups = _group_by(trades, lambda t: f"{t.open_time.astimezone(zone).hour:02d}")
    return _in_order(groups, [f"{h:02d}" for h in range(24)])


def by_session(
    trades: Iterable[ClosedTrade],
    tz: str = DEFAULT_TIMEZONE,
    sessions: Sequence[Session] = DEFAULT_SESSIONS,
) -> list[Group]:
    """Grouped by the session the trade was opened in. Hours no session covers go to "Other"."""
    zone = ZoneInfo(tz)

    def session_of(trade: ClosedTrade) -> str:
        hour = trade.open_time.astimezone(zone).hour
        return next((s.name for s in sessions if s.contains(hour)), "Other")

    groups = _group_by(trades, session_of)
    return _in_order(groups, [s.name for s in sessions])
