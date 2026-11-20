"""Offline evaluation for CloudPulse's RAG and chat agent.

    docker compose exec backend python -m evals.run                 # full run, writes evals/results/
    docker compose exec backend python -m evals.run --retrieval-only
    docker compose exec backend python -m evals.run --no-baseline   # skip the full-context comparison
    docker compose exec backend python -m evals.run --check         # exit 1 if below evals/thresholds.json

Part 1, retrieval ablation. Two question sets:
  * golden_retrieval.jsonl - questions phrased the way the guides are written;
  * golden_retrieval_hard.jsonl - paraphrases that avoid the guides' vocabulary, where
    keyword search should struggle and embeddings should earn their keep.
Each runs through every retrieval configuration the current setup supports (keyword,
keyword+rerank, and, when an embedding model is configured, vector, hybrid and
hybrid+rerank), scored with hit@1, hit@k, recall@k and MRR at document level.

Part 2, end-to-end answers. Every question in golden_answers.jsonl goes through the real
agent twice: once with RAG (the search tool) and once with the whole knowledge base in
the prompt and no retrieval. With a corpus this small, the full-context arm is a real
alternative, so RAG has to beat or match it on quality and cost to justify itself. An
LLM judge scores faithfulness (are the claims supported by what that arm's model
actually saw?) and correctness (does it match the reference?). For data questions the
reference is computed from the database, so it stays right whatever data is loaded.
"""
import argparse
import json
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Anomaly, CloudAccount, CostRecord, User
from app.services import chat_agent, knowledge_base, llm, retrieval
from app.services.anomaly_service import detect_anomalies
from app.services.auth_service import hash_password
from app.services.mock_data import seed_mock_data
from evals.metrics import summarize

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
QUESTION_SETS = {"standard": "golden_retrieval.jsonl", "hard": "golden_retrieval_hard.jsonl"}
CONFIGS = [  # name, mode, rerank, needs embeddings
    ("keyword", "keyword", False, False),
    ("keyword+rerank", "keyword", True, False),
    ("vector", "vector", False, True),
    ("hybrid", "hybrid", False, True),
    ("hybrid+rerank", "hybrid", True, True),
]
ARMS = {"rag": "RAG (search tool)", "full_context": "Full context (no retrieval)"}
EVAL_USER_EMAIL = "eval@cloudpulse.local"

JUDGE_PROMPT = """You grade answers from a cloud-cost assistant. Return JSON:
{"faithfulness": <1-5>, "correctness": <1-5>, "reason": "<one sentence>"}

faithfulness: are the answer's factual claims (numbers, dates, AWS facts) supported by CONTEXT, which holds the tool outputs and knowledge-base passages the assistant had available? 5 = everything supported, 3 = some unsupported claims, 1 = mostly invented.
correctness: does the answer address the QUESTION and agree with the REFERENCE? 5 = complete and correct, 3 = partially, 1 = wrong or missing. Extra correct detail is fine.
Ignore tone, formatting and length. Citation markers like [K1] are expected."""


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (EVAL_DIR / name).read_text().splitlines() if line.strip()]


def production_config() -> str:
    """The retrieval configuration the app itself uses with the current settings."""
    base = "hybrid" if settings.embeddings_enabled else "keyword"
    return f"{base}+rerank" if settings.rag_rerank else base


def _cache_embeddings():
    """Each retrieval config embeds the same questions; embed each one only once.
    Returns the original function so the caller can restore it."""
    original, cache = llm.embed, {}

    def cached(texts, tracker=None, batch_size=100):
        if len(texts) != 1:
            return original(texts, tracker, batch_size)
        if texts[0] not in cache:
            cache[texts[0]] = original(texts, tracker, batch_size)[0]
        return [cache[texts[0]]]

    llm.embed = cached
    return original


# ---------- part 1: retrieval ----------

def eval_retrieval(db: Session, k: int, tracker: llm.UsageTracker) -> dict:
    """{question_set: {config: {"metrics": ..., "rows": ...} | {"skipped": reason}}}"""
    results: dict[str, dict] = {}
    for set_name, filename in QUESTION_SETS.items():
        cases = _load(filename)
        print(f"  {set_name} set ({len(cases)} questions)")
        results[set_name] = {}
        for name, mode, rerank, needs_embeddings in CONFIGS:
            if needs_embeddings and not settings.embeddings_enabled:
                results[set_name][name] = {"skipped": "no embedding model configured"}
                continue
            rows = []
            for case in cases:
                passages = retrieval.search(db, case["question"], mode=mode, use_rerank=rerank,
                                            top_k=k, tracker=tracker)
                rows.append({"question": case["question"], "relevant": set(case["relevant"]),
                             "retrieved": [p.source for p in passages]})
            results[set_name][name] = {"metrics": summarize(rows, k), "rows": rows}
            print(f"    {name:<15} {results[set_name][name]['metrics']}")
    return results


