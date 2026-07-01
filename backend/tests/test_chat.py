"""
Chat/RAG endpoint tests. These mock the service layer rather than loading the real
local embedding/chat models or hitting a real pgvector-enabled Postgres, so the suite
runs fast and without downloading any model weights. Hit the endpoints manually with
curl if you want to smoke-test the real local models end to end.
"""
from app.routes import chat as chat_route


def test_index_endpoint(client, monkeypatch):
    monkeypatch.setattr(chat_route, "index_cost_data", lambda db: 6)
    res = client.post("/api/chat/index")
    assert res.status_code == 200
    assert res.json() == {"indexed": 6}


def test_ask_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        chat_route, "answer_question", lambda db, question: "EC2 is your biggest cost driver."
    )
    res = client.post("/api/chat/ask", json={"question": "which service costs the most?"})
    assert res.status_code == 200
    assert "EC2" in res.json()["answer"]
