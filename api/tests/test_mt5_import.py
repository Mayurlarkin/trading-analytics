from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Instrument, Trade
from app.services.accounts import create_account, update_account
from tests.mt5_builder import SAMPLE_POSITIONS, build_report, position

URL = "/import/mt5-report"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client: TestClient, headers: dict[str, str], data: bytes | None = None, **params):
    files = {"file": ("report.xlsx", build_report() if data is None else data, XLSX)}
    return client.post(URL, params=params, files=files, headers=headers)


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def ready_headers(db_session, account_and_key, auth_headers) -> dict[str, str]:
    """Headers for an account that already knows its server time and currency (like IFX/ZAR)."""
    update_account(db_session, account_and_key[0].id, server_timezone="ny_close", currency="ZAR")
    return auth_headers


# --- access and prerequisites ---------------------------------------------------------


def test_requires_an_api_key(client: TestClient) -> None:
    response = client.post(URL, files={"file": ("r.xlsx", build_report(), XLSX)})
    assert response.status_code == 401


def test_refuses_to_guess_when_the_server_time_is_not_set(client, auth_headers) -> None:
    response = upload(client, auth_headers)
    assert response.status_code == 422
    assert "server time" in response.json()["detail"]


def test_unknown_server_time_rule_is_rejected(client, auth_headers) -> None:
    response = upload(client, auth_headers, server_time="Mars/Olympus")
    assert response.status_code == 422
    assert "Mars/Olympus" in response.json()["detail"]


def test_missing_file_field(client, ready_headers) -> None:
    assert client.post(URL, headers=ready_headers).status_code == 422


# --- happy path and idempotency -------------------------------------------------------


