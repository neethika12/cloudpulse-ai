from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.auth import get_current_user
from app.schemas.chat import KnowledgeSearchRequest
from app.services import knowledge_base, llm, retrieval

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _require_llm() -> None:
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail=llm.NOT_CONFIGURED_MESSAGE)


@router.get("/status")
def status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return knowledge_base.status(db)


@router.post("/reindex")
def reindex(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-reads backend/knowledge/*.md and embeds only new or changed chunks."""
    _require_llm()
    tracker = llm.UsageTracker()
    result = knowledge_base.ingest(db, tracker)
    return {**result, "usage": tracker.summary()}


@router.post("/search")
def search(payload: KnowledgeSearchRequest, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs retrieval on its own, without the chat model: useful for comparing
    vector, keyword and hybrid results for the same query."""
    _require_llm()
    tracker = llm.UsageTracker()
    knowledge_base.ensure_indexed(db, tracker)
    passages = retrieval.search(db, payload.query, mode=payload.mode, use_rerank=payload.rerank,
                                top_k=payload.top_k, tracker=tracker)
    return {
        "results": [
            {"source": p.source, "section": p.section, "ranks": p.ranks, "rrf_score": round(p.score, 5),
             "snippet": p.content.split("\n\n", 1)[-1][:400]}
            for p in passages
        ],
        "usage": tracker.summary(),
    }
