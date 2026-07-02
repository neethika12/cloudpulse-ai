from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CloudAccount, User
from app.schemas.account import AccountOut, ConnectAwsRequest, SyncResponse
from app.routes.auth import get_current_user
from app.services.aws_service import connect_aws_account, sync_real_costs, AwsCredentialError

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(CloudAccount).all()


@router.get("/me", response_model=AccountOut | None)
def my_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(CloudAccount).filter_by(user_id=current_user.id).first()


@router.post("/connect-aws", response_model=AccountOut)
def connect_aws(
    payload: ConnectAwsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return connect_aws_account(
            db, current_user, payload.access_key_id, payload.secret_access_key, payload.region
        )
    except AwsCredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sync", response_model=SyncResponse)
def sync_aws_costs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.query(CloudAccount).filter_by(user_id=current_user.id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="No AWS account connected yet")

    try:
        count = sync_real_costs(db, account)
    except AwsCredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"synced_records": count}
