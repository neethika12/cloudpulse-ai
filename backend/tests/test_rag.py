"""Knowledge-base chunking, incremental ingestion and hybrid retrieval.
Runs on SQLite (in-Python retrievers) with the fake embedding client."""
from app.models import KnowledgeChunk
from app.services import knowledge_base, llm, retrieval
from app.services.retrieval import Passage
from tests.fakes import FakeOpenAI

DOC = """# Widget Costs

Intro paragraph about widgets.

## Small widgets

Small widgets are cheap.

## Large widgets

""" + ("Large widgets are expensive. " * 80).strip()


def test_chunk_markdown_is_heading_aware_with_context_headers():
    chunks = knowledge_base.chunk_markdown(DOC, "widgets.md")
    assert chunks[0].section == "Overview"
    assert chunks[1].section == "Small widgets"
    assert chunks[1].content.startswith("Widget Costs > Small widgets\n\n")
    large = [c for c in chunks if c.section == "Large widgets"]
    assert len(large) >= 2  # oversized paragraph is split
    assert all(len(c.content.split("\n\n", 1)[1]) <= knowledge_base.MAX_CHARS for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_every_guide_chunks_cleanly():
    chunks = knowledge_base.load_documents()
    sources = {c.source for c in chunks}
    assert len(sources) >= 9
    assert all(c.title and c.section for c in chunks)
    assert len({c.content_hash for c in chunks}) == len(chunks)


def test_ingest_is_incremental(db, use_fake_openai, monkeypatch):
    fake = use_fake_openai(FakeOpenAI())
    first = knowledge_base.ingest(db)
    assert first["added"] > 0 and first["removed"] == 0

    embedded = len(fake.embedding_inputs)
    second = knowledge_base.ingest(db)
    assert second == {"added": 0, "unchanged": first["added"], "removed": 0}
    assert len(fake.embedding_inputs) == embedded  # nothing re-embedded

    original = knowledge_base.load_documents()
    edited = original[:-1] + [knowledge_base.Chunk("new.md", "New", "Overview", 0, "New > Overview\n\nfresh text")]
    monkeypatch.setattr(knowledge_base, "load_documents", lambda: edited)
    third = knowledge_base.ingest(db)
    assert third["added"] == 1 and third["removed"] == 1
    assert db.query(KnowledgeChunk).count() == len(edited)


def test_rrf_rewards_agreement_between_retrievers():
    fused = retrieval.reciprocal_rank_fusion({
        "vector": [Passage(1, "1.md", "t", "s", "x"), Passage(2, "2.md", "t", "s", "x")],
        "keyword": [Passage(2, "2.md", "t", "s", "x"), Passage(3, "3.md", "t", "s", "x")],
    })
    assert [p.id for p in fused] == [2, 1, 3]
    assert fused[0].ranks == {"vector": 2, "keyword": 1}


def test_rerank_reorders_and_never_drops_passages(use_fake_openai):
    passages = [Passage(i, f"{i}.md", "t", "s", f"passage {i}") for i in (1, 2, 3)]
    use_fake_openai(FakeOpenAI(rerank=lambda prompt, n: [3, 1]))
    assert [p.id for p in retrieval.rerank("q", passages, None)] == [3, 1, 2]

    class Broken(FakeOpenAI):
        def _chat(self, **kwargs):
            raise ValueError("bad json")

    use_fake_openai(Broken())
    assert [p.id for p in retrieval.rerank("q", passages, None)] == [1, 2, 3]


def test_hybrid_search_finds_the_right_guide(db, use_fake_openai):
    use_fake_openai(FakeOpenAI())
    knowledge_base.ingest(db)
    tracker = llm.UsageTracker()

    cases = {
        "NAT gateway data processing charges": "networking-and-data-transfer.md",
        "Glacier Deep Archive minimum storage duration": "s3-storage-optimization.md",
        "Spot instance two-minute interruption notice": "spot-instances.md",
    }
    for query, expected in cases.items():
        for mode in retrieval.MODES:
            results = retrieval.search(db, query, mode=mode, use_rerank=False, tracker=tracker)
            assert results[0].source == expected, (query, mode, [r.source for r in results])

    assert all(c["kind"] == "embedding" for c in tracker.calls)


def test_keyword_search_ignores_stopword_only_queries(db, use_fake_openai):
    use_fake_openai(FakeOpenAI())
    knowledge_base.ingest(db)
    assert retrieval.keyword_search(db, "what is the", 5) == []


def test_cost_pricing_uses_longest_prefix():
    assert llm.cost_usd("gpt-4o-mini-2024-07-18", 1_000_000, 0) == 0.15
    assert llm.cost_usd("gpt-4o-2024-08-06", 1_000_000, 0) == 2.50
    assert llm.cost_usd("some-future-model", 10, 10) is None


def test_keyword_only_mode_without_embedding_model(monkeypatch):
    """With OPENAI_EMBEDDING_MODEL blank the knowledge base indexes and searches with
    no embedding calls at all."""
    from app.config import settings
    from app.services import knowledge_base, retrieval
    from tests.conftest import TestingSessionLocal, engine
    from app.database import Base

    monkeypatch.setattr(settings, "openai_embedding_model", "")
    assert not settings.embeddings_enabled

    def boom(*a, **k):
        raise AssertionError("embeddings must not be called in keyword-only mode")

    monkeypatch.setattr("app.services.llm.embed", boom)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        knowledge_base.ingest(db)
        hits = retrieval.search(db, "NAT gateway data processing cost", mode="hybrid", use_rerank=False)
        assert hits and any("NAT" in h.content for h in hits)
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
