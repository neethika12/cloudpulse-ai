from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Anomaly
from app.schemas.anomaly import AnomalyOut, AlertResponse
from app.services.anomaly_service import detect_anomalies
from app.services.slack_service import send_anomaly_alert

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.post("/detect", response_model=list[AnomalyOut])
def detect(db: Session = Depends(get_db)):
    return detect_anomalies(db)


@router.post("/alert", response_model=AlertResponse)
def alert(db: Session = Depends(get_db)):
    anomalies = db.query(Anomaly).all()
    sent, detail = send_anomaly_alert(anomalies)
    return {"sent": sent, "count": len(anomalies), "detail": detail}


@router.get("", response_model=list[AnomalyOut])
def list_anomalies(db: Session = Depends(get_db)):
    return db.query(Anomaly).order_by(Anomaly.date.desc()).all()
