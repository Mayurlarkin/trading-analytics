import io
import zipfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.importers.mt5_report import (
    ReportFormatError,
    read_report,
    reconcile,
    to_trade_inputs,
)
from app.timezones import NY_CLOSE
from tests.mt5_builder import SAMPLE_PATH, SAMPLE_POSITIONS, build_report, position


def test_committed_sample_file_is_readable() -> None:
    report = read_report(SAMPLE_PATH.read_bytes())
    assert [p.ticket for p in report.positions] == [900001 + n for n in range(8)]


def test_only_the_positions_section_is_imported() -> None:
    report = read_report(build_report())
    # Orders/Deals rows carry other numbers (tickets + 5,000,000 / 9,000,000); none leak in.
    assert [p.ticket for p in report.positions] == [p["ticket"] for p in SAMPLE_POSITIONS]
    assert report.row_errors == []


def test_values_are_exact_decimals_in_naive_server_time() -> None:
    first = read_report(build_report()).positions[0]
    assert first.row == 8  # spreadsheet row of the first position
    assert first.symbol == "WS30.ifx_m"  # raw broker symbol, normalised later
    assert first.direction == "sell"
    assert first.volume == Decimal("0.01")
    assert first.open_price == Decimal("47100.4")
    assert first.profit == Decimal("-6.1")
    assert first.open_time == datetime(2026, 3, 3, 9, 12, 41)
    assert first.open_time.tzinfo is None


def test_blank_stops_and_zero_costs_become_none_and_zero() -> None:
    by_ticket = {p.ticket: p for p in read_report(build_report()).positions}
    assert by_ticket[900001].sl is None and by_ticket[900001].tp is None
    assert by_ticket[900002].sl == Decimal("23890.4")
    assert by_ticket[900001].commission == Decimal(0)
    assert by_ticket[900008].commission == Decimal("-2.4")
    assert by_ticket[900005].swap == Decimal("-0.87")


def test_report_header_details() -> None:
    info = read_report(build_report()).info
    assert info.currency == "ZAR"
    assert info.company == "Example Brokers Ltd."
    assert info.account_kind == "demo"
    assert info.margin_mode == "hedge"
    assert info.generated_at == datetime(2026, 11, 15, 19, 25)


def test_empty_positions_section_is_fine() -> None:
    report = read_report(build_report([], net_profit=None))
    assert report.positions == []
    assert report.row_errors == []


# --- reconciliation with the report's own total ---------------------------------------


def test_totals_match_the_reports_net_profit() -> None:
    report = read_report(build_report())
    trades, errors = to_trade_inputs(report.positions, NY_CLOSE)
    assert errors == []
    assert report.reported_net_profit == Decimal(
        "-944.87"
    )  # -929.10 profit - 2.40 commission - 13.37 swap
    assert reconcile(trades, report.reported_net_profit) is None


def test_mismatching_total_produces_a_warning() -> None:
    report = read_report(build_report(net_profit=5000.0))
    trades, _ = to_trade_inputs(report.positions, NY_CLOSE)
    warning = reconcile(trades, report.reported_net_profit)
    assert warning is not None
    assert "5000.00" in warning


def test_missing_net_profit_row_is_not_an_error() -> None:
    report = read_report(build_report(net_profit=None))
    assert report.reported_net_profit is None
    assert reconcile([], None) is None


# --- unreadable files -----------------------------------------------------------------


def test_not_an_xlsx_file() -> None:
    with pytest.raises(ReportFormatError, match="not an Excel"):
        read_report(b"this is a csv, not a workbook")


def test_a_zip_that_is_not_a_workbook() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    with pytest.raises(ReportFormatError, match="could not read"):
        read_report(buffer.getvalue())


def test_oversized_expansion_is_refused() -> None:
    with pytest.raises(ReportFormatError, match="unreasonable size"):
        read_report(build_report(), max_uncompressed=100)


def test_report_without_a_positions_section() -> None:
    with pytest.raises(ReportFormatError, match="Positions"):
        read_report(build_report(positions_marker=None))


def test_localised_headers_are_rejected_with_a_clear_message() -> None:
    header = ["Hora", "Posición", "Símbolo", "Tipo", "Volumen", "Precio", "S / L", "T / P",
              "Hora", "Precio", "Comisión", "Swap", "Beneficio"]  # fmt: skip
    with pytest.raises(ReportFormatError, match="English"):
        read_report(build_report(header=header))


# --- bad rows -------------------------------------------------------------------------


def test_every_bad_row_is_reported_and_good_rows_still_parse() -> None:
    rows = [
        position(1, "2026.03.03 10:00:00", "2026.03.03 10:05:00"),
        position(2, "2026.03.03 10:00:00", "2026.03.03 10:05:00", direction="hold"),
        position(3, "yesterday", "2026.03.03 10:05:00"),
        position(1, "2026.03.03 11:00:00", "2026.03.03 11:05:00"),  # duplicate ticket
        position(5, "2026.03.03 10:00:00", "2026.03.03 10:05:00", profit=None),  # type: ignore[arg-type]
    ]
    report = read_report(build_report(rows, net_profit=None))

    assert [p.ticket for p in report.positions] == [1]
    by_row = {e.row: e.message for e in report.row_errors}
    assert set(by_row) == {9, 10, 11, 12}  # data starts on row 8
    assert "not buy or sell" in by_row[9]
    assert "open Time" in by_row[10]
    assert "already appears on row 8" in by_row[11]
    assert "Profit: missing" in by_row[12]


# --- conversion to UTC TradeIn objects --------------------------------------------------


def test_times_are_converted_to_utc_with_the_us_daylight_saving_rule() -> None:
    report = read_report(build_report())
    trades, _ = to_trade_inputs(report.positions, NY_CLOSE)
    opened = {t.ticket: t.open_time for t in trades}
    assert opened[900001] == datetime(2026, 3, 3, 7, 12, 41, tzinfo=UTC)  # winter, UTC+2
    assert opened[900002] == datetime(2026, 3, 10, 11, 41, 7, tzinfo=UTC)  # US-only DST, UTC+3
    assert opened[900004] == datetime(2026, 7, 1, 6, 15, tzinfo=UTC)  # summer, UTC+3
    assert opened[900006] == datetime(2026, 10, 28, 11, 0, tzinfo=UTC)  # EU ended, US DST on
    assert opened[900007] == datetime(2026, 11, 12, 3, 5, 33, tzinfo=UTC)  # winter, UTC+2


def test_utc_rule_leaves_times_unshifted() -> None:
    report = read_report(build_report())
    trades, _ = to_trade_inputs(report.positions, "UTC")
    assert trades[0].open_time == datetime(2026, 3, 3, 9, 12, 41, tzinfo=UTC)


def test_zero_stop_loss_is_treated_as_unset_and_invalid_rows_are_reported() -> None:
    rows = [
        position(1, "2026.03.03 10:00:00", "2026.03.03 10:05:00", sl=0, tp=0),
        position(2, "2026.03.03 10:10:00", "2026.03.03 10:05:00"),  # closes before it opens
        position(3, "2026.03.03 10:00:00", "2026.03.03 10:05:00", open_price=1.123456),
    ]
    report = read_report(build_report(rows, net_profit=None))
    trades, errors = to_trade_inputs(report.positions, NY_CLOSE)

    assert [t.ticket for t in trades] == [1]
    assert trades[0].sl is None and trades[0].tp is None
    assert {e.row for e in errors} == {9, 10}
    assert "close_time" in errors[0].message or "before" in errors[0].message
    assert "open_price" in errors[1].message
