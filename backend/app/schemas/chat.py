from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default=[], max_length=50)


class Citation(BaseModel):
    ref: str
    source: str
    title: str
    section: str
    snippet: str


class ToolStep(BaseModel):
    id: str
    name: str
    args: dict[str, Any]
    summary: str
    latency_ms: int
    refs: list[str] | None = None


class ChatUsage(BaseModel):
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    latency_ms: int


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    steps: list[ToolStep]
    usage: ChatUsage


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    rerank: bool = True
    top_k: int = Field(default=5, ge=1, le=20)
