import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# cost_embeddings uses pgvector's Vector column type, which only compiles against
# a real Postgres + pgvector database. SQLite can't create that table, so we skip it
# here — chat/RAG tests mock the service layer instead of touching this table directly.
SQLITE_COMPATIBLE_TABLES = [
    t for t in Base.metadata.sorted_tables if t.name != "cost_embeddings"
]


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine, tables=SQLITE_COMPATIBLE_TABLES)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine, tables=SQLITE_COMPATIBLE_TABLES)
    app.dependency_overrides.clear()
