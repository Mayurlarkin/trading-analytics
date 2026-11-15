"""Reader for the MT5 "Trade History Report" Excel export (History tab -> Report).

The sheet stacks several sections: Positions, Orders, Deals and a Results summary. Only
the Positions section is imported (one row per closed position, which is what the
database stores). Times in the sheet are broker server time with no timezone; converting
them to UTC is a separate step (see ``to_trade_inputs``).

Nothing here touches the database.
"""

import io
import itertools
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl
from pydantic import ValidationError

from app.schemas import TradeIn
from app.timezones import server_time_to_utc

MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # guards against zip bombs
MAX_SHEET_ROWS = 200_000

_TIME_FORMAT = "%Y.%m.%d %H:%M:%S"
_SECTION_MARKERS = {"orders", "deals", "results"}
_EXPECTED_HEADER = [
    "time",
    "position",
    "symbol",
    "type",
    "volume",
    "price",
    "s / l",
    "t / p",
    "time",
    "price",
    "commission",
    "swap",
    "profit",
]


class ReportFormatError(ValueError):
    """The file is not an MT5 report we can read (as opposed to bad rows inside one)."""


@dataclass(frozen=True)
class RowError:
    row: int  # 1-based spreadsheet row, so it can be found in Excel
    message: str


@dataclass(frozen=True)
class ReportInfo:
    currency: str | None = None
    company: str | None = None
    account_kind: str | None = None  # "demo" / "real" / ...
    margin_mode: str | None = None  # "hedge" / "netting" / ...
    generated_at: datetime | None = None  # server time


@dataclass(frozen=True)
class RawPosition:
    row: int
    ticket: int
    symbol: str
    direction: str
    volume: Decimal
    open_time: datetime  # naive, server time
    open_price: Decimal
    sl: Decimal | None
    tp: Decimal | None
    close_time: datetime  # naive, server time
    close_price: Decimal
    commission: Decimal
    swap: Decimal
    profit: Decimal


@dataclass
class ParsedReport:
    info: ReportInfo
    positions: list[RawPosition] = field(default_factory=list)
    row_errors: list[RowError] = field(default_factory=list)
    reported_net_profit: Decimal | None = None


