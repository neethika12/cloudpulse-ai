# Tests must not depend on a developer's local backend/.env (real keys, Azure endpoint,
# custom deployment names). Environment variables beat .env in pydantic-settings, so pin
# the AI settings here, before anything imports app.config.
import os

for _name, _value in {
    "AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_API_KEY": "", "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "gpt-4o", "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
    "OPENAI_RERANK_MODEL": "", "OPENAI_JUDGE_MODEL": "", "LLM_CHAT_API": "auto",
    "LLM_SEND_TEMPERATURE": "",
}.items():
    os.environ[_name] = _value
os.environ.pop("LLM_SEND_TEMPERATURE")

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



@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture()
def db(client):
    session = TestingSessionLocal()
    yield session
    session.close()


def signup(client, email="user@example.com") -> dict:
    res = client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def auth_headers(client):
    return signup(client)


@pytest.fixture()
def use_fake_openai(monkeypatch):
    """Call with a FakeOpenAI to route every LLM call in the app to it."""
    from app.config import settings
    from app.services import llm

    def install(fake):
        monkeypatch.setattr(settings, "openai_api_key", "test-key")
        monkeypatch.setattr(llm, "get_client", lambda: fake)
        return fake

    return install
