from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone
from app.database import Base

# all-MiniLM-L6-v2 (local sentence-transformers model) outputs 384-dim vectors.
EMBEDDING_DIM = 384


class CostEmbedding(Base):
    __tablename__ = "cost_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
