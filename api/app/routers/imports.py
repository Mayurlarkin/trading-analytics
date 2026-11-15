from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_api_key_account
from app.importers.mt5_report import ReportFormatError
from app.models import Account
from app.schemas import Mt5ImportResult
from app.services.mt5_import import ImportRejected, ServerTimeNotSet, import_mt5_report
from app.timezones import InvalidServerTimeRule

router = APIRouter(prefix="/import", tags=["import"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ERRORS_SHOWN = 50


@router.post("/mt5-report", response_model=Mt5ImportResult)
def import_mt5_report_file(
    file: UploadFile = File(description="MT5 History report exported as Excel (.xlsx)"),
    server_time: str | None = Query(
        default=None,
        description=(
            "How to read the report's times: 'ny_close' (New York + 7h, typical for IFX) or an "
            "IANA zone such as 'Europe/Athens' or 'UTC'. Defaults to the account's stored value."
        ),
    ),
    dry_run: bool = Query(default=False, description="Validate and count, but save nothing"),
    account: Account = Depends(get_api_key_account),
    db: Session = Depends(get_db),
) -> Mt5ImportResult:
    """Import closed positions from an MT5 report (History tab -> Report -> Excel).

    Only the Positions section is used. Safe to repeat: positions are matched on ticket.
    """
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file is larger than 10 MB")

    try:
        return import_mt5_report(db, account, data, server_time=server_time, dry_run=dry_run)
    except (ServerTimeNotSet, InvalidServerTimeRule) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReportFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportRejected as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "the report has invalid rows; nothing was imported",
                "total_errors": len(exc.errors),
                "errors": [
                    {"row": e.row, "message": e.message} for e in exc.errors[:MAX_ERRORS_SHOWN]
                ],
            },
        ) from exc
