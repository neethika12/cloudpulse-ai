"""Retrieval metrics at document level: a retrieved chunk counts as relevant when it
comes from one of the question's relevant source files."""


def _sources_in_order(retrieved: list[str]) -> list[str]:
    return list(dict.fromkeys(retrieved))


def hit_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(s in relevant for s in retrieved[:k]) else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, source in enumerate(_sources_in_order(retrieved), start=1):
        if source in relevant:
            return 1.0 / rank
    return 0.0


def summarize(rows: list[dict], k: int) -> dict:
    n = len(rows) or 1
    return {
        "hit@1": round(sum(hit_at_k(r["retrieved"], r["relevant"], 1) for r in rows) / n, 3),
        f"hit@{k}": round(sum(hit_at_k(r["retrieved"], r["relevant"], k) for r in rows) / n, 3),
        f"recall@{k}": round(sum(recall_at_k(r["retrieved"], r["relevant"], k) for r in rows) / n, 3),
        "mrr": round(sum(reciprocal_rank(r["retrieved"], r["relevant"]) for r in rows) / n, 3),
    }