# ---------- part 2: answers ----------

def _eval_user(db: Session) -> User:
    user = db.query(User).filter_by(email=EVAL_USER_EMAIL).first()
    if user is None:
        user = User(email=EVAL_USER_EMAIL, hashed_password=hash_password(str(random.random())), full_name="Eval runner")
        db.add(user)
        db.commit()
    return user


def _ensure_demo_data(db: Session) -> None:
    """Demo cost data with anomalies, so the anomaly questions have something to find."""
    demo_ids = [a.id for a in db.query(CloudAccount.id).filter(CloudAccount.user_id.is_(None))]
    has_costs = demo_ids and db.query(CostRecord.id).filter(CostRecord.account_id.in_(demo_ids)).first()
    if not has_costs:
        print("  no demo cost data found, seeding it (seed 42)")
        random.seed(42)
        seed_mock_data(db)
        demo_ids = [a.id for a in db.query(CloudAccount.id).filter(CloudAccount.user_id.is_(None))]
    if not db.query(Anomaly.id).filter(Anomaly.account_id.in_(demo_ids)).first():
        print("  no anomalies stored, running anomaly detection")
        detect_anomalies(db)


def _data_reference(db: Session, user: User, case_id: str) -> str:
    ids = chat_agent.accessible_account_ids(db, user)
    if case_id == "top-service":
        top = chat_agent.run_tool(db, ids, "get_cost_summary", {})["services"][0]
        return f"{top['service']} costs the most, ${top['total_usd']:,.2f} in total."
    if case_id == "last-7-days":
        start = (date.today() - timedelta(days=6)).isoformat()
        total = chat_agent.run_tool(db, ids, "get_cost_summary", {"start_date": start})["grand_total_usd"]
        return f"Total spend from {start} to today is ${total:,.2f}."
    anomalies = chat_agent.run_tool(db, ids, "get_anomalies", {})["anomalies"]
    if case_id == "anomalies":
        if not anomalies:
            return "There are no anomalies."
        return "Anomalies: " + "; ".join(f"{a['service']} on {a['date']} (${a['usd']:,.2f})" for a in anomalies)
    if case_id == "spike-advice" and anomalies:
        biggest = max(anomalies, key=lambda a: a["usd"])
        return f"Biggest anomaly: {biggest['service']} on {biggest['date']} (${biggest['usd']:,.2f}). "
    return ""


def _run_agent(db: Session, user: User, question: str, arm: str) -> dict:
    # The model's system prompt states today's date and the data's date range; without
    # them the judge marks answers that mention those facts as unsupported.
    ids = chat_agent.accessible_account_ids(db, user)
    contexts = [{"system_prompt_facts": f"Today's date is {date.today().isoformat()}. "
                                        f"{chat_agent._data_range(db, ids)}"}]
    done = None
    for event in chat_agent.run_chat(db, user, question, knowledge_mode=arm):
        if event["type"] == "tool_result":
            contexts.append({"tool": event["name"], "args": event["args"], "output": event["output"]})
        elif event["type"] == "done":
            done = event
        elif event["type"] == "error":
            raise RuntimeError(event["detail"])
    if arm == "full_context":
        # The judge must see what the model saw: the whole knowledge base was in its prompt.
        contexts.append({"knowledge_base_in_prompt": [c.content for c in knowledge_base.load_documents()]})
    return {"answer": done["answer"], "citations": done["citations"], "contexts": contexts, "usage": done["usage"]}


def _judge(question: str, reference: str, contexts: list[dict], answer: str, tracker: llm.UsageTracker) -> dict:
    context = json.dumps(contexts)[:80_000]
    result = llm.complete_json(
        [{"role": "system", "content": JUDGE_PROMPT},
         {"role": "user", "content": f"QUESTION:\n{question}\n\nREFERENCE:\n{reference}\n\nCONTEXT:\n{context}\n\nANSWER:\n{answer}"}],
        settings.openai_judge_model, tracker, kind="judge",
    )
    scale = lambda v: round((min(max(float(v), 1), 5) - 1) / 4, 3)  # 1-5 -> 0-1
    return {"faithfulness": scale(result.get("faithfulness", 1)),
            "correctness": scale(result.get("correctness", 1)),
            "reason": result.get("reason", "")}


