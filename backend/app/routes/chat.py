from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, IndexResponse
from app.services.rag_service import index_cost_data, answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/index", response_model=IndexResponse)
def index(db: Session = Depends(get_db)):
    count = index_cost_data(db)
    return {"indexed": count}


@router.post("/ask", response_model=ChatResponse)
def ask(payload: ChatRequest, db: Session = Depends(get_db)):
    answer = answer_question(db, payload.question)
    return {"answer": answer}
