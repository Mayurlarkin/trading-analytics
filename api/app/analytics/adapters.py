from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.analytics.symbols import canonical_symbol
from app.analytics.trade import ClosedTrade
from app.models import Account, Trade


def to_closed_trade(trade: Trade) -> ClosedTrade:
    return ClosedTrade(
        ticket=trade.ticket,
        symbol=canonical_symbol(trade.instrument.symbol),
        direction=trade.direction,
        open_time=trade.open_time,
        close_time=trade.close_time,
        profit=trade.profit,
        commission=trade.commission,
        swap=trade.swap,
    )


def load_closed_trades(
    db: Session,
    account_id: int,
    *,
    closed_from: datetime | None = None,
    closed_until: datetime | None = None,
) -> list[ClosedTrade]:
    """An account's trades as analytics input. ``closed_from`` is inclusive, ``closed_until``
    exclusive; both must be timezone-aware."""
    query = (
        select(Trade)
        .options(joinedload(Trade.instrument))
        .where(Trade.account_id == account_id)
        .order_by(Trade.close_time, Trade.ticket)
    )
    if closed_from is not None:
        query = query.where(Trade.close_time >= closed_from)
    if closed_until is not None:
        query = query.where(Trade.close_time < closed_until)
    return [to_closed_trade(t) for t in db.scalars(query)]


def balance_before(db: Session, account: Account, moment: datetime | None) -> Decimal:
    """The account balance just before ``moment``: starting balance plus what every trade that
    closed earlier made. With no moment it is simply the starting balance."""
    if moment is None:
        return account.starting_balance
    earlier = db.scalar(
        select(func.coalesce(func.sum(Trade.profit + Trade.commission + Trade.swap), 0)).where(
            Trade.account_id == account.id, Trade.close_time < moment
        )
    )
    return account.starting_balance + Decimal(str(earlier)).quantize(Decimal("0.01"))
