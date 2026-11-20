"""Hybrid retrieval over the knowledge base.

    query ──┬─► vector search  (pgvector cosine distance, HNSW index) ─┐
            └─► keyword search (Postgres full-text, ts_rank_cd)       ─┴─► RRF fusion ─► LLM rerank ─► top k

Vector search catches paraphrases ("shrink my instance bill" ~ "rightsizing"); keyword
search catches exact terms embeddings blur together ("NAT gateway", "gp3",
"Deep Archive"). Reciprocal Rank Fusion merges the two lists using ranks only, so the
incomparable scores (cosine distance vs ts_rank) never need calibrating. A small LLM
then reorders the fused shortlist by actual relevance to the question.

On SQLite (the test database) both retrievers fall back to an in-Python implementation
with the same interface.
"""
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import KnowledgeChunk
from app.services import llm

logger = logging.getLogger("cloudpulse")

RRF_K = 60  # standard constant from the original RRF paper (Cormack et al., 2009)
MODES = ("vector", "keyword", "hybrid")

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how",
    "i", "if", "in", "is", "it", "my", "of", "on", "or", "should", "so", "that", "the", "this",
    "to", "we", "what", "when", "which", "why", "with", "you", "your",
}


@dataclass
class Passage:
    id: int
    source: str
    title: str
    section: str
    content: str
    ranks: dict[str, int] = field(default_factory=dict)  # retriever -> 1-based rank
    score: float = 0.0


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _to_passage(row: KnowledgeChunk) -> Passage:
    return Passage(row.id, row.source, row.title, row.section, row.content)


# ---------- retrievers ----------

def vector_search(db: Session, query_vector: list[float], k: int) -> list[Passage]:
    if _is_postgres(db):
        rows = (
            db.query(KnowledgeChunk)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vector))
            .limit(k)
            .all()
        )
        return [_to_passage(r) for r in rows]

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
        return dot / norm if norm else 0.0

    rows = db.query(KnowledgeChunk).all()
    rows.sort(key=lambda r: cosine(query_vector, list(r.embedding)), reverse=True)
    return [_to_passage(r) for r in rows[:k]]


def keyword_search(db: Session, query: str, k: int) -> list[Passage]:
    terms = _tokens(query)
    if not terms:
        return []

    if _is_postgres(db):
        # OR the terms together: plainto/websearch_to_tsquery AND them, which returns
        # nothing for most natural-language questions. Terms are [a-z0-9]+ only, so
        # building the tsquery string is injection-safe.
        tsquery = func.to_tsquery("english", " | ".join(terms))
        document = func.to_tsvector("english", KnowledgeChunk.content)
        rows = (
            db.query(KnowledgeChunk)
            .filter(document.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(document, tsquery).desc())
            .limit(k)
            .all()
        )
        return [_to_passage(r) for r in rows]

    # BM25 fallback for SQLite.
    rows = db.query(KnowledgeChunk).all()
    docs = [_tokens(r.content) for r in rows]
    if not docs:
        return []
    avg_len = sum(len(d) for d in docs) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    k1, b = 1.5, 0.75
    scored = []
    for row, doc in zip(rows, docs):
        tf = Counter(doc)
        score = 0.0
        for term in set(terms):
            if term not in tf:
                continue
            idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(doc) / avg_len))
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [_to_passage(r) for _, r in scored[:k]]


# ---------- fusion + rerank ----------

def reciprocal_rank_fusion(ranked_lists: dict[str, list[Passage]], k: int = RRF_K) -> list[Passage]:
    fused: dict[int, Passage] = {}
    for retriever, passages in ranked_lists.items():
        for rank, passage in enumerate(passages, start=1):
            entry = fused.setdefault(passage.id, passage)
            entry.ranks[retriever] = rank
            entry.score += 1.0 / (k + rank)
    return sorted(fused.values(), key=lambda p: p.score, reverse=True)


RERANK_PROMPT = (
    "You rank search results for a cloud cost (FinOps) assistant. Given a question and "
    "numbered passages, return JSON {\"ranking\": [passage numbers]} listing the passages "
    "that help answer the question, most useful first. Leave out irrelevant passages."
)


def rerank(question: str, passages: list[Passage], tracker: llm.UsageTracker | None) -> list[Passage]:
    if len(passages) <= 1:
        return passages
    listing = "\n\n".join(f"[{i}] {p.content[:700]}" for i, p in enumerate(passages, start=1))
    try:
        result = llm.complete_json(
            [{"role": "system", "content": RERANK_PROMPT},
             {"role": "user", "content": f"Question: {question}\n\nPassages:\n{listing}"}],
            settings.openai_rerank_model, tracker, kind="rerank",
        )
        order = [int(n) for n in result.get("ranking", []) if str(n).isdigit()]
    except Exception:  # reranking is an enhancement; fall back to fused order
        logger.exception("rerank failed, using fused order")
        return passages

    seen, reranked = set(), []
    for n in order:
        if 1 <= n <= len(passages) and n not in seen:
            seen.add(n)
            reranked.append(passages[n - 1])
    # Keep anything the reranker skipped at the end, so a too-strict reranker can't empty the results.
    reranked.extend(p for i, p in enumerate(passages, start=1) if i not in seen)
    return reranked


def search(
    db: Session,
    query: str,
    *,
    mode: str = "hybrid",
    use_rerank: bool | None = None,
    top_k: int | None = None,
    tracker: llm.UsageTracker | None = None,
) -> list[Passage]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not settings.embeddings_enabled:
        mode = "keyword"  # no embedding model configured
    top_k = top_k or settings.rag_top_k
    use_rerank = settings.rag_rerank if use_rerank is None else use_rerank
    n = settings.rag_candidates

    lists: dict[str, list[Passage]] = {}
    if mode in ("vector", "hybrid"):
        lists["vector"] = vector_search(db, llm.embed([query], tracker)[0], n)
    if mode in ("keyword", "hybrid"):
        lists["keyword"] = keyword_search(db, query, n)

    candidates = reciprocal_rank_fusion(lists)
    if use_rerank:
        # Rerank a shortlist only; the tail of the fused list is rarely worth the tokens.
        shortlist = candidates[: max(top_k * 2, 10)]
        candidates = rerank(query, shortlist, tracker)
    return candidates[:top_k]
