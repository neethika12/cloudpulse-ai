import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger("cloudpulse")
router = APIRouter()


@router.get("/health")
def health_check():
    """Liveness probe - just confirms the process is up and answering requests."""
    return {"status": "ok", "service": "cloudpulse-ai-backend"}


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe - confirms the app can actually serve traffic, i.e. the database
    connection works. Container orchestrators (ECS, Kubernetes) poll this separately
    from /health so a DB blip pulls the instance out of rotation without restarting it.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Readiness check failed: database unreachable (%s)", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unreachable"},
        )

    return {"status": "ok", "database": "ok"}
