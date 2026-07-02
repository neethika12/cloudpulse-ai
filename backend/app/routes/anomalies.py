from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Anomaly, User
from app.schemas.anomaly import AnomalyOut, AlertResponse
from app.routes.auth import get_optional_current_user
from app.services.anomaly_service import detect_anomalies
from app.services.slack_service import send_anomaly_alert

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.post("/detect", response_model=list[AnomalyOut])
def detect(db: Session = Depends(get_db)):
    return detect_anomalies(db)


@router.post("/alert", response_model=AlertResponse)
def alert(
    current_user: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    anomalies = db.query(Anomaly).all()
    webhook_url = current_user.slack_webhook_url if current_user else None
    sent, detail = send_anomaly_alert(anomalies, webhook_url=webhook_url)
    return {"sent": sent, "count": len(anomalies), "detail": detail}


@router.get("", response_model=list[AnomalyOut])
def list_anomalies(db: Session = Depends(get_db)):
    return db.query(Anomaly).order_by(Anomaly.date.desc()).all()
