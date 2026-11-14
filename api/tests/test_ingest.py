from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApiKey, Instrument, Trade
from app.schemas import MAX_BATCH_SIZE
from app.services.accounts import create_account

URL = "/ingest/trades"


def post(client: TestClient, headers: dict[str, str], *trades: dict):
    return client.post(URL, json={"trades": list(trades)}, headers=headers)


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- authentication -------------------------------------------------------------------


def test_missing_api_key_is_rejected(client: TestClient, trade_payload) -> None:
    response = client.post(URL, json={"trades": [trade_payload()]})
    assert response.status_code == 401


def test_unknown_api_key_is_rejected(client: TestClient, trade_payload) -> None:
    response = post(client, {"X-API-Key": "ta_not-a-real-key"}, trade_payload())
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid or missing API key"}


def test_revoked_api_key_is_rejected(client, db_session, auth_headers, trade_payload) -> None:
    key = db_session.scalars(select(ApiKey)).one()
    key.revoked_at = datetime.now(UTC)
    db_session.commit()
    assert post(client, auth_headers, trade_payload()).status_code == 401


# --- create / idempotency / update ----------------------------------------------------


def test_creates_trades_and_stores_values_exactly(
    client, db_session, auth_headers, account_and_key, trade_payload
) -> None:
    response = post(
        client,
        auth_headers,
        trade_payload(ticket=1, open_price=1.1, close_price=1.12345, profit=-12.3),
        trade_payload(ticket=2, symbol="xauusd", direction="SELL"),
    )
    assert response.status_code == 200
    assert response.json() == {"received": 2, "created": 2, "updated": 0, "unchanged": 0}

    first = db_session.scalars(select(Trade).where(Trade.ticket == 1)).one()
    assert first.account_id == account_and_key[0].id
    assert first.open_price == Decimal("1.1")
    assert first.close_price == Decimal("1.12345")
    assert first.profit == Decimal("-12.30")
    assert first.commission == Decimal("-3.50")
    assert first.strategy_tag == "ict-sweep"

    second = db_session.scalars(select(Trade).where(Trade.ticket == 2)).one()
    assert second.direction == "sell"
    assert second.instrument.symbol == "XAUUSD"


def test_resending_identical_trades_changes_nothing(
    client, db_session, auth_headers, trade_payload
) -> None:
    batch = [trade_payload(ticket=1), trade_payload(ticket=2)]
    post(client, auth_headers, *batch)
    response = post(client, auth_headers, *batch)

    assert response.json() == {"received": 2, "created": 0, "updated": 0, "unchanged": 2}
    assert count(db_session, Trade) == 2


def test_changed_trade_is_updated_in_place(client, db_session, auth_headers, trade_payload) -> None:
    post(client, auth_headers, trade_payload(ticket=1, profit="10.00"))
    response = post(client, auth_headers, trade_payload(ticket=1, profit="25.50"))

    assert response.json()["updated"] == 1
    assert count(db_session, Trade) == 1
    assert db_session.scalars(select(Trade)).one().profit == Decimal("25.50")


def test_mixed_batch_reports_each_outcome(client, auth_headers, trade_payload) -> None:
    post(client, auth_headers, trade_payload(ticket=1), trade_payload(ticket=2))
    response = post(
        client,
        auth_headers,
        trade_payload(ticket=1),  # unchanged
        trade_payload(ticket=2, profit="1.00"),  # updated
        trade_payload(ticket=3),  # created
    )
    assert response.json() == {"received": 3, "created": 1, "updated": 1, "unchanged": 1}


def test_changing_the_symbol_moves_the_trade_to_another_instrument(
    client, db_session, auth_headers, trade_payload
) -> None:
    post(client, auth_headers, trade_payload(ticket=1, symbol="US30"))
    response = post(client, auth_headers, trade_payload(ticket=1, symbol="NAS100"))

    assert response.json()["updated"] == 1
    assert db_session.scalars(select(Trade)).one().instrument.symbol == "NAS100"


# --- normalisation --------------------------------------------------------------------


def test_instruments_are_shared_and_case_insensitive(
    client, db_session, auth_headers, trade_payload
) -> None:
    post(
        client,
        auth_headers,
        trade_payload(ticket=1, symbol="us30"),
        trade_payload(ticket=2, symbol=" US30 "),
    )
    post(client, auth_headers, trade_payload(ticket=3, symbol="US30"))
    assert [i.symbol for i in db_session.scalars(select(Instrument))] == ["US30"]


