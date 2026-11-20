import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import ChatTrace, User
from app.routes.auth import get_current_user
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_agent, llm

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _require_llm() -> None:
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail=llm.NOT_CONFIGURED_MESSAGE)


def _check_rate_limit(db: Session, user: User) -> None:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    recent = db.query(ChatTrace).filter(ChatTrace.user_id == user.id, ChatTrace.created_at >= since).count()
    if recent >= settings.chat_requests_per_hour:
        raise HTTPException(
            status_code=429,
            detail=f"Chat limit reached ({settings.chat_requests_per_hour} questions per hour). Try again later.",
        )


@router.post("/ask", response_model=ChatResponse)
def ask(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_llm()
    _check_rate_limit(db, user)
    history = [m.model_dump() for m in payload.history]
    try:
        return chat_agent.answer_question(db, user, payload.question, history)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/stream")
def stream(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Server-Sent Events: tool_call, tool_result, token, then done (or error)."""
    _require_llm()
    _check_rate_limit(db, user)
    history = [m.model_dump() for m in payload.history]

    def events():
        for event in chat_agent.run_chat(db, user, payload.question, history):
            event.pop("output", None)  # full tool results stay server-side
            yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