def _summarize_arm(rows: list[dict]) -> dict:
    n = len(rows) or 1
    needing = [r for r in rows if r["cited"] is not None]
    costs = [r["cost_usd"] for r in rows]
    return {
        "faithfulness": round(sum(r["faithfulness"] for r in rows) / n, 3),
        "correctness": round(sum(r["correctness"] for r in rows) / n, 3),
        "citation_rate": round(sum(r["cited"] for r in needing) / len(needing), 3) if needing else None,
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n),
        "avg_tokens": round(sum(r["tokens"] for r in rows) / n),
        "avg_cost_usd": None if any(c is None for c in costs) else round(sum(costs) / n, 5),
    }


def eval_answers(db: Session, arms: list[str], tracker: llm.UsageTracker) -> dict:
    """{arm: {"metrics": ..., "rows": [...]}}"""
    _ensure_demo_data(db)
    user = _eval_user(db)
    cases = _load("golden_answers.jsonl")
    results = {}
    for arm in arms:
        print(f"  {ARMS[arm]}")
        rows = []
        for case in cases:
            reference = _data_reference(db, user, case["id"]) + case.get("reference", "")
            started = time.perf_counter()
            run = _run_agent(db, user, case["question"], arm)
            latency = round((time.perf_counter() - started) * 1000)
            scores = _judge(case["question"], reference, run["contexts"], run["answer"], tracker)
            needs_citation = case["kind"] in ("knowledge", "mixed")
            usage = run["usage"]
            rows.append({
                "id": case["id"], "kind": case["kind"], "question": case["question"], "reference": reference,
                "answer": run["answer"], "tools": [c["tool"] for c in run["contexts"] if "tool" in c],
                "citations": [c["source"] for c in run["citations"]],
                "cited": bool(run["citations"]) if needs_citation else None,
                "latency_ms": latency, "tokens": usage["prompt_tokens"] + usage["completion_tokens"],
                "cost_usd": usage["cost_usd"], **scores,
            })
            print(f"    {case['id']:<16} faith={scores['faithfulness']:.2f} correct={scores['correctness']:.2f} "
                  f"tools={rows[-1]['tools']} cited={rows[-1]['cited']} tokens={rows[-1]['tokens']}")
        results[arm] = {"metrics": _summarize_arm(rows), "rows": rows}
    return results


# ---------- report ----------

def _cell(value, fmt="{:.2f}") -> str:
    return "-" if value is None else fmt.format(value)


