from sqlalchemy import String, Float, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date
from app.database import Base


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    service: Mapped[str] = mapped_column(String(80), index=True)  # e.g. EC2, S3, RDS
    date: Mapped[date] = mapped_column(Date, index=True)
    amount_usd: Mapped[float] = mapped_column(Float)

    account = relationship("CloudAccount", back_populates="cost_records")