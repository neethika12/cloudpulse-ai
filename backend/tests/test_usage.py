from tests.conftest import signup
from tests.fakes import FakeOpenAI


def test_usage_summarizes_only_the_current_users_traces(client, use_fake_openai):
    alice = signup(client, "alice@example.com")
    bob = signup(client, "bob@example.com")

    use_fake_openai(FakeOpenAI(script=[
        {"tool_calls": [("get_cost_summary", {})]},
        {"content": "Answer one."},
        {"content": "Answer two."},
        {"content": "Bob's answer."},
    ]))
    for question in ("first?", "second?"):
        assert client.post("/api/chat/ask", headers=alice, json={"question": question}).status_code == 200
    assert client.post("/api/chat/ask", headers=bob, json={"question": "bob?"}).status_code == 200

    res = client.get("/api/llm/usage", headers=alice)
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["requests"] == 2
    assert body["summary"]["errors"] == 0
    assert body["summary"]["prompt_tokens"] == 3000  # 2 model calls + 1 model call
    assert body["summary"]["avg_tool_calls"] == 0.5
    assert body["tools"] == [{"name": "get_cost_summary", "calls": 1}]
    assert [r["question"] for r in body["recent"]] == ["second?", "first?"]


def test_usage_requires_login(client):
    assert client.get("/api/llm/usage").status_code == 401
