from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, false, func, select
from sqlalchemy.orm import Session, joinedload

from app.analytics import (
    DEFAULT_SESSIONS,
    by_hour,
    by_instrument,
    by_session,
    by_weekday,
    canonical_symbol,
    equity_curve,
    summarize,
)
from app.analytics.adapters import balance_before, load_closed_trades
from app.analytics.breakdowns import DEFAULT_TIMEZONE
from app.db import get_db
from app.deps import get_current_user, get_owned_account
from app.models import Account, Instrument, Trade, User
from app.schemas_analytics import (
    AccountOut,
    BreakdownOut,
    EquityCurveOut,
    EquityPointOut,
    GroupOut,
    SummaryOut,
    TradeOut,
    TradesPage,
    _money,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@dataclass(frozen=True)
class Period:
    closed_from: datetime | None
    closed_until: datetime | None


def get_period(
    closed_from: Annotated[
        datetime | None,
        Query(description="Only trades closed at or after this time (must include a timezone)"),
    ] = None,
    closed_until: Annotated[
        datetime | None,
        Query(description="Only trades closed before this time (must include a timezone)"),
    ] = None,
) -> Period:
    for name, value in (("closed_from", closed_from), ("closed_until", closed_until)):
        if value is not None and value.tzinfo is None:
            raise HTTPException(
                status_code=422,
                detail=f"{name} needs a timezone, e.g. 2026-03-01T00:00:00Z or +02:00",
            )
    if closed_from and closed_until and closed_from >= closed_until:
        raise HTTPException(status_code=422, detail="closed_from must be before closed_until")
    return Period(closed_from, closed_until)


def _valid_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"unknown timezone: {tz}") from exc
    return tz


def _account_rows(db: Session, user: User, account_id: int | None = None):  # type: ignore[no-untyped-def]
    query = (
        select(Account, func.count(Trade.id), func.max(Trade.close_time))
        .outerjoin(Trade, Trade.account_id == Account.id)
        .where(Account.user_id == user.id)
        .group_by(Account.id)
        .order_by(Account.id)
    )
    if account_id is not None:
        query = query.where(Account.id == account_id)
    return db.execute(query).all()


