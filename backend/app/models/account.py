from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.database import Base


class CloudAccount(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="aws")
    aws_account_id: Mapped[str] = mapped_column(String(50), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Real AWS credentials for accounts connected via "Connect AWS account" in the UI.
    # Null for the shared demo account. Secret key is encrypted at rest (Fernet) -
    # never stored or logged in plaintext.
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    aws_access_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aws_secret_access_key_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    aws_region: Mapped[str | None] = mapped_column(String(50), nullable=True)

    cost_records = relationship("CostRecord", back_populates="account", cascade="all, delete-orphan")
