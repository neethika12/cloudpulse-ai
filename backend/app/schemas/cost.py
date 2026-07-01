from pydantic import BaseModel
from datetime import date


class CostRecordOut(BaseModel):
    service: str
    date: date
    amount_usd: float

    class Config:
        from_attributes = True


class ServiceTotal(BaseModel):
    service: str
    total_usd: float


class DailyTotal(BaseModel):
    date: date
    total_usd: float
