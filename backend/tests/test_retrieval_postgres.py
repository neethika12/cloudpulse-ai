"""Exercises the real Postgres retrievers (pgvector cosine distance + full-text search)
and the knowledge_chunks migration. Skipped unless DATABASE_URL points at Postgres,
as it does in CI (after `alembic upgrade head`) and inside the backend container.
Everything runs in a transaction that is rolled back, so no data is left behind."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.services import knowledge_base, retrieval
from tests.fakes import FakeOpenAI

pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"), reason="needs Postgres + pgvector"
)


@pytest.fixture()
def pg_session():
    engine = create_engine(settings.database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def test_postgres_hybrid_retrieval(pg_session, use_fake_openai):
    use_fake_openai(FakeOpenAI())
    pg_session.execute(knowledge_base.KnowledgeChunk.__table__.delete())
    knowledge_base.ingest(pg_session)

    query = "NAT gateway data processing charges"
    keyword = retrieval.keyword_search(pg_session, query, 5)
    assert keyword and keyword[0].source == "networking-and-data-transfer.md"

    for mode in retrieval.MODES:
        results = retrieval.search(pg_session, query, mode=mode, use_rerank=False)
        assert results[0].source == "networking-and-data-transfer.md", (mode, [r.source for r in results])