def test_imports_positions_with_utc_times_and_reports_the_file(
    client, db_session, ready_headers
) -> None:
    response = upload(client, ready_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["positions_in_report"] == 8
    assert (body["created"], body["updated"], body["unchanged"]) == (8, 0, 0)
    assert body["dry_run"] is False
    assert body["server_time"] == "ny_close"
    assert body["report"] == {
        "currency": "ZAR",
        "company": "Example Brokers Ltd.",
        "account_kind": "demo",
        "margin_mode": "hedge",
    }
    assert body["warnings"] == []

    trade = db_session.scalars(select(Trade).where(Trade.ticket == 900002)).one()
    # Server 14:41:07 on 10 Mar is New York 07:41:07 (US DST already on), i.e. 11:41:07 UTC.
    assert trade.open_time == datetime(2026, 3, 10, 11, 41, 7, tzinfo=UTC)
    assert trade.instrument.symbol == "T100.IFX_M"
    assert {i.symbol for i in db_session.scalars(select(Instrument))} == {
        "T100.IFX_M",
        "WS30.IFX_M",
        "XAUUSD.IFX",
    }


def test_importing_the_same_file_twice_changes_nothing(client, db_session, ready_headers) -> None:
    upload(client, ready_headers)
    body = upload(client, ready_headers).json()

    assert (body["created"], body["updated"], body["unchanged"]) == (0, 0, 8)
    assert count(db_session, Trade) == 8


def test_a_longer_report_adds_only_the_new_positions(client, db_session, ready_headers) -> None:
    upload(client, ready_headers)
    extra = position(900009, "2026.11.13 10:00:00", "2026.11.13 10:30:00", profit=42.0)
    body = upload(client, ready_headers, build_report([*SAMPLE_POSITIONS, extra])).json()

    assert (body["created"], body["updated"], body["unchanged"]) == (1, 0, 8)
    assert count(db_session, Trade) == 9


def test_a_corrected_position_is_updated(client, db_session, ready_headers) -> None:
    upload(client, ready_headers)
    edited = [dict(p) for p in SAMPLE_POSITIONS]
    edited[0]["profit"] = -9.99
    body = upload(client, ready_headers, build_report(edited, net_profit=None)).json()

    assert (body["created"], body["updated"], body["unchanged"]) == (0, 1, 7)


def test_dry_run_counts_but_saves_nothing(client, db_session, ready_headers) -> None:
    body = upload(client, ready_headers, dry_run="true").json()

    assert body["dry_run"] is True
    assert body["created"] == 8
    assert count(db_session, Trade) == 0
    assert count(db_session, Instrument) == 0

    real = upload(client, ready_headers).json()  # a real import afterwards still creates all
    assert real["created"] == 8


def test_server_time_parameter_overrides_the_stored_value(
    client, db_session, ready_headers
) -> None:
    body = upload(client, ready_headers, server_time="UTC").json()

    assert body["server_time"] == "UTC"
    trade = db_session.scalars(select(Trade).where(Trade.ticket == 900001)).one()
    assert trade.open_time == datetime(2026, 3, 3, 9, 12, 41, tzinfo=UTC)  # not shifted


def test_each_account_gets_its_own_copy(client, db_session, ready_headers) -> None:
    other, other_key = create_account(
        db_session, email="other@example.com", label="Other", server_timezone="ny_close"
    )
    upload(client, ready_headers)
    body = upload(client, {"X-API-Key": other_key}, server_time="ny_close").json()

    assert body["created"] == 8
    assert count(db_session, Trade) == 16
    assert isinstance(other, Account)


# --- warnings --------------------------------------------------------------------------


def test_warns_when_report_currency_differs_from_the_account(client, auth_headers) -> None:
    body = upload(client, auth_headers, server_time="ny_close").json()  # account defaults to USD
    assert "report currency is ZAR but this account is set to USD" in body["warnings"]


def test_warns_when_totals_do_not_match_the_report(client, ready_headers) -> None:
    body = upload(client, ready_headers, build_report(net_profit=1.0)).json()
    assert any("Total Net Profit" in w for w in body["warnings"])


def test_warns_for_netting_accounts(client, ready_headers) -> None:
    data = build_report(account_line=" (ZAR, Example-Real, real, Netting)")
    body = upload(client, ready_headers, data).json()
    assert any("netting accounts merge positions" in w for w in body["warnings"])


def test_an_empty_report_is_accepted_with_a_warning(client, db_session, ready_headers) -> None:
    response = upload(client, ready_headers, build_report([], net_profit=None))

    assert response.status_code == 200
    assert response.json()["positions_in_report"] == 0
    assert "the report contains no positions" in response.json()["warnings"]
    assert count(db_session, Trade) == 0


# --- rejected files ------------------------------------------------------------------


def test_invalid_rows_reject_the_whole_file_and_name_every_row(
    client, db_session, ready_headers
) -> None:
    rows = [
        position(1, "2026.03.03 10:00:00", "2026.03.03 10:05:00"),
        position(2, "2026.03.03 10:00:00", "2026.03.03 10:05:00", direction="hold"),
        position(3, "2026.03.03 10:10:00", "2026.03.03 10:05:00"),  # closes before it opens
        position(4, "2026.03.03 10:00:00", "2026.03.03 10:05:00", open_price=1.123456),
    ]
    response = upload(client, ready_headers, build_report(rows, net_profit=None))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["total_errors"] == 3
    assert [e["row"] for e in detail["errors"]] == [9, 10, 11]
    assert count(db_session, Trade) == 0  # the valid first row was not imported either


def test_a_file_that_is_not_a_report_is_a_400(client, ready_headers) -> None:
    response = upload(client, ready_headers, b"just some text")
    assert response.status_code == 400
    assert "not an Excel" in response.json()["detail"]


def test_a_workbook_without_positions_is_a_400(client, ready_headers) -> None:
    response = upload(client, ready_headers, build_report(positions_marker=None))
    assert response.status_code == 400
    assert "Positions" in response.json()["detail"]


def test_oversized_uploads_are_refused(client, ready_headers, monkeypatch) -> None:
    monkeypatch.setattr("app.routers.imports.MAX_UPLOAD_BYTES", 100)
    assert upload(client, ready_headers).status_code == 413