def write_report(retrieval_results: dict, answer_results: dict | None, k: int, tracker: llm.UsageTracker) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    prod = production_config()
    lines = [
        "# CloudPulse eval report", "",
        f"Run {date.today().isoformat()} · chat `{settings.openai_model}` · embeddings "
        f"`{settings.openai_embedding_model or 'none (keyword-only)'}` · rerank `{settings.openai_rerank_model}` "
        f"· judge `{settings.openai_judge_model}`" + (" · Azure OpenAI" if settings.use_azure else ""), "",
    ]
    if settings.openai_judge_model == settings.openai_model:
        lines += ["> **Self-grading:** the judge is the same model as the chat model, and models tend to "
                  "rate their own answers generously. Set `OPENAI_JUDGE_MODEL` to a different model for "
                  "an independent judge, and spot-check a few scores by hand.", ""]

    lines += [f"## Retrieval (k={k}, scored by source guide)", "",
              f"The app currently uses **{prod}**. *Hard* questions are paraphrases that avoid the guides' wording.", "",
              f"| Config | Set | hit@1 | hit@{k} | recall@{k} | MRR |", "|---|---|---|---|---|---|"]
    for name, *_ in CONFIGS:
        for set_name in QUESTION_SETS:
            result = retrieval_results[set_name][name]
            label = f"**{name}**" if name == prod else name
            if "skipped" in result:
                lines.append(f"| {label} | {set_name} | skipped: {result['skipped']} | | | |")
                continue
            m = result["metrics"]
            lines.append(f"| {label} | {set_name} | {m['hit@1']:.2f} | {m[f'hit@{k}']:.2f} | "
                         f"{m[f'recall@{k}']:.2f} | {m['mrr']:.2f} |")

    for set_name in QUESTION_SETS:
        misses = [r for r in retrieval_results[set_name][prod]["rows"] if not set(r["retrieved"][:k]) & r["relevant"]]
        if misses:
            lines += ["", f"Misses for {prod} on the {set_name} set (no relevant guide in the top {k}):", ""]
            lines += [f"- {r['question']} (expected `{', '.join(sorted(r['relevant']))}`, "
                      f"got `{', '.join(dict.fromkeys(r['retrieved'])) or 'nothing'}`)" for r in misses]

    if answer_results:
        n = len(next(iter(answer_results.values()))["rows"])
        lines += ["", f"## Answers ({n} questions, judged by `{settings.openai_judge_model}`)", "",
                  "| Arm | Faithfulness | Correctness | Citation rate | Avg latency | Avg tokens | Avg cost |",
                  "|---|---|---|---|---|---|---|"]
        for arm, result in answer_results.items():
            m = result["metrics"]
            lines.append(f"| {ARMS[arm]} | {m['faithfulness']:.2f} | {m['correctness']:.2f} | "
                         f"{_cell(m['citation_rate'])} | {m['avg_latency_ms'] / 1000:.1f}s | {m['avg_tokens']:,} | "
                         f"{_cell(m['avg_cost_usd'], '${:.4f}')} |")
        for arm, result in answer_results.items():
            lines += ["", f"### {ARMS[arm]}", "",
                      "| Case | Kind | Faithful | Correct | Tools | Cited | Judge's reason |", "|---|---|---|---|---|---|---|"]
            for r in result["rows"]:
                cited = "-" if r["cited"] is None else ("yes" if r["cited"] else "no")
                lines.append(f"| {r['id']} | {r['kind']} | {r['faithfulness']:.2f} | {r['correctness']:.2f} | "
                             f"{', '.join(r['tools']) or '-'} | {cited} | {r['reason'].replace('|', '/')} |")
            lines += ["", "<details><summary>Full answers, for checking the judge by hand</summary>", ""]
            for r in result["rows"]:
                lines += [f"**{r['id']}**: {r['question']}", "", f"> Reference: {r['reference']}", "",
                          r["answer"], "", "---", ""]
            lines += ["</details>"]

    cost = tracker.cost_usd
    lines += ["", f"Retrieval, rerank and judge calls: {len(tracker.calls)}"
                  + (f", ${cost:.4f}" if cost is not None else " (some models unpriced)")
                  + ". Chat calls are counted per arm above and saved in chat_traces."]

    report = RESULTS_DIR / "report.md"
    report.write_text("\n".join(lines) + "\n")
    serializable = {
        "settings": {"chat_model": settings.openai_model, "embedding_model": settings.openai_embedding_model,
                     "rerank_model": settings.openai_rerank_model, "judge_model": settings.openai_judge_model,
                     "production_config": prod, "k": k},
        "retrieval": {
            set_name: {name: r if "skipped" in r else
                       {"metrics": r["metrics"], "rows": [{**row, "relevant": sorted(row["relevant"])} for row in r["rows"]]}
                       for name, r in configs.items()}
            for set_name, configs in retrieval_results.items()
        },
        "answers": answer_results,
    }
    (RESULTS_DIR / "results.json").write_text(json.dumps(serializable, indent=2))
    return report


def check_thresholds(retrieval_results: dict, answer_results: dict | None) -> list[str]:
    """Retrieval thresholds apply to the configuration the app actually uses on the
    standard set; answer thresholds to the RAG arm."""
    thresholds = json.loads((EVAL_DIR / "thresholds.json").read_text())
    prod = production_config()
    failures = []
    for metric, minimum in thresholds["retrieval"].items():
        value = retrieval_results["standard"][prod]["metrics"].get(metric)
        if value is None or value < minimum:
            failures.append(f"retrieval {prod} {metric} = {value} < {minimum}")
    if answer_results and "rag" in answer_results:
        for metric, minimum in thresholds["answers"].items():
            value = answer_results["rag"]["metrics"].get(metric)
            if value is not None and value < minimum:
                failures.append(f"answers (rag) {metric} = {value} < {minimum}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--no-baseline", action="store_true", help="skip the full-context answer arm")
    parser.add_argument("--check", action="store_true", help="exit 1 if any metric is below evals/thresholds.json")
    args = parser.parse_args(argv)

    if not llm.is_configured():
        print(llm.NOT_CONFIGURED_MESSAGE, file=sys.stderr)
        return 2

    tracker = llm.UsageTracker()
    original_embed = _cache_embeddings()
    db = SessionLocal()
    try:
        print("indexing knowledge base")
        print(" ", knowledge_base.ingest(db, tracker))
        print(f"retrieval ablation (app uses {production_config()})")
        retrieval_results = eval_retrieval(db, args.k, tracker)
        answer_results = None
        if not args.retrieval_only:
            print("end-to-end answers")
            arms = ["rag"] if args.no_baseline else ["rag", "full_context"]
            answer_results = eval_answers(db, arms, tracker)
        report = write_report(retrieval_results, answer_results, args.k, tracker)
        print(f"report written to {report}")
    finally:
        db.close()
        llm.embed = original_embed

    if args.check:
        failures = check_thresholds(retrieval_results, answer_results)
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        if failures:
            return 1
        print("all thresholds met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