def test_times_with_an_offset_are_stored_as_utc(
    client, db_session, auth_headers, trade_payload
) -> None:
    post(
        client,
        auth_headers,
        trade_payload(
            open_time="2026-11-02T16:00:00+02:00", close_time="2026-11-02T17:30:00+02:00"
        ),
    )
    trade = db_session.scalars(select(Trade)).one()
    assert trade.open_time == datetime(2026, 11, 2, 14, 0, tzinfo=UTC)
    assert trade.close_time == datetime(2026, 11, 2, 15, 30, tzinfo=UTC)
    assert trade.open_time.tzinfo is not None


def test_fractional_seconds_are_dropped_so_resends_stay_unchanged(
    client, auth_headers, trade_payload
) -> None:
    trade = trade_payload(open_time="2026-11-02T14:30:00.123456+00:00")
    post(client, auth_headers, trade)
    assert post(client, auth_headers, trade).json()["unchanged"] == 1


def test_zero_stop_loss_and_take_profit_mean_unset(
    client, db_session, auth_headers, trade_payload
) -> None:
    post(client, auth_headers, trade_payload(sl=0, tp="0.0"))
    trade = db_session.scalars(select(Trade)).one()
    assert trade.sl is None
    assert trade.tp is None


# --- account isolation ----------------------------------------------------------------


def test_same_ticket_in_two_accounts_are_independent_trades(
    client, db_session, auth_headers, account_and_key, trade_payload
) -> None:
    other_account, other_key = create_account(db_session, email="other@example.com", label="Other")

    post(client, auth_headers, trade_payload(ticket=7, profit="10.00"))
    response = post(client, {"X-API-Key": other_key}, trade_payload(ticket=7, profit="99.00"))

    assert response.json()["created"] == 1
    trades = {t.account_id: t.profit for t in db_session.scalars(select(Trade))}
    assert trades == {account_and_key[0].id: Decimal("10.00"), other_account.id: Decimal("99.00")}


# --- validation -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "why"),
    [
        ({"open_time": "2026-11-02T14:30:00"}, "naive datetime"),
        ({"close_time": "2026-11-02T14:00:00+00:00"}, "close before open"),
        ({"direction": "hold"}, "bad direction"),
        ({"volume": "0"}, "zero volume"),
        ({"volume": "-1"}, "negative volume"),
        ({"open_price": "0"}, "zero price"),
        ({"open_price": "1.123456"}, "too many price decimals"),
        ({"profit": "1.234"}, "too many money decimals"),
        ({"ticket": 0}, "non-positive ticket"),
        ({"symbol": ""}, "empty symbol"),
        ({"strategy_tag": "x" * 65}, "tag too long"),
        ({"unexpected": "field"}, "unknown field"),
    ],
)
def test_invalid_trades_are_rejected_and_nothing_is_saved(
    client, db_session, auth_headers, trade_payload, override, why
) -> None:
    response = post(client, auth_headers, trade_payload(**override))
    assert response.status_code == 422, why
    assert count(db_session, Trade) == 0


def test_one_bad_trade_rejects_the_whole_batch(
    client, db_session, auth_headers, trade_payload
) -> None:
    response = post(
        client, auth_headers, trade_payload(ticket=1), trade_payload(ticket=2, volume=0)
    )
    assert response.status_code == 422
    assert count(db_session, Trade) == 0


def test_empty_batch_is_rejected(client, auth_headers) -> None:
    assert client.post(URL, json={"trades": []}, headers=auth_headers).status_code == 422


def test_oversized_batch_is_rejected(client, auth_headers, trade_payload) -> None:
    batch = [trade_payload(ticket=n) for n in range(1, MAX_BATCH_SIZE + 2)]
    assert post(client, auth_headers, *batch).status_code == 422


def test_duplicate_tickets_in_one_batch_are_rejected(client, auth_headers, trade_payload) -> None:
    response = post(client, auth_headers, trade_payload(ticket=5), trade_payload(ticket=5))
    assert response.status_code == 422


def test_largest_allowed_batch_succeeds(client, db_session, auth_headers, trade_payload) -> None:
    batch = [trade_payload(ticket=n) for n in range(1, MAX_BATCH_SIZE + 1)]
    response = post(client, auth_headers, *batch)
    assert response.json()["created"] == MAX_BATCH_SIZE
    assert count(db_session, Trade) == MAX_BATCH_SIZE
