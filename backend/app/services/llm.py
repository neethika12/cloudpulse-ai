"""Thin layer over the OpenAI client that records tokens, cost and latency for every
call. Chat, embeddings, reranking and eval judging all go through here, so one
UsageTracker per request gives an exact cost breakdown for that request."""
import json
import time
from dataclasses import dataclass, field
from typing import Iterator

from openai import AzureOpenAI, OpenAI

from app.config import settings

# USD per 1M tokens (input, output). List prices at time of writing - update them if
# OpenAI changes pricing. Add other models with OPENAI_PRICING_OVERRIDES in .env;
# models priced nowhere are tracked with cost_usd = None.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}


class LLMNotConfigured(Exception):
    """Raised when no OpenAI / Azure OpenAI credentials are set."""


NOT_CONFIGURED_MESSAGE = (
    "OPENAI_API_KEY is not set (or, for Azure OpenAI, AZURE_OPENAI_ENDPOINT and "
    "AZURE_OPENAI_API_KEY). Add them to backend/.env and restart the backend."
)


def azure_v1_base_url(endpoint: str) -> str | None:
    """Accepts whatever the Azure portal shows (".../openai/v1/responses",
    ".../openai/v1/", ...) and returns the ".../openai/v1/" base URL, or None for a
    plain resource endpoint (which uses the older api-version style client)."""
    marker = "/openai/v1"
    if marker not in endpoint:
        return None
    return endpoint[: endpoint.index(marker)].rstrip("/") + marker + "/"


# Reasoning-style models (gpt-5 family, o-series, and newer) reject a custom
# temperature; only these classic chat families accept one.
_TEMPERATURE_PREFIXES = ("gpt-4", "gpt-3.5")


def _sampling(model: str, temperature: float) -> dict:
    send = settings.llm_send_temperature
    if send is None:
        send = model.lower().startswith(_TEMPERATURE_PREFIXES)
    return {"temperature": temperature} if send else {}


def is_configured() -> bool:
    if settings.use_azure:
        return bool(settings.azure_openai_api_key)
    return bool(settings.openai_api_key)


def get_client() -> OpenAI:
    if not is_configured():
        raise LLMNotConfigured(NOT_CONFIGURED_MESSAGE)
    if settings.use_azure:
        base_url = azure_v1_base_url(settings.azure_openai_endpoint)
        if base_url:
            # Azure's v1 API: a plain OpenAI client pointed at .../openai/v1/. The
            # `model` argument of every call is the deployment name.
            return OpenAI(base_url=base_url, api_key=settings.azure_openai_api_key)
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    return OpenAI(api_key=settings.openai_api_key)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    # Longest prefix wins, so dated snapshots ("gpt-4o-2024-08-06") price as their family
    # and "gpt-4o-mini" is not priced as "gpt-4o".
    prices = {**PRICING_PER_MTOK, **settings.openai_pricing_overrides}
    matches = [name for name in prices if model.startswith(name)]
    if not matches:
        return None
    price_in, price_out = prices[max(matches, key=len)]
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


@dataclass
class UsageTracker:
    calls: list[dict] = field(default_factory=list)

    def record(self, kind: str, model: str, prompt_tokens: int, completion_tokens: int, latency_ms: float):
        self.calls.append({
            "kind": kind,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms),
            "cost_usd": cost_usd(model, prompt_tokens, completion_tokens),
        })

    @property
    def prompt_tokens(self) -> int:
        return sum(c["prompt_tokens"] for c in self.calls)

    @property
    def completion_tokens(self) -> int:
        return sum(c["completion_tokens"] for c in self.calls)

    @property
    def cost_usd(self) -> float | None:
        costs = [c["cost_usd"] for c in self.calls]
        if any(c is None for c in costs):
            return None
        return round(sum(costs), 6)

    def summary(self) -> dict:
        return {
            "llm_calls": len(self.calls),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
        }


def embed(texts: list[str], tracker: UsageTracker | None = None, batch_size: int = 100) -> list[list[float]]:
    client = get_client()
    model = settings.openai_embedding_model
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        start = time.perf_counter()
        extra = {"dimensions": settings.embedding_dimensions} if settings.embedding_supports_dimensions else {}
        response = client.embeddings.create(model=model, input=batch, **extra)
        if tracker:
            tracker.record("embedding", model, response.usage.prompt_tokens, 0, (time.perf_counter() - start) * 1000)
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
    return vectors


