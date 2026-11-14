from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, Instrument, Trade
from app.schemas import IngestResult, TradeIn

# Columns copied from the payload onto a Trade (everything except ticket/symbol).
_TRADE_FIELDS = (
    "direction",
    "volume",
    "open_time",
    "close_time",
    "open_price",
    "close_price",
    "sl",
    "tp",
    "commission",
    "swap",
    "profit",
    "strategy_tag",
)


def _get_or_create_instruments(db: Session, symbols: set[str]) -> dict[str, Instrument]:
    found = {
        i.symbol: i
        for i in db.scalars(select(Instrument).where(Instrument.symbol.in_(list(symbols))))
    }
    for symbol in symbols - found.keys():
        instrument = Instrument(symbol=symbol)
        db.add(instrument)
        found[symbol] = instrument
    return found


def _apply(db: Session, account: Account, items: list[TradeIn]) -> IngestResult:
    instruments = _get_or_create_instruments(db, {i.symbol for i in items})
    existing = {
        t.ticket: t
        for t in db.scalars(
            select(Trade).where(
                Trade.account_id == account.id, Trade.ticket.in_([i.ticket for i in items])
            )
        )
    }

    created = updated = unchanged = 0
    for item in items:
        values = {name: getattr(item, name) for name in _TRADE_FIELDS}
        instrument = instruments[item.symbol]
        trade = existing.get(item.ticket)

        if trade is None:
            db.add(
                Trade(account_id=account.id, ticket=item.ticket, instrument=instrument, **values)
            )
            created += 1
            continue

        changed = False
        # A brand-new instrument has no id yet, so it always compares as different.
        if trade.instrument_id != instrument.id:
            trade.instrument = instrument
            changed = True
        for name, value in values.items():
            if getattr(trade, name) != value:
                setattr(trade, name, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    db.commit()
    return IngestResult(received=len(items), created=created, updated=updated, unchanged=unchanged)


def ingest_trades(db: Session, account: Account, items: list[TradeIn]) -> IngestResult:
    """Insert new trades and update changed ones; re-sending identical data is a no-op.

    Idempotency key is (account, ticket). A concurrent request inserting the same row
    trips the unique constraint; we roll back and retry once, which then sees that row.
    """
    for attempt in (1, 2):
        try:
            return _apply(db, account, items)
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