def _account_out(account: Account, trade_count: int, last_close: datetime | None) -> AccountOut:
    return AccountOut(
        id=account.id,
        label=account.label,
        broker=account.broker,
        currency=account.currency,
        starting_balance=account.starting_balance,
        is_demo=account.is_demo,
        server_timezone=account.server_timezone,
        trade_count=trade_count,
        last_close_time=last_close,
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[AccountOut]:
    return [_account_out(*row) for row in _account_rows(db, user)]


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account: Account = Depends(get_owned_account),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    (row,) = _account_rows(db, user, account.id)
    return _account_out(*row)


@router.get("/{account_id}/summary", response_model=SummaryOut)
def summary(
    account: Account = Depends(get_owned_account),
    period: Period = Depends(get_period),
    db: Session = Depends(get_db),
) -> SummaryOut:
    """Performance statistics for the account, optionally limited to a period.

    With ``closed_from`` the starting balance is the balance at that moment (the account's
    starting balance plus everything that closed earlier), so drawdown and return are correct
    for the period."""
    trades = load_closed_trades(
        db, account.id, closed_from=period.closed_from, closed_until=period.closed_until
    )
    opening = balance_before(db, account, period.closed_from)
    return SummaryOut.of(
        summarize(trades, opening),
        currency=account.currency,
        closed_from=period.closed_from,
        closed_until=period.closed_until,
    )


@router.get("/{account_id}/equity-curve", response_model=EquityCurveOut)
def equity(
    account: Account = Depends(get_owned_account),
    period: Period = Depends(get_period),
    db: Session = Depends(get_db),
) -> EquityCurveOut:
    """The balance after each closed trade, with the running peak and drawdown."""
    trades = load_closed_trades(
        db, account.id, closed_from=period.closed_from, closed_until=period.closed_until
    )
    opening = balance_before(db, account, period.closed_from)
    return EquityCurveOut(
        currency=account.currency,
        starting_balance=_money(opening),  # type: ignore[arg-type]
        points=[EquityPointOut.of(p) for p in equity_curve(trades, opening)],
    )


@router.get("/{account_id}/breakdown", response_model=BreakdownOut)
def breakdown(
    by: Annotated[Literal["instrument", "session", "weekday", "hour"], Query()],
    account: Account = Depends(get_owned_account),
    period: Period = Depends(get_period),
    tz: Annotated[
        str,
        Query(description="Clock for session, weekday and hour (an IANA name, e.g. Europe/London)"),
    ] = DEFAULT_TIMEZONE,
    db: Session = Depends(get_db),
) -> BreakdownOut:
    """Statistics grouped by instrument, session, weekday or hour of opening."""
    _valid_timezone(tz)
    trades = load_closed_trades(
        db, account.id, closed_from=period.closed_from, closed_until=period.closed_until
    )
    if by == "instrument":
        groups = by_instrument(trades)
    elif by == "session":
        groups = by_session(trades, tz, DEFAULT_SESSIONS)
    elif by == "weekday":
        groups = by_weekday(trades, tz)
    else:
        groups = by_hour(trades, tz)
    return BreakdownOut(
        by=by,
        timezone=None if by == "instrument" else tz,
        currency=account.currency,
        groups=[GroupOut.of(g) for g in groups],
    )


_NET = Trade.profit + Trade.commission + Trade.swap
_SORT_COLUMNS = {
    "close_time": Trade.close_time,
    "open_time": Trade.open_time,
    "profit": Trade.profit,
    "net": _NET,
}


def _trade_out(trade: Trade) -> TradeOut:
    return TradeOut(
        ticket=trade.ticket,
        symbol=trade.instrument.symbol,
        instrument=canonical_symbol(trade.instrument.symbol),
        direction=trade.direction,  # type: ignore[arg-type]
        volume=trade.volume,
        open_time=trade.open_time,
        close_time=trade.close_time,
        open_price=trade.open_price,
        close_price=trade.close_price,
        sl=trade.sl,
        tp=trade.tp,
        commission=trade.commission,
        swap=trade.swap,
        profit=trade.profit,
        net=trade.profit + trade.commission + trade.swap,
        strategy_tag=trade.strategy_tag,
    )


def _instrument_ids(db: Session, account: Account, name: str) -> list[int]:
    """Ids of this account's instruments that go by the common name (``NAS100`` finds
    ``T100.IFX_M``)."""
    wanted = canonical_symbol(name)
    rows = db.execute(
        select(Instrument.id, Instrument.symbol)
        .join(Trade, Trade.instrument_id == Instrument.id)
        .where(Trade.account_id == account.id)
        .distinct()
    )
    return [i for i, symbol in rows if canonical_symbol(symbol) == wanted]


@router.get("/{account_id}/trades", response_model=TradesPage)
def list_trades(
    account: Account = Depends(get_owned_account),
    period: Period = Depends(get_period),
    symbol: Annotated[
        str | None, Query(description="Instrument, by common or broker name (NAS100 or T100.IFX_M)")
    ] = None,
    direction: Annotated[Literal["buy", "sell"] | None, Query()] = None,
    result: Annotated[
        Literal["win", "loss", "breakeven"] | None,
        Query(description="By net result: above, below or exactly zero"),
    ] = None,
    sort: Annotated[Literal["close_time", "open_time", "profit", "net"], Query()] = "close_time",
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> TradesPage:
    """The account's trades, newest first by default, with filters and paging."""
    query: Select = select(Trade).where(Trade.account_id == account.id)
    if period.closed_from is not None:
        query = query.where(Trade.close_time >= period.closed_from)
    if period.closed_until is not None:
        query = query.where(Trade.close_time < period.closed_until)
    if direction is not None:
        query = query.where(Trade.direction == direction)
    if result == "win":
        query = query.where(_NET > 0)
    elif result == "loss":
        query = query.where(_NET < 0)
    elif result == "breakeven":
        query = query.where(_NET == 0)
    if symbol is not None:
        ids = _instrument_ids(db, account, symbol)
        query = query.where(Trade.instrument_id.in_(ids)) if ids else query.where(false())

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    column = _SORT_COLUMNS[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    page = (
        query.options(joinedload(Trade.instrument))
        .order_by(ordering, Trade.id.asc() if order == "asc" else Trade.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return TradesPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[_trade_out(t) for t in db.scalars(page)],
    )
