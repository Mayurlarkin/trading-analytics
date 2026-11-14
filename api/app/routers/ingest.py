from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_api_key_account
from app.models import Account
from app.schemas import IngestResult, TradesIn
from app.services.ingest import ingest_trades

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/trades", response_model=IngestResult)
def post_trades(
    payload: TradesIn,
    account: Account = Depends(get_api_key_account),
    db: Session = Depends(get_db),
) -> IngestResult:
    """Upsert a batch of closed trades for the account that owns the API key.

    Safe to retry: trades are matched on (account, ticket), so re-sending identical
    data changes nothing and the response reports it as `unchanged`.
    """
    return ingest_trades(db, account, payload.trades)
