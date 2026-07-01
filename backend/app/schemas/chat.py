from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


class IndexResponse(BaseModel):
    indexed: int
