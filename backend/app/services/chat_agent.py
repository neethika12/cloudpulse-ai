"""Tool-calling chat agent: SQL tools for the user's numbers, hybrid RAG for advice.

The model gets two kinds of tools:
  * read-only SQL tools over the cost database, so every figure about the user's own
    spend comes from a query, scoped to the accounts that user can see;
  * search_knowledge_base, hybrid retrieval over the FinOps guides in backend/knowledge/,
    whose passages come back labelled [K1], [K2]... so the answer can cite them.

run_chat() yields events as they happen (tool_call, tool_result, token, done/error),
which the /stream endpoint forwards as Server-Sent Events and /ask collects. Every run
is saved as a ChatTrace with its tool steps, token usage, cost and latency.
"""
import json
import logging
import re
import time
from datetime import date
from typing import Iterator

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Anomaly, ChatTrace, CloudAccount, CostRecord, User
from app.services import knowledge_base, llm, retrieval

logger = logging.getLogger("cloudpulse")

MAX_TOOL_ROUNDS = 6
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 24_000  # roughly 6k tokens of prior conversation

# How the agent gets FinOps knowledge:
#   "rag"          - the search_knowledge_base tool (hybrid retrieval), the default;
#   "full_context" - every guide pasted into the system prompt, no retrieval. Used as
#                    the baseline in evals: with a corpus this small it is a real
#                    alternative, and RAG has to beat it to justify itself.
KNOWLEDGE_MODES = ("rag", "full_context")

# Kept for callers that catch the old name.
ChatNotConfigured = llm.LLMNotConfigured

FULL_CONTEXT_TOOLS_NOTE = (
    "The knowledge base is not a tool in this conversation: all of it is included below, "
    "and you should cite it by ref exactly the same way.\n\n"
)

SYSTEM_PROMPT = """You are CloudPulse AI, an assistant that helps people understand and reduce their AWS spend.
Today's date is {today}. Amounts are in USD. {data_range}

Tools:
- Cost tools (get_cost_summary, get_daily_costs, compare_periods, get_anomalies) query this user's real cost data. Use them for any number about the user's spend; never guess or invent figures.
- search_knowledge_base searches FinOps and AWS cost-optimization guides. Use it for "how", "why" and "what should I do" questions, and before recommending a fix.

Citations: when a sentence relies on a knowledge-base passage, put its ref right after the sentence, like [K2]. Only cite refs a search actually returned. Do not cite the cost tools. Prices in the guides are general list prices, not the user's bill; say so if you quote them.

{knowledge_block}Style: be concise, quote exact dollar amounts, and when asked about a spike, check daily costs and anomalies first, then explain what happened and suggest one or two practical next steps. If the data does not contain the answer, say so plainly."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_cost_summary",
            "description": "Total spend per AWS service between two dates, highest first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive. Omit for the beginning of the data."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive. Omit for today."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_costs",
            "description": "Daily spend for one service (or all services combined if service is omitted).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name such as EC2, S3, RDS."},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Compare total spend per service between two periods.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_a_start": {"type": "string"},
                    "period_a_end": {"type": "string"},
                    "period_b_start": {"type": "string"},
                    "period_b_end": {"type": "string"},
                },
                "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anomalies",
            "description": "Days flagged as unusual spend spikes by the anomaly detector.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search FinOps / AWS cost-optimization guides (rightsizing, Savings Plans, Spot, S3 storage "
                "classes, RDS, Lambda, data transfer, tagging, anomaly runbook). Returns passages with refs to cite."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "A focused search query, e.g. 'reduce NAT gateway data processing cost'."},
                },
                "required": ["query"],
            },
        },
    },
]


# ---------- account scoping ----------

def accessible_account_ids(db: Session, user: User) -> list[int]:
    """The user's own connected accounts once they hold cost data; otherwise the
    shared demo account(s). Never another user's account."""
    own = [a.id for a in db.query(CloudAccount.id).filter(CloudAccount.user_id == user.id)]
    if own and db.query(CostRecord.id).filter(CostRecord.account_id.in_(own)).first():
        return own
    return [a.id for a in db.query(CloudAccount.id).filter(CloudAccount.user_id.is_(None))]


# ---------- SQL tools ----------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _costs(db: Session, account_ids: list[int], start: date | None, end: date | None):
    query = db.query(CostRecord).filter(CostRecord.account_id.in_(account_ids))
    if start:
        query = query.filter(CostRecord.date >= start)
    if end:
        query = query.filter(CostRecord.date <= end)
    return query


def _totals(db: Session, account_ids: list[int], start: date | None, end: date | None) -> dict[str, float]:
    rows = (
        _costs(db, account_ids, start, end)
        .with_entities(CostRecord.service, func.sum(CostRecord.amount_usd))
        .group_by(CostRecord.service)
        .all()
    )
    return {service: round(total, 2) for service, total in rows}


