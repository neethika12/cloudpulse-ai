import json

from app.config import settings
from evals import metrics, run as eval_run
from tests.conftest import TestingSessionLocal
from tests.fakes import FakeOpenAI


def test_retrieval_metrics():
    retrieved = ["b.md", "a.md", "a.md", "c.md"]
    assert metrics.hit_at_k(retrieved, {"a.md"}, 1) == 0.0
    assert metrics.hit_at_k(retrieved, {"a.md"}, 2) == 1.0
    assert metrics.recall_at_k(retrieved, {"a.md", "c.md"}, 3) == 0.5
    assert metrics.reciprocal_rank(retrieved, {"c.md"}) == 1 / 3  # ranked by distinct source
    assert metrics.reciprocal_rank(retrieved, {"z.md"}) == 0.0


def _run_evals(use_fake_openai, monkeypatch, tmp_path, argv):
    fake = use_fake_openai(FakeOpenAI(judge={"faithfulness": 5, "correctness": 2, "reason": "misses the figure"}))
    monkeypatch.setattr(eval_run, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(eval_run, "RESULTS_DIR", tmp_path)
    exit_code = eval_run.main(argv)
    results = json.loads((tmp_path / "results.json").read_text())
    return exit_code, results, (tmp_path / "report.md").read_text(), fake


def test_full_eval_run_compares_arms_and_checks_thresholds(client, use_fake_openai, monkeypatch, tmp_path):
    exit_code, results, report, fake = _run_evals(use_fake_openai, monkeypatch, tmp_path, ["--check"])

    assert set(results["retrieval"]) == {"standard", "hard"}
    assert set(results["retrieval"]["standard"]) == {name for name, *_ in eval_run.CONFIGS}
    assert results["settings"]["production_config"] == "hybrid+rerank"
    assert "| **hybrid+rerank** | standard |" in report and "| keyword | hard |" in report

    # Both answer arms ran; the full-context arm never calls the search tool.
    assert set(results["answers"]) == {"rag", "full_context"}
    rag, full = results["answers"]["rag"], results["answers"]["full_context"]
    assert rag["metrics"]["faithfulness"] == 1.0 and rag["metrics"]["correctness"] == 0.25
    assert rag["metrics"]["citation_rate"] == 0.0  # the fake answer never cites
    assert all("search_knowledge_base" not in r["tools"] for r in full["rows"])
    full_prompts = [r["messages"][0]["content"] for r in fake.chat_requests if "KNOWLEDGE BASE:" in r["messages"][0]["content"]]
    assert len(full_prompts) == len(full["rows"])
    assert all(t["function"]["name"] != "search_knowledge_base"
               for r in fake.chat_requests if "KNOWLEDGE BASE:" in r["messages"][0]["content"] for t in r["tools"])

    # Data references are computed from the seeded database.
    top = next(r for r in rag["rows"] if r["id"] == "top-service")
    assert "costs the most, $" in top["reference"]
    assert "Full answers, for checking the judge by hand" in report
    anomalies = next(r for r in rag["rows"] if r["id"] == "anomalies")
    assert anomalies["reference"].startswith("Anomalies: ")  # detection ran, so there is something to find
    assert "Self-grading" not in report  # judge (gpt-4o-mini) differs from chat model (gpt-4o)
    assert exit_code == 1  # correctness and citation rate are below thresholds


def test_keyword_only_setup_skips_vector_configs(client, use_fake_openai, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "openai_embedding_model", "")
    monkeypatch.setattr(settings, "openai_judge_model", settings.openai_model)
    exit_code, results, report, fake = _run_evals(
        use_fake_openai, monkeypatch, tmp_path, ["--retrieval-only", "--check"])

    assert results["settings"]["production_config"] == "keyword+rerank"
    standard = results["retrieval"]["standard"]
    assert standard["vector"] == {"skipped": "no embedding model configured"}
    assert "metrics" in standard["keyword+rerank"]
    assert fake.embedding_inputs == []  # nothing was embedded
    assert "Self-grading" in report
    assert results["answers"] is None
    assert exit_code in (0, 1)


def test_eval_refuses_to_run_without_a_key(client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert eval_run.main([]) == 2
