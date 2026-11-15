from sqlalchemy.orm import Session

from app.importers.mt5_report import (
    RowError,
    read_report,
    reconcile,
    to_trade_inputs,
)
from app.models import Account
from app.schemas import Mt5ImportResult, ReportInfoOut
from app.services.ingest import ingest_trades
from app.timezones import validate_server_time_rule


class ServerTimeNotSet(Exception):
    """No server-time rule given and the account has none stored."""


class ImportRejected(Exception):
    """The report was readable but some rows are invalid; nothing was imported."""

    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(f"{len(errors)} invalid row(s)")
        self.errors = errors


def import_mt5_report(
    db: Session,
    account: Account,
    data: bytes,
    *,
    server_time: str | None = None,
    dry_run: bool = False,
) -> Mt5ImportResult:
    """Import the closed positions from an MT5 Excel report into an account.

    All-or-nothing: any invalid row rejects the whole file. Safe to repeat: positions are
    matched on ticket, so importing the same (or an extended) report again only adds or
    updates what changed. With ``dry_run`` the counts are computed but nothing is saved.

    Raises ServerTimeNotSet, InvalidServerTimeRule, ReportFormatError or ImportRejected.
    """
    rule = server_time or account.server_timezone
    if not rule:
        raise ServerTimeNotSet(
            "This account has no broker server time set. Pass server_time (e.g. 'ny_close') "
            "or store it with: python -m app.cli update-account --account-id N --server-time ..."
        )
    rule = validate_server_time_rule(rule)

    report = read_report(data)
    trades, conversion_errors = to_trade_inputs(report.positions, rule)
    errors = sorted(report.row_errors + conversion_errors, key=lambda e: e.row)
    if errors:
        raise ImportRejected(errors)

    info = report.info
    warnings: list[str] = []
    if not trades:
        warnings.append("the report contains no positions")
    if info.currency and info.currency != account.currency:
        warnings.append(
            f"report currency is {info.currency} but this account is set to {account.currency}"
        )
    if info.margin_mode and info.margin_mode != "hedge":
        warnings.append(
            f"{info.margin_mode} accounts merge positions, so results are not validated for them"
        )
    mismatch = reconcile(trades, report.reported_net_profit)
    if mismatch:
        warnings.append(mismatch)

    outcome = ingest_trades(db, account, trades, commit=not dry_run) if trades else None
    if dry_run:
        db.rollback()

    return Mt5ImportResult(
        positions_in_report=len(trades),
        created=outcome.created if outcome else 0,
        updated=outcome.updated if outcome else 0,
        unchanged=outcome.unchanged if outcome else 0,
        dry_run=dry_run,
        server_time=rule,
        report=ReportInfoOut(
            currency=info.currency,
            company=info.company,
            account_kind=info.account_kind,
            margin_mode=info.margin_mode,
        ),
        warnings=warnings,
    )
