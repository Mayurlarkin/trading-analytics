from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, ApiKey, Instrument, Trade
from app.services.accounts import create_account
from app.types import UTCDateTime


def make_trade(account: Account, instrument: Instrument, **overrides: object) -> Trade:
    values: dict = {
        "account_id": account.id,
        "instrument_id": instrument.id,
        "ticket": 1,
        "direction": "buy",
        "volume": Decimal("1"),
        "open_time": datetime(2026, 11, 2, 14, 0, tzinfo=UTC),
        "close_time": datetime(2026, 11, 2, 15, 0, tzinfo=UTC),
        "open_price": Decimal("100"),
        "close_price": Decimal("101"),
        "profit": Decimal("1"),
    }
    values.update(overrides)
    return Trade(**values)


@pytest.fixture
def account_and_instrument(db_session: Session) -> tuple[Account, Instrument]:
    account, _ = create_account(db_session, email="db@example.com", label="DB")
    instrument = Instrument(symbol="US30")
    db_session.add(instrument)
    db_session.commit()
    return account, instrument


def test_ticket_is_unique_per_account(db_session, account_and_instrument) -> None:
    account, instrument = account_and_instrument
    db_session.add(make_trade(account, instrument, ticket=5))
    db_session.commit()

    db_session.add(make_trade(account, instrument, ticket=5))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    "bad",
    [
        {"direction": "hold"},
        {"volume": Decimal("0")},
        {"close_time": datetime(2026, 11, 2, 13, 0, tzinfo=UTC)},
    ],
)
def test_check_constraints_are_enforced_by_the_database(
    db_session, account_and_instrument, bad
) -> None:
    account, instrument = account_and_instrument
    db_session.add(make_trade(account, instrument, **bad))
    # SQLite reports an IntegrityError; PyMySQL reports MySQL's CHECK violation (error 3819)
    # as an OperationalError. Both are DBAPIErrors: what matters is the database refused it.
    with pytest.raises(DBAPIError):
        db_session.commit()


def test_deleting_an_account_removes_its_trades_and_keys(
    db_session, account_and_instrument
) -> None:
    account, instrument = account_and_instrument
    db_session.add(make_trade(account, instrument))
    db_session.commit()

    db_session.execute(delete(Account).where(Account.id == account.id))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Trade)) == 0
    assert db_session.scalar(select(func.count()).select_from(ApiKey)) == 0
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1  # shared, kept


def test_an_instrument_in_use_cannot_be_deleted(db_session, account_and_instrument) -> None:
    account, instrument = account_and_instrument
    db_session.add(make_trade(account, instrument))
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(delete(Instrument).where(Instrument.id == instrument.id))
        db_session.commit()


def test_datetimes_round_trip_as_aware_utc(db_session, account_and_instrument) -> None:
    account, instrument = account_and_instrument
    db_session.add(make_trade(account, instrument))
    db_session.commit()
    db_session.expire_all()

    trade = db_session.scalars(select(Trade)).one()
    assert trade.open_time == datetime(2026, 11, 2, 14, 0, tzinfo=UTC)
    assert trade.open_time.utcoffset().total_seconds() == 0


def test_naive_datetimes_are_refused_by_the_column_type() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        UTCDateTime().process_bind_param(datetime(2026, 11, 2, 14, 0), sqlite.dialect())


def test_core_insert_works_with_the_models_table(db_session, account_and_instrument) -> None:
    account, instrument = account_and_instrument
    db_session.execute(
        insert(Trade).values(
            account_id=account.id,
            instrument_id=instrument.id,
            ticket=9,
            direction="sell",
            volume=Decimal("0.5"),
            open_time=datetime(2026, 11, 2, 14, 0, tzinfo=UTC),
            close_time=datetime(2026, 11, 2, 14, 5, tzinfo=UTC),
            open_price=Decimal("1"),
            close_price=Decimal("1"),
            commission=Decimal("0"),
            swap=Decimal("0"),
            profit=Decimal("0"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Trade)) == 1
