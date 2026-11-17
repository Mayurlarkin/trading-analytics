from datetime import UTC, datetime
from decimal import Decimal

from app.analytics import summarize
from app.analytics.adapters import load_closed_trades
from app.schemas import TradeIn
from app.services.accounts import create_account, update_account
from app.services.ingest import ingest_trades
from app.services.mt5_import import import_mt5_report
from tests.mt5_builder import build_report


def add(db, account, trade_payload, **overrides) -> None:
    ingest_trades(db, account, [TradeIn.model_validate(trade_payload(**overrides))])


def test_loads_trades_oldest_close_first_with_common_symbol_names(
    db_session, account_and_key, trade_payload
) -> None:
    account, _ = account_and_key
    add(db_session, account, trade_payload, ticket=2, symbol="WS30.ifx_m",
        close_time="2026-11-03T10:00:00+00:00")  # fmt: skip
    add(db_session, account, trade_payload, ticket=1, symbol="T100.IFX_M")

    loaded = load_closed_trades(db_session, account.id)

    assert [(t.ticket, t.symbol) for t in loaded] == [(1, "NAS100"), (2, "US30")]
    assert loaded[0].close_time == datetime(2026, 11, 2, 15, 45, tzinfo=UTC)
    assert loaded[0].net == Decimal("96.25")  # 99.75 profit - 3.50 commission


def test_filters_by_close_time_and_account(db_session, account_and_key, trade_payload) -> None:
    account, _ = account_and_key
    other, _ = create_account(db_session, email="o@example.com", label="Other")
    add(db_session, account, trade_payload, ticket=1, close_time="2026-11-02T15:00:00+00:00")
    add(db_session, account, trade_payload, ticket=2, close_time="2026-11-05T15:00:00+00:00")
    add(db_session, other, trade_payload, ticket=3, close_time="2026-11-03T15:00:00+00:00")

    window = load_closed_trades(
        db_session,
        account.id,
        closed_from=datetime(2026, 11, 2, 15, 0, tzinfo=UTC),  # inclusive
        closed_until=datetime(2026, 11, 5, 15, 0, tzinfo=UTC),  # exclusive
    )

    assert [t.ticket for t in window] == [1]
    assert [t.ticket for t in load_closed_trades(db_session, account.id)] == [1, 2]


def test_statistics_over_an_imported_report_match_the_reports_own_total(
    db_session, account_and_key
) -> None:
    account, _ = account_and_key
    update_account(db_session, account.id, server_timezone="ny_close", currency="ZAR")
    import_mt5_report(db_session, account, build_report())

    summary = summarize(load_closed_trades(db_session, account.id), Decimal(100000))

    assert summary.stats.trades == 8
    assert summary.stats.net_profit == Decimal("-944.87")  # the sample report's Total Net Profit
    assert summary.ending_balance == Decimal("99055.13")
