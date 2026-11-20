from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.database import Base


class KnowledgeChunk(Base):
    """One retrievable passage of a knowledge-base document, with its embedding.

    The embedding is a pgvector column on Postgres. The SQLite test database stores it
    as JSON instead, and retrieval falls back to an in-Python search there."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(200), index=True)  # file name, e.g. ec2-rightsizing.md
    title: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(300))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # sha256 of content + embedding model, so re-indexing only embeds what changed.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions).with_variant(JSON(), "sqlite")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
