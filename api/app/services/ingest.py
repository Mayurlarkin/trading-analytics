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


# Keep IN (...) lists a sensible size when importing thousands of trades at once.
_LOOKUP_CHUNK = 500


def _existing_trades(db: Session, account: Account, tickets: list[int]) -> dict[int, Trade]:
    found: dict[int, Trade] = {}
    for start in range(0, len(tickets), _LOOKUP_CHUNK):
        chunk = tickets[start : start + _LOOKUP_CHUNK]
        for trade in db.scalars(
            select(Trade).where(Trade.account_id == account.id, Trade.ticket.in_(chunk))
        ):
            found[trade.ticket] = trade
    return found


def _apply(db: Session, account: Account, items: list[TradeIn], *, commit: bool) -> IngestResult:
    instruments = _get_or_create_instruments(db, {i.symbol for i in items})
    existing = _existing_trades(db, account, [i.ticket for i in items])

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
            # A tag is optional metadata: a sender that has none (e.g. a report import) must
            # not erase one that an EA already set. Other None values (sl/tp) really mean unset.
            if name == "strategy_tag" and value is None:
                continue
            if getattr(trade, name) != value:
                setattr(trade, name, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    # flush() sends the SQL (so constraint errors surface) without making it permanent.
    db.commit() if commit else db.flush()
    return IngestResult(received=len(items), created=created, updated=updated, unchanged=unchanged)


def ingest_trades(
    db: Session, account: Account, items: list[TradeIn], *, commit: bool = True
) -> IngestResult:
    """Insert new trades and update changed ones; re-sending identical data is a no-op.

    Idempotency key is (account, ticket). A concurrent request inserting the same row
    trips the unique constraint; we roll back and retry once, which then sees that row.
    With commit=False the changes are only flushed; the caller decides whether to keep them
    (used for dry runs).
    """
    for attempt in (1, 2):
        try:
            return _apply(db, account, items, commit=commit)
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
