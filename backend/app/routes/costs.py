from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CostRecord
from app.schemas.cost import CostRecordOut, ServiceTotal, DailyTotal
from app.services.mock_data import seed_mock_data

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    account = seed_mock_data(db)
    count = db.query(CostRecord).filter_by(account_id=account.id).count()
    return {"seeded": True, "account_id": account.id, "records": count}


@router.get("", response_model=list[CostRecordOut])
def list_costs(db: Session = Depends(get_db)):
    return db.query(CostRecord).order_by(CostRecord.date.desc()).limit(200).all()


@router.get("/by-service", response_model=list[ServiceTotal])
def by_service(db: Session = Depends(get_db)):
    rows = (
        db.query(CostRecord.service, func.sum(CostRecord.amount_usd).label("total"))
        .group_by(CostRecord.service)
        .order_by(func.sum(CostRecord.amount_usd).desc())
        .all()
    )
    return [{"service": r.service, "total_usd": round(r.total, 2)} for r in rows]


@router.get("/trend", response_model=list[DailyTotal])
def trend(db: Session = Depends(get_db)):
    rows = (
        db.query(CostRecord.date, func.sum(CostRecord.amount_usd).label("total"))
        .group_by(CostRecord.date)
        .order_by(CostRecord.date)
        .all()
    )
    return [{"date": r.date, "total_usd": round(r.total, 2)} for r in rows]