def run_tool(db: Session, account_ids: list[int], name: str, args: dict) -> dict:
    if name == "get_cost_summary":
        totals = _totals(db, account_ids, _parse_date(args.get("start_date")), _parse_date(args.get("end_date")))
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return {
            "services": [{"service": s, "total_usd": t} for s, t in ranked],
            "grand_total_usd": round(sum(totals.values()), 2),
        }

    if name == "get_daily_costs":
        query = _costs(db, account_ids, _parse_date(args.get("start_date")), _parse_date(args.get("end_date")))
        service = args.get("service")
        if service:
            query = query.filter(func.lower(CostRecord.service) == service.lower())
        rows = (
            query.with_entities(CostRecord.date, func.sum(CostRecord.amount_usd))
            .group_by(CostRecord.date)
            .order_by(CostRecord.date)
            .all()
        )
        return {"days": [{"date": d.isoformat(), "usd": round(t, 2)} for d, t in rows][-120:]}

    if name == "compare_periods":
        a = _totals(db, account_ids, _parse_date(args["period_a_start"]), _parse_date(args["period_a_end"]))
        b = _totals(db, account_ids, _parse_date(args["period_b_start"]), _parse_date(args["period_b_end"]))
        result = []
        for service in sorted(set(a) | set(b)):
            before, after = a.get(service, 0.0), b.get(service, 0.0)
            change = round(after - before, 2)
            pct = round(change / before * 100, 1) if before else None
            result.append({"service": service, "period_a_usd": before, "period_b_usd": after,
                           "change_usd": change, "change_pct": pct})
        result.sort(key=lambda r: abs(r["change_usd"]), reverse=True)
        return {"comparison": result}

    if name == "get_anomalies":
        rows = (
            db.query(Anomaly)
            .filter(Anomaly.account_id.in_(account_ids))
            .order_by(Anomaly.date.desc())
            .all()
        )
        return {"anomalies": [{"service": r.service, "date": r.date.isoformat(), "usd": round(r.amount_usd, 2)} for r in rows]}

    return {"error": f"unknown tool {name}"}


def _summarize(name: str, result: dict) -> str:
    """One short line describing a tool result, for the UI trace."""
    if "error" in result:
        return f"error: {result['error']}"
    if name == "get_cost_summary":
        return f"{len(result['services'])} services, ${result['grand_total_usd']:,.2f} total"
    if name == "get_daily_costs":
        return f"{len(result['days'])} days"
    if name == "compare_periods":
        return f"{len(result['comparison'])} services compared"
    if name == "get_anomalies":
        return f"{len(result['anomalies'])} anomalies"
    if name == "search_knowledge_base":
        return f"{len(result['results'])} passages"
    return ""


# ---------- agent loop ----------

class _Sources:
    """Numbers knowledge-base passages [K1], [K2]... across every search in one answer."""

    def __init__(self):
        self.by_ref: dict[str, dict] = {}
        self._ref_for_id: dict[int, str] = {}

    def add(self, passage: retrieval.Passage) -> str:
        if passage.id not in self._ref_for_id:
            ref = f"K{len(self._ref_for_id) + 1}"
            self._ref_for_id[passage.id] = ref
            body = passage.content.split("\n\n", 1)[-1]
            self.by_ref[ref] = {"ref": ref, "source": passage.source, "title": passage.title,
                                "section": passage.section,
                                "snippet": body if len(body) <= 400 else body[:400].rsplit(" ", 1)[0] + "…"}
        return self._ref_for_id[passage.id]

    def cited_in(self, answer: str) -> list[dict]:
        refs = dict.fromkeys(re.findall(r"\[(K\d+)\]", answer))  # first-appearance order, deduped
        return [self.by_ref[r] for r in refs if r in self.by_ref]


def _search_tool(db: Session, args: dict, sources: _Sources, tracker: llm.UsageTracker) -> dict:
    query = str(args.get("query", "")).strip()[:300]
    if not query:
        return {"error": "query is required"}
    knowledge_base.ensure_indexed(db, tracker)
    passages = retrieval.search(db, query, tracker=tracker)
    return {"results": [
        {"ref": sources.add(p), "source": p.source, "section": p.section,
         "text": p.content.split("\n\n", 1)[-1]}
        for p in passages
    ]}


def _full_context_block(sources: _Sources) -> str:
    lines = ["KNOWLEDGE BASE:"]
    for i, chunk in enumerate(knowledge_base.load_documents(), start=1):
        passage = retrieval.Passage(i, chunk.source, chunk.title, chunk.section, chunk.content)
        lines.append(f"[{sources.add(passage)}] {chunk.content}")
    return "\n\n".join(lines) + "\n\n"


def _trim_history(history: list[dict]) -> list[dict]:
    """Most recent messages that fit both the message and the character budget."""
    kept, used = [], 0
    for m in reversed(history[-MAX_HISTORY_MESSAGES:]):
        if m.get("role") not in ("user", "assistant") or not m.get("content"):
            continue
        used += len(m["content"])
        if used > MAX_HISTORY_CHARS:
            break
        kept.append({"role": m["role"], "content": m["content"]})
    return list(reversed(kept))


