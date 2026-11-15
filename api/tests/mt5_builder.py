"""Builds small, synthetic MT5 "Trade History Report" workbooks for tests.

The layout mirrors a real export (Positions / Orders / Deals / Results stacked in one
sheet) but every number here is invented, so no real trading history is committed.

Regenerate the committed sample with:  python -m tests.mt5_builder
"""

import io
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl

SAMPLE_PATH = Path(__file__).parent / "fixtures" / "mt5_sample_report.xlsx"

POSITION_HEADER = [
    "Time",
    "Position",
    "Symbol",
    "Type",
    "Volume",
    "Price",
    "S / L",
    "T / P",
    "Time",
    "Price",
    "Commission",
    "Swap",
    "Profit",
]


def position(
    ticket: int,
    open_time: str,
    close_time: str,
    *,
    symbol: str = "T100.ifx_m",
    direction: str = "buy",
    volume: str = "0.10",
    open_price: float = 24000.5,
    close_price: float = 24010.5,
    sl: float | None = None,
    tp: float | None = None,
    commission: float = 0,
    swap: float = 0,
    profit: float = 100.0,
) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "ticket": ticket,
        "symbol": symbol,
        "direction": direction,
        "volume": volume,
        "open_price": open_price,
        "sl": sl,
        "tp": tp,
        "close_time": close_time,
        "close_price": close_price,
        "commission": commission,
        "swap": swap,
        "profit": profit,
    }


# Times are broker server time. They straddle the spring/autumn windows where US and EU
# daylight saving differ (10 Mar and 28 Oct), plus plain winter and summer days.
SAMPLE_POSITIONS: list[dict[str, Any]] = [
    position(
        900001,
        "2026.03.03 09:12:41",
        "2026.03.03 09:19:07",
        symbol="WS30.ifx_m",
        direction="sell",
        volume="0.01",
        open_price=47100.4,
        close_price=47131.9,
        profit=-6.1,
    ),
    position(
        900002,
        "2026.03.10 14:41:07",
        "2026.03.10 14:43:30",
        sl=23890.4,
        tp=23960.1,
        volume="0.1",
        open_price=23912.35,
        close_price=23918.85,
        profit=50.2,
    ),
    position(
        900003,
        "2026.03.10 15:02:11",
        "2026.03.10 15:06:45",
        direction="sell",
        volume="1",
        open_price=23955.2,
        close_price=23951.7,
        sl=23962.0,
        tp=23944.9,
        profit=175.0,
    ),
    position(
        900004,
        "2026.07.01 09:15:00",
        "2026.07.01 11:45:30",
        symbol="XAUUSD.ifx",
        volume="0.01",
        open_price=4801.3,
        close_price=4795.8,
        sl=4788.0,
        tp=4815.5,
        profit=-55.0,
    ),
    position(
        900005,
        "2026.07.01 16:30:05",
        "2026.07.02 01:01:00",
        direction="sell",
        volume="0.05",
        open_price=24410.2,
        close_price=24388.7,
        swap=-0.87,
        profit=43.7,
    ),
    position(
        900006,
        "2026.10.28 14:00:00",
        "2026.10.28 14:20:41",
        symbol="WS30.ifx_m",
        volume="0.34",
        open_price=46100.0,
        close_price=46040.0,
        sl=46030.0,
        profit=-251.5,
    ),
    position(
        900007,
        "2026.11.12 05:05:33",
        "2026.11.12 14:40:12",
        volume="0.03",
        open_price=28010.4,
        close_price=27866.2,
        sl=27850.0,
        tp=28300.0,
        swap=-12.5,
        profit=-980.4,
    ),
    position(
        900008,
        "2026.11.12 14:50:00",
        "2026.11.12 14:55:00",
        direction="sell",
        volume="0.02",
        open_price=27900.0,
        close_price=27890.5,
        commission=-2.4,
        profit=95.0,
    ),
]


def build_report(
    positions: list[dict[str, Any]] | None = None,
    *,
    account_line: str = " (ZAR, IFXBrokers-Real, demo, Hedge)",
    net_profit: Decimal | float | str | None = "auto",
    header: list[str] | None = None,
    positions_marker: str | None = "Positions",
) -> bytes:
    """Return the bytes of an .xlsx laid out like an MT5 report."""
    rows = SAMPLE_POSITIONS if positions is None else positions
    wb = openpyxl.Workbook()
    ws = wb.active

    ws.append(["Trade History Report"])
    ws.append(["Name:", None, None, "Sample Trader"])
    ws.append(["Account:", None, None, account_line])
    ws.append(["Company:", None, None, "Example Brokers Ltd."])
    ws.append(["Date:", None, None, "2026.11.15 19:25"])
    if positions_marker is not None:
        ws.append([positions_marker])
    ws.append(header or POSITION_HEADER)
    for p in rows:
        ws.append(
            [
                p["open_time"], p["ticket"], p["symbol"], p["direction"], p["volume"],
                p["open_price"], p["sl"], p["tp"], p["close_time"], p["close_price"],
                p["commission"], p["swap"], p["profit"],
            ]
        )  # fmt: skip

    # Orders and Deals sections: present in real exports and must be ignored by the importer.
    ws.append(["Orders"])
    ws.append(["Open Time", "Order", "Symbol", "Type", "Volume", "Price", "S / L", "T / P",
               "Time", "State", None, "Comment"])  # fmt: skip
    for p in rows[:2]:
        ws.append([p["open_time"], p["ticket"] + 5_000_000, p["symbol"], p["direction"],
                   f"{p['volume']} / {p['volume']}", "market", None, None, p["open_time"],
                   "filled"])  # fmt: skip
    ws.append(["Deals"])
    ws.append(["Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order",
               "Commission", "Fee", "Swap", "Profit", "Balance", "Comment"])  # fmt: skip
    ws.append(["2026.03.03 17:26:28", 800000, None, "balance", None, None, None, None, 0, 0, 0,
               100000, 100000])  # fmt: skip
    for p in rows[:2]:
        deal_id, order_id = p["ticket"] + 9_000_000, p["ticket"] + 5_000_000
        ws.append([p["open_time"], deal_id, p["symbol"], p["direction"], "in", p["volume"],
                   p["open_price"], order_id, 0, 0, 0, 0, 100000])  # fmt: skip
    ws.append([])
    ws.append([])
    ws.append(["Results"])
    if net_profit is not None:
        if net_profit == "auto":
            net_profit = float(
                sum(Decimal(repr(p["profit"])) + Decimal(repr(p["commission"]))
                    + Decimal(repr(p["swap"])) for p in rows)
            )  # fmt: skip
        ws.append(
            ["Total Net Profit:", None, None, float(net_profit), "Gross Profit:", None, None, 1]
        )

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_PATH.write_bytes(build_report())
    print(f"wrote {SAMPLE_PATH}")
