from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CloudAccount
from app.schemas.account import AccountOut

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(CloudAccount).all()
