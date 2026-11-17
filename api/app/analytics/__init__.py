"""Trade analytics: pure functions over closed trades, no database or web code.

Everything here takes plain ``ClosedTrade`` values and returns plain dataclasses, so each
metric can be tested against numbers worked out by hand. ``adapters`` is the only module that
touches the database.
"""

from app.analytics.breakdowns import (
    DEFAULT_SESSIONS,
    Group,
    Session,
    by_hour,
    by_instrument,
    by_session,
    by_weekday,
)
from app.analytics.equity import Drawdown, EquityPoint, equity_curve, max_drawdowns
from app.analytics.stats import Streak, Summary, TradeStats, summarize, trade_stats
from app.analytics.symbols import canonical_symbol
from app.analytics.trade import ClosedTrade

__all__ = [
    "DEFAULT_SESSIONS",
    "ClosedTrade",
    "Drawdown",
    "EquityPoint",
    "Group",
    "Session",
    "Streak",
    "Summary",
    "TradeStats",
    "by_hour",
    "by_instrument",
    "by_session",
    "by_weekday",
    "canonical_symbol",
    "equity_curve",
    "max_drawdowns",
    "summarize",
    "trade_stats",
]