def complete_json(messages: list[dict], model: str, tracker: UsageTracker | None, kind: str) -> dict:
    """Single non-streaming call in JSON mode. Used for reranking and eval judging."""
    client = get_client()
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **_sampling(model, 0),
        response_format={"type": "json_object"},
    )
    if tracker and response.usage:
        tracker.record(kind, model, response.usage.prompt_tokens, response.usage.completion_tokens,
                       (time.perf_counter() - start) * 1000)
    return json.loads(response.choices[0].message.content or "{}")


@dataclass
class StreamedTurn:
    """What one streamed chat completion produced, once fully consumed."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)


def _stream_chat_completions(messages: list[dict], tools: list[dict], tracker: UsageTracker,
                             turn: StreamedTurn) -> Iterator[str]:
    """Streams one chat completion, yielding text deltas as they arrive. Tool-call
    fragments are reassembled into `turn.tool_calls`, and usage is recorded on the
    tracker from the final chunk (stream_options.include_usage)."""
    client = get_client()
    model = settings.openai_model
    start = time.perf_counter()
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        **_sampling(model, 0.2),
        stream=True,
        stream_options={"include_usage": True},
    )
    partial: dict[int, dict] = {}
    usage = None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            turn.content += delta.content
            yield delta.content
        for tc in delta.tool_calls or []:
            slot = partial.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function and tc.function.name:
                slot["name"] += tc.function.name
            if tc.function and tc.function.arguments:
                slot["arguments"] += tc.function.arguments

    turn.tool_calls = [partial[i] for i in sorted(partial)]
    if usage:
        tracker.record("chat", model, usage.prompt_tokens, usage.completion_tokens,
                       (time.perf_counter() - start) * 1000)


def _use_responses_api(model: str) -> bool:
    mode = settings.llm_chat_api
    if mode in ("chat", "responses"):
        return mode == "responses"
    return not model.lower().startswith(_TEMPERATURE_PREFIXES)


def _to_responses_input(messages: list[dict]) -> tuple[str, list[dict]]:
    """Converts chat-completions style history into (instructions, Responses input items)."""
    instructions: list[str] = []
    items: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            instructions.append(m["content"])
        elif role == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
        elif role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                items.append({"role": "assistant", "content": m["content"]})
            for call in m["tool_calls"]:
                items.append({"type": "function_call", "call_id": call["id"],
                              "name": call["function"]["name"], "arguments": call["function"]["arguments"]})
        else:
            items.append({"role": role, "content": m["content"]})
    return "\n\n".join(instructions), items


def _stream_responses(messages: list[dict], tools: list[dict], tracker: UsageTracker,
                      turn: StreamedTurn) -> Iterator[str]:
    """Same contract as _stream_chat_completions, but over the Responses API."""
    client = get_client()
    model = settings.openai_model
    start = time.perf_counter()
    instructions, items = _to_responses_input(messages)
    flat_tools = [{"type": "function", "name": t["function"]["name"],
                   "description": t["function"].get("description", ""),
                   "parameters": t["function"]["parameters"]} for t in tools]
    stream = client.responses.create(
        model=model, instructions=instructions, input=items, tools=flat_tools,
        stream=True, store=False,
    )
    usage = None
    for event in stream:
        kind = event.type
        if kind == "response.output_text.delta":
            turn.content += event.delta
            yield event.delta
        elif kind == "response.output_item.done" and event.item.type == "function_call":
            turn.tool_calls.append({"id": event.item.call_id, "name": event.item.name,
                                    "arguments": event.item.arguments})
        elif kind == "response.completed":
            usage = event.response.usage
        elif kind in ("response.failed", "response.incomplete", "error"):
            detail = getattr(getattr(event, "response", None), "error", None) or getattr(event, "message", kind)
            raise RuntimeError(f"Model response did not complete: {detail}")
    if usage:
        tracker.record("chat", model, usage.input_tokens, usage.output_tokens,
                       (time.perf_counter() - start) * 1000)


def stream_chat(messages: list[dict], tools: list[dict], tracker: UsageTracker,
                turn: StreamedTurn) -> Iterator[str]:
    """Streams one agent turn, yielding text deltas. Fills `turn.tool_calls` and records
    usage. Uses /chat/completions or /responses depending on the model (LLM_CHAT_API)."""
    impl = _stream_responses if _use_responses_api(settings.openai_model) else _stream_chat_completions
    yield from impl(messages, tools, tracker, turn)
