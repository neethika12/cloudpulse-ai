"""Builds the RAG index from the markdown guides in backend/knowledge/.

Chunking is heading-aware: each `## section` is split on paragraph boundaries into
chunks of at most MAX_CHARS, and every chunk is prefixed with "<doc title> > <section>"
(a contextual chunk header), so a passage like "Delete them after 7 days" still says
what it is about when retrieved on its own.

Ingestion is incremental: chunks are keyed by a hash of their text and the embedding
model, so re-running it only embeds new or edited passages and deletes stale ones.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import KnowledgeChunk
from app.services import llm

logger = logging.getLogger("cloudpulse")

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
MAX_CHARS = 1200
OVERLAP_CHARS = 200


@dataclass
class Chunk:
    source: str
    title: str
    section: str
    chunk_index: int
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{settings.openai_embedding_model}\n{self.content}".encode()).hexdigest()


def _split_long(text: str) -> list[str]:
    """Hard-split one oversized paragraph into overlapping windows, breaking on spaces."""
    pieces, start = [], 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        if end < len(text):
            space = text.rfind(" ", start + MAX_CHARS // 2, end)
            end = space if space != -1 else end
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return pieces


def _pack(paragraphs: list[str]) -> list[str]:
    chunks, current = [], ""
    for para in paragraphs:
        if len(para) > MAX_CHARS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long(para))
        elif len(current) + len(para) + 2 > MAX_CHARS:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(source).stem.replace("-", " ").title()

    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block or block.startswith("# "):
            continue
        heading = re.match(r"^##+ (.+)$", block.splitlines()[0])
        if heading:
            sections.append((heading.group(1).strip(), []))
            rest = "\n".join(block.splitlines()[1:]).strip()
            if rest:
                sections[-1][1].append(rest)
        else:
            sections[-1][1].append(block)

    chunks: list[Chunk] = []
    for section, paragraphs in sections:
        for body in _pack(paragraphs):
            chunks.append(Chunk(source, title, section, len(chunks), f"{title} > {section}\n\n{body}"))
    return chunks


def load_documents(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    return chunks


def ingest(db: Session, tracker: llm.UsageTracker | None = None) -> dict:
    chunks = load_documents()
    wanted = {c.content_hash: c for c in chunks}
    existing = {row.content_hash: row for row in db.query(KnowledgeChunk).all()}

    removed = 0
    for content_hash, row in existing.items():
        if content_hash not in wanted:
            db.delete(row)
            removed += 1

    new_chunks = [c for h, c in wanted.items() if h not in existing]
    if new_chunks:
        if settings.embeddings_enabled:
            vectors = llm.embed([c.content for c in new_chunks], tracker)
        else:
            # Keyword-only mode: the column is NOT NULL, so store an unused placeholder.
            vectors = [[0.0] * settings.embedding_dimensions for _ in new_chunks]
        for chunk, vector in zip(new_chunks, vectors):
            db.add(KnowledgeChunk(
                source=chunk.source, title=chunk.title, section=chunk.section,
                chunk_index=chunk.chunk_index, content=chunk.content,
                content_hash=chunk.content_hash, embedding=vector,
            ))
    db.commit()

    result = {"added": len(new_chunks), "unchanged": len(wanted) - len(new_chunks), "removed": removed}
    logger.info("knowledge base indexed: %s", result)
    return result


def ensure_indexed(db: Session, tracker: llm.UsageTracker | None = None) -> None:
    """Builds the index on first use so a fresh install works without a manual step."""
    if db.query(KnowledgeChunk.id).first() is None:
        try:
            ingest(db, tracker)
        except IntegrityError:
            # Another request indexed the same chunks at the same moment; theirs won.
            db.rollback()


def status(db: Session) -> dict:
    chunks, documents = db.query(func.count(KnowledgeChunk.id), func.count(func.distinct(KnowledgeChunk.source))).one()
    on_disk = sorted(p.name for p in KNOWLEDGE_DIR.glob("*.md"))
    return {
        "chunks": chunks,
        "documents": documents,
        "documents_on_disk": len(on_disk),
        "sources": on_disk,
        "embedding_model": settings.openai_embedding_model,
    }