def _data_range(db: Session, account_ids: list[int]) -> str:
    lo, hi = (
        db.query(func.min(CostRecord.date), func.max(CostRecord.date))
        .filter(CostRecord.account_id.in_(account_ids))
        .one()
    )
    if lo is None:
        return "No cost data is loaded yet."
    return f"The user's cost data covers {lo.isoformat()} to {hi.isoformat()}."


def run_chat(
    db: Session,
    user: User,
    question: str,
    history: list[dict] | None = None,
    knowledge_mode: str = "rag",
) -> Iterator[dict]:
    """Runs the agent and yields events. Always ends with a `done` or `error` event, and
    always records a ChatTrace, even if the caller stops consuming early."""
    if knowledge_mode not in KNOWLEDGE_MODES:
        raise ValueError(f"knowledge_mode must be one of {KNOWLEDGE_MODES}")
    started = time.perf_counter()
    tracker = llm.UsageTracker()
    sources = _Sources()
    steps: list[dict] = []
    answer, status = "", "error"
    account_ids = accessible_account_ids(db, user)

    if knowledge_mode == "full_context":
        tools = [t for t in TOOLS if t["function"]["name"] != "search_knowledge_base"]
        knowledge_block = FULL_CONTEXT_TOOLS_NOTE + _full_context_block(sources)
    else:
        tools, knowledge_block = TOOLS, ""
    system = SYSTEM_PROMPT.format(today=date.today().isoformat(), data_range=_data_range(db, account_ids),
                                  knowledge_block=knowledge_block)
    messages: list[dict] = [{"role": "system", "content": system}, *_trim_history(history or [])]
    messages.append({"role": "user", "content": question})

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            turn = llm.StreamedTurn()
            for text in llm.stream_chat(messages, tools, tracker, turn):
                yield {"type": "token", "text": text}

            if not turn.tool_calls:
                answer = turn.content.strip()
                break

            messages.append({
                "role": "assistant",
                "content": turn.content or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in turn.tool_calls
                ],
            })
            for call in turn.tool_calls:
                tool_started = time.perf_counter()
                try:
                    args = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_call", "id": call["id"], "name": call["name"], "args": args}
                try:
                    if call["name"] == "search_knowledge_base":
                        result = _search_tool(db, args, sources, tracker)
                    else:
                        result = run_tool(db, account_ids, call["name"], args)
                except Exception as exc:  # surface tool errors to the model instead of crashing
                    logger.exception("tool %s failed", call["name"])
                    result = {"error": str(exc)}
                step = {
                    "id": call["id"], "name": call["name"], "args": args,
                    "summary": _summarize(call["name"], result),
                    "latency_ms": round((time.perf_counter() - tool_started) * 1000),
                }
                if call["name"] == "search_knowledge_base" and "results" in result:
                    step["refs"] = [r["ref"] for r in result["results"]]
                steps.append(step)
                # `output` is the full tool result: evals judge faithfulness against it.
                # The SSE layer drops it before sending events to the browser.
                yield {"type": "tool_result", **step, "output": result}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
        else:
            answer = "I couldn't finish looking that up. Please try rephrasing the question."

        status = "ok"
        yield {
            "type": "done",
            "answer": answer,
            "citations": sources.cited_in(answer),
            "sources": list(sources.by_ref.values()),
            "steps": steps,
            "usage": {**tracker.summary(), "latency_ms": round((time.perf_counter() - started) * 1000)},
        }
    except llm.LLMNotConfigured:
        raise
    except Exception as exc:
        logger.exception("chat request failed")
        yield {"type": "error", "detail": "The AI provider request failed. Check the backend logs.",
               "error_class": type(exc).__name__}
    finally:
        _record_trace(db, user, question, answer, status, steps, sources.cited_in(answer), tracker, started)


def _record_trace(db, user, question, answer, status, steps, citations, tracker, started) -> None:
    try:
        db.add(ChatTrace(
            user_id=user.id, question=question, answer=answer, status=status,
            model=settings.openai_model, steps=steps,
            citations=[{"ref": c["ref"], "source": c["source"], "section": c["section"]} for c in citations],
            llm_calls=len(tracker.calls), prompt_tokens=tracker.prompt_tokens,
            completion_tokens=tracker.completion_tokens, cost_usd=tracker.cost_usd,
            latency_ms=round((time.perf_counter() - started) * 1000),
        ))
        db.commit()
    except Exception:
        logger.exception("could not save chat trace")
        db.rollback()


def answer_question(db: Session, user: User, question: str, history: list[dict] | None = None) -> dict:
    """Non-streaming wrapper: runs the agent to completion and returns the `done` event."""
    for event in run_chat(db, user, question, history):
        if event["type"] == "done":
            return event
        if event["type"] == "error":
            raise RuntimeError(event["detail"])
    raise RuntimeError("chat ended without an answer")
