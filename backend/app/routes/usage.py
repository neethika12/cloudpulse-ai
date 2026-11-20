from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatTrace, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


@router.get("/usage")
def usage(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Token, cost and latency stats for the current user's chat requests."""
    traces = db.query(ChatTrace).filter(ChatTrace.user_id == user.id).order_by(ChatTrace.created_at.desc(), ChatTrace.id.desc()).all()
    latencies = [t.latency_ms for t in traces if t.status == "ok"]
    tools = Counter(step["name"] for t in traces for step in (t.steps or []))
    known_costs = [t.cost_usd for t in traces if t.cost_usd is not None]

    return {
        "summary": {
            "requests": len(traces),
            "errors": sum(1 for t in traces if t.status != "ok"),
            "prompt_tokens": sum(t.prompt_tokens for t in traces),
            "completion_tokens": sum(t.completion_tokens for t in traces),
            "cost_usd": round(sum(known_costs), 4),
            "unpriced_requests": len(traces) - len(known_costs),
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "avg_tool_calls": round(sum(len(t.steps or []) for t in traces) / len(traces), 2) if traces else 0,
            "cited_answers": sum(1 for t in traces if t.citations),
        },
        "tools": [{"name": name, "calls": count} for name, count in tools.most_common()],
        "recent": [
            {
                "id": t.id,
                "question": t.question,
                "status": t.status,
                "model": t.model,
                "tools": [step["name"] for step in (t.steps or [])],
                "citations": len(t.citations or []),
                "tokens": t.prompt_tokens + t.completion_tokens,
                "cost_usd": t.cost_usd,
                "latency_ms": t.latency_ms,
                "created_at": t.created_at.isoformat(),
            }
            for t in traces[:limit]
        ],
    }
