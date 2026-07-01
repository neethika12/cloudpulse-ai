from pydantic import BaseModel
from datetime import date


class AnomalyOut(BaseModel):
    service: str
    date: date
    amount_usd: float

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    sent: bool
    count: int
    detail: str