# --- cell helpers ---------------------------------------------------------------------


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any, label: str) -> Decimal | None:
    """Excel numbers arrive as floats; go via repr so 4.97 becomes Decimal('4.97')."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}: unexpected value {value!r}")
    try:
        if isinstance(value, int):
            return Decimal(value)
        if isinstance(value, float):
            return Decimal(repr(round(value, 10)))
        return Decimal(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{label}: {value!r} is not a number") from None


def _required_decimal(value: Any, label: str) -> Decimal:
    result = _decimal(value, label)
    if result is None:
        raise ValueError(f"{label}: missing")
    return result


def _datetime(value: Any, label: str) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.strptime(_text(value), _TIME_FORMAT)
    except ValueError:
        raise ValueError(f"{label}: {value!r} is not a time like 2026.03.03 17:56:52") from None


def _value_after(row: tuple[Any, ...], label: str) -> Any:
    """The first non-empty cell to the right of a label cell, e.g. 'Total Net Profit:'."""
    for index, cell in enumerate(row):
        if _text(cell) == label:
            return next((v for v in row[index + 1 :] if v not in (None, "")), None)
    return None


# --- workbook ---------------------------------------------------------------------------


def _load_rows(data: bytes, max_uncompressed: int) -> list[tuple[Any, ...]]:
    buffer = io.BytesIO(data)
    if not zipfile.is_zipfile(buffer):
        raise ReportFormatError("not an Excel .xlsx file")
    with zipfile.ZipFile(buffer) as archive:
        if sum(info.file_size for info in archive.infolist()) > max_uncompressed:
            raise ReportFormatError("file expands to an unreasonable size")
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        rows = list(itertools.islice(sheet.iter_rows(values_only=True), MAX_SHEET_ROWS))
        workbook.close()
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise ReportFormatError(f"could not read the workbook: {exc}") from exc
    return rows


def _parse_info(rows: list[tuple[Any, ...]], limit: int) -> ReportInfo:
    currency = kind = mode = None
    company = None
    generated_at = None
    for row in rows[:limit]:
        label = _text(row[0]) if row else ""
        value = _value_after(row, label) if label else None
        if label == "Account:" and value is not None:
            match = re.search(r"\(([^)]*)\)", str(value))
            parts = [p.strip() for p in match.group(1).split(",")] if match else []
            currency = next((p for p in parts if re.fullmatch(r"[A-Z]{3}", p)), None)
            kind = next(
                (p.lower() for p in parts if p.lower() in {"demo", "real", "contest"}), None
            )
            mode = next(
                (p.lower() for p in parts if p.lower() in {"hedge", "netting", "exchange"}), None
            )
        elif label == "Company:":
            company = _text(value) or None
        elif label == "Date:" and value is not None:
            try:
                generated_at = datetime.strptime(_text(value), "%Y.%m.%d %H:%M")
            except ValueError:
                generated_at = None
    return ReportInfo(currency, company, kind, mode, generated_at)


def _parse_position(row_number: int, row: tuple[Any, ...]) -> RawPosition:
    cells = list(row) + [None] * (13 - len(row))
    problems: list[str] = []

    def attempt(func: Any, *args: Any) -> Any:
        try:
            return func(*args)
        except ValueError as exc:
            problems.append(str(exc))
            return None

    ticket = cells[1]
    if isinstance(ticket, float) and ticket.is_integer():
        ticket = int(ticket)
    if not isinstance(ticket, int) or isinstance(ticket, bool):
        problems.append(f"Position: {ticket!r} is not a whole number")

    direction = _text(cells[3]).lower()
    if direction not in {"buy", "sell"}:
        problems.append(f"Type: {cells[3]!r} is not buy or sell")

    symbol = _text(cells[2])
    if not symbol:
        problems.append("Symbol: missing")

    open_time = attempt(_datetime, cells[0], "open Time")
    close_time = attempt(_datetime, cells[8], "close Time")
    volume = attempt(_required_decimal, cells[4], "Volume")
    open_price = attempt(_required_decimal, cells[5], "open Price")
    close_price = attempt(_required_decimal, cells[9], "close Price")
    profit = attempt(_required_decimal, cells[12], "Profit")
    sl = attempt(_decimal, cells[6], "S / L")
    tp = attempt(_decimal, cells[7], "T / P")
    commission = attempt(_decimal, cells[10], "Commission")
    swap = attempt(_decimal, cells[11], "Swap")

    if problems:
        raise ValueError("; ".join(problems))
    return RawPosition(
        row=row_number,
        ticket=ticket,
        symbol=symbol,
        direction=direction,
        volume=volume,
        open_time=open_time,
        open_price=open_price,
        sl=sl,
        tp=tp,
        close_time=close_time,
        close_price=close_price,
        commission=commission if commission is not None else Decimal(0),
        swap=swap if swap is not None else Decimal(0),
        profit=profit,
    )


def read_report(data: bytes, *, max_uncompressed: int = MAX_UNCOMPRESSED_BYTES) -> ParsedReport:
    """Parse the Positions section of an MT5 report.

    Raises ReportFormatError if the file is not a report we understand. Problems in
    individual rows are collected in ``row_errors`` (all of them, not just the first).
    """
    rows = _load_rows(data, max_uncompressed)

    start = next((i for i, r in enumerate(rows) if r and _text(r[0]) == "Positions"), None)
    if start is None:
        raise ReportFormatError(
            "no 'Positions' section found. Export from the History tab: right-click -> "
            "Report, in English, with the Positions view"
        )
    if start + 1 >= len(rows):
        raise ReportFormatError("the Positions section has no header row")
    header = [_text(c).lower() for c in rows[start + 1][:13]]
    if header != _EXPECTED_HEADER:
        raise ReportFormatError(
            "unexpected Positions columns (only English MT5 reports are supported). "
            f"Expected {_EXPECTED_HEADER}, got {header}"
        )

    report = ParsedReport(info=_parse_info(rows, start))
    seen: dict[int, int] = {}
    end = len(rows)
    for index in range(start + 2, len(rows)):
        row = rows[index]
        first = _text(row[0]) if row else ""
        if first.lower() in _SECTION_MARKERS or all(c in (None, "") for c in row):
            end = index
            break
        row_number = index + 1  # spreadsheet rows are 1-based
        try:
            position = _parse_position(row_number, row)
        except ValueError as exc:
            report.row_errors.append(RowError(row_number, str(exc)))
            continue
        if position.ticket in seen:
            report.row_errors.append(
                RowError(
                    row_number,
                    f"Position {position.ticket} already appears on row {seen[position.ticket]}",
                )
            )
            continue
        seen[position.ticket] = row_number
        report.positions.append(position)

    for row in rows[end:]:
        value = _value_after(row, "Total Net Profit:") if row else None
        if value is not None:
            try:
                report.reported_net_profit = _decimal(value, "Total Net Profit")
            except ValueError:
                report.reported_net_profit = None
            break
    return report


# --- conversion to the ingestion model --------------------------------------------------


def to_trade_inputs(
    positions: list[RawPosition], server_time_rule: str
) -> tuple[list[TradeIn], list[RowError]]:
    """Convert server-time positions to validated, UTC TradeIn objects.

    Reuses the same validation as the HTTP ingest endpoint, so both paths accept and
    reject exactly the same data.
    """
    trades: list[TradeIn] = []
    errors: list[RowError] = []
    for p in positions:
        try:
            trades.append(
                TradeIn(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    direction=p.direction,
                    volume=p.volume,
                    open_time=server_time_to_utc(p.open_time, server_time_rule),
                    close_time=server_time_to_utc(p.close_time, server_time_rule),
                    open_price=p.open_price,
                    close_price=p.close_price,
                    sl=p.sl,
                    tp=p.tp,
                    commission=p.commission,
                    swap=p.swap,
                    profit=p.profit,
                )
            )
        except ValidationError as exc:
            detail = "; ".join(
                f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            errors.append(RowError(p.row, detail))
    return trades, errors


def reconcile(trades: list[TradeIn], reported_net_profit: Decimal | None) -> str | None:
    """Compare our totals with the report's own 'Total Net Profit'; return a warning if off."""
    if reported_net_profit is None:
        return None
    ours = sum((t.profit + t.commission + t.swap for t in trades), Decimal(0))
    if ours.quantize(Decimal("0.01")) == reported_net_profit.quantize(Decimal("0.01")):
        return None
    return (
        f"imported positions total {ours:.2f} (profit + commission + swap) but the report's "
        f"Total Net Profit is {reported_net_profit:.2f}; some rows may be missing"
    )
