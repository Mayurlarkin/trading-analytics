"""Create and change accounts, manage their API keys, and import reports: all with a login.

These do what the command line does, for the dashboard. Every route that names an account
goes through ``get_owned_account``, so another user's account (or key) answers 404."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_owned_account
from app.models import Account, User
from app.routers.accounts import _account_out, _account_rows
from app.routers.imports import SERVER_TIME_HELP, run_mt5_import
from app.schemas import Mt5ImportResult
from app.schemas_analytics import AccountOut
from app.schemas_manage import (
    AccountCreate,
    AccountUpdate,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
)
from app.services.accounts import (
    DuplicateAccountLabel,
    TooManyKeys,
    add_account,
    change_account,
    issue_api_key_checked,
    list_api_keys,
    revoke_api_key_by_id,
)
from app.timezones import InvalidServerTimeRule

router = APIRouter(prefix="/accounts", tags=["account management"])


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AccountOut:
    """Create an account. It has no API key yet: issue one with POST /accounts/{id}/api-keys."""
    try:
        account = add_account(db, user, **payload.model_dump())
    except InvalidServerTimeRule as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateAccountLabel as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _account_out(account, 0, None)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    payload: AccountUpdate,
    account: Account = Depends(get_owned_account),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    """Change some settings of an account; fields you leave out stay as they are.

    A new starting balance or currency changes every figure computed for the account."""
    try:
        change_account(db, account, payload.changes())
    except InvalidServerTimeRule as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateAccountLabel as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    (row,) = _account_rows(db, user, account.id)
    return _account_out(*row)


@router.get("/{account_id}/api-keys", response_model=list[ApiKeyOut])
def list_keys(
    account: Account = Depends(get_owned_account), db: Session = Depends(get_db)
) -> list[ApiKeyOut]:
    """The account's keys, newest first. Secrets are never shown again after creation."""
    return [ApiKeyOut.of(key) for key in list_api_keys(db, account)]


@router.post("/{account_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(
    payload: ApiKeyCreate | None = None,
    account: Account = Depends(get_owned_account),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    """Issue a key for an EA or script. The secret is in this response only: store it now."""
    try:
        row, secret = issue_api_key_checked(db, account, payload.label if payload else None)
    except TooManyKeys as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiKeyCreated(**ApiKeyOut.of(row).model_dump(), key=secret)


@router.delete("/{account_id}/api-keys/{key_id}", status_code=204)
def revoke_key(
    key_id: int, account: Account = Depends(get_owned_account), db: Session = Depends(get_db)
) -> Response:
    """Revoke a key: it stops working immediately. Repeating the call is harmless."""
    if revoke_api_key_by_id(db, account, key_id) is None:
        raise HTTPException(status_code=404, detail="key not found")
    return Response(status_code=204)


@router.post("/{account_id}/import/mt5-report", response_model=Mt5ImportResult)
def import_report(
    file: UploadFile = File(description="MT5 History report exported as Excel (.xlsx)"),
    server_time: str | None = Query(default=None, description=SERVER_TIME_HELP),
    dry_run: bool = Query(default=False, description="Validate and count, but save nothing"),
    account: Account = Depends(get_owned_account),
    db: Session = Depends(get_db),
) -> Mt5ImportResult:
    """Import an MT5 report into this account, logged in (same rules as /import/mt5-report)."""
    return run_mt5_import(db, account, file, server_time, dry_run)
