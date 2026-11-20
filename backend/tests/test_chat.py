"""Chat agent tests. OpenAI is replaced by tests/fakes.FakeOpenAI; the SQL tools and the
knowledge-base retrieval run for real against the in-memory database."""
import json
from datetime import date, timedelta

from app.models import Anomaly, ChatTrace, CloudAccount, CostRecord, User
from app.services import chat_agent
from tests.conftest import signup
from tests.fakes import FakeOpenAI


def _seed(db, user_id=None, aws_id="demo", amount=100.0):
    acct = CloudAccount(name=aws_id, aws_account_id=aws_id, user_id=user_id)
    db.add(acct)
    db.flush()
    today = date.today()
    for i in range(10):
        db.add(CostRecord(account_id=acct.id, service="EC2", date=today - timedelta(days=i), amount_usd=amount))
        db.add(CostRecord(account_id=acct.id, service="S3", date=today - timedelta(days=i), amount_usd=10.0))
    db.add(Anomaly(account_id=acct.id, service="EC2", date=today - timedelta(days=3), amount_usd=4 * amount))
    db.commit()
    return acct


def _user(db, email="user@example.com"):
    return db.query(User).filter_by(email=email).one()


def test_tools_return_real_numbers(db, auth_headers):
    _seed(db)
    ids = chat_agent.accessible_account_ids(db, _user(db))
    summary = chat_agent.run_tool(db, ids, "get_cost_summary", {})
    assert summary["services"][0] == {"service": "EC2", "total_usd": 1000.0}
    assert summary["grand_total_usd"] == 1100.0
    assert chat_agent.run_tool(db, ids, "get_anomalies", {})["anomalies"][0]["usd"] == 400.0
    assert len(chat_agent.run_tool(db, ids, "get_daily_costs", {"service": "s3"})["days"]) == 10
    today = date.today()
    cmp = chat_agent.run_tool(db, ids, "compare_periods", {
        "period_a_start": str(today - timedelta(days=9)), "period_a_end": str(today - timedelta(days=5)),
        "period_b_start": str(today - timedelta(days=4)), "period_b_end": str(today)})
    assert {r["service"] for r in cmp["comparison"]} == {"EC2", "S3"}


def test_tools_never_see_another_users_account(client, db):
    signup(client, "alice@example.com")
    signup(client, "bob@example.com")
    alice, bob = _user(db, "alice@example.com"), _user(db, "bob@example.com")
    _seed(db)  # shared demo account
    _seed(db, user_id=bob.id, aws_id="bob-real", amount=999.0)

    alice_ids = chat_agent.accessible_account_ids(db, alice)
    assert chat_agent.run_tool(db, alice_ids, "get_cost_summary", {})["grand_total_usd"] == 1100.0
    assert all(a["usd"] == 400.0 for a in chat_agent.run_tool(db, alice_ids, "get_anomalies", {})["anomalies"])

    # Bob has his own data, so he sees only that, not the demo account.
    bob_ids = chat_agent.accessible_account_ids(db, bob)
    assert chat_agent.run_tool(db, bob_ids, "get_cost_summary", {})["grand_total_usd"] == 10090.0


def test_chat_requires_login(client):
    assert client.post("/api/chat/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/api/chat/stream", json={"question": "hi"}).status_code == 401


def test_ask_without_key_returns_503(client, auth_headers, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "")
    res = client.post("/api/chat/ask", json={"question": "hi"}, headers=auth_headers)
    assert res.status_code == 503
    assert "OPENAI_API_KEY" in res.json()["detail"]


def test_agent_calls_sql_tool_then_answers_and_records_trace(client, db, auth_headers, use_fake_openai):
    _seed(db)
    fake = use_fake_openai(FakeOpenAI(script=[
        {"tool_calls": [("get_cost_summary", {})]},
        {"content": "EC2 costs the most at $1,000.00."},
    ]))
    res = client.post("/api/chat/ask", headers=auth_headers, json={
        "question": "which service costs the most?",
        "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi!"}],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["answer"] == "EC2 costs the most at $1,000.00."
    assert body["steps"][0]["name"] == "get_cost_summary"
    assert body["steps"][0]["summary"] == "2 services, $1,100.00 total"
    assert body["citations"] == []
    # two streamed gpt-4o calls at 1000 in / 50 out tokens each
    assert body["usage"]["prompt_tokens"] == 2000
    assert body["usage"]["cost_usd"] == round(2 * (1000 * 2.5 + 50 * 10) / 1e6, 6)

    # History is passed through, and the tool result reaches the second model call.
    first_messages = fake.chat_requests[0]["messages"]
    assert [m["role"] for m in first_messages] == ["system", "user", "assistant", "user"]
    tool_message = [m for m in fake.chat_requests[1]["messages"] if m["role"] == "tool"][0]
    assert json.loads(tool_message["content"])["grand_total_usd"] == 1100.0

    trace = db.query(ChatTrace).one()
    assert trace.status == "ok"
    assert trace.steps[0]["name"] == "get_cost_summary"
    assert trace.prompt_tokens == 2000


def test_knowledge_search_produces_citations(client, db, auth_headers, use_fake_openai):
    use_fake_openai(FakeOpenAI(script=[
        {"tool_calls": [("search_knowledge_base", {"query": "NAT gateway data processing charges"})]},
        {"content": "Add a free S3 gateway endpoint so S3 traffic skips the NAT gateway [K1]. [K99] is not real."},
    ]))
    res = client.post("/api/chat/ask", headers=auth_headers, json={"question": "How do I cut NAT costs?"})
    assert res.status_code == 200, res.text
    body = res.json()

    step = body["steps"][0]
    assert step["name"] == "search_knowledge_base"
    assert step["refs"][0] == "K1"
    # Only refs the search returned become citations; the made-up [K99] is dropped.
    assert [c["ref"] for c in body["citations"]] == ["K1"]
    assert body["citations"][0]["source"] == "networking-and-data-transfer.md"
    # The knowledge base was indexed on first use.
    assert db.query(ChatTrace).one().citations[0]["source"] == "networking-and-data-transfer.md"


def test_stream_emits_events_in_order(client, db, auth_headers, use_fake_openai):
    _seed(db)
    use_fake_openai(FakeOpenAI(script=[
        {"tool_calls": [("get_anomalies", {})]},
        {"content": "One EC2 spike on day 3."},
    ]))
    with client.stream("POST", "/api/chat/stream", headers=auth_headers, json={"question": "any spikes?"}) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        raw = "".join(res.iter_text())

    events = [json.loads(block.split("data: ", 1)[1]) for block in raw.strip().split("\n\n")]
    types = [e["type"] for e in events]
    assert types[:2] == ["tool_call", "tool_result"]
    assert types[-1] == "done"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "One EC2 spike on day 3."
    assert events[1]["summary"] == "1 anomalies"
    assert "output" not in events[1]  # full tool output stays server-side


def test_provider_failure_returns_502_and_records_error_trace(client, db, auth_headers, use_fake_openai):
    use_fake_openai(FakeOpenAI(fail_chat=True))
    res = client.post("/api/chat/ask", headers=auth_headers, json={"question": "hi"})
    assert res.status_code == 502
    assert db.query(ChatTrace).one().status == "error"


def test_reseed_clears_stale_anomalies(client, db):
    client.post("/api/costs/seed")
    client.post("/api/anomalies/detect")
    client.post("/api/costs/seed")
    assert db.query(Anomaly).count() == 0


def test_azure_client_selected_when_endpoint_set(monkeypatch):
    from app.config import settings
    from openai import AzureOpenAI
    from app.services import llm

    monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com")
    monkeypatch.setattr(settings, "azure_openai_api_key", "az-key")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert llm.is_configured()
    assert isinstance(llm.get_client(), AzureOpenAI)

    monkeypatch.setattr(settings, "azure_openai_api_key", "")
    assert not llm.is_configured()


def test_aux_models_default_to_chat_deployment_on_azure():
    from app.config import Settings

    azure = Settings(azure_openai_endpoint="https://x.openai.azure.com", openai_model="my-chat", _env_file=None)
    assert azure.openai_rerank_model == "my-chat" and azure.openai_judge_model == "my-chat"
    plain = Settings(_env_file=None)
    assert plain.openai_rerank_model == "gpt-4o-mini"


def test_azure_v1_endpoint_from_portal_url(monkeypatch):
    from openai import AzureOpenAI
    from app.config import settings
    from app.services import llm

    portal = "https://res.services.ai.azure.com/openai/v1/responses"
    assert llm.azure_v1_base_url(portal) == "https://res.services.ai.azure.com/openai/v1/"
    assert llm.azure_v1_base_url("https://res.openai.azure.com") is None

    monkeypatch.setattr(settings, "azure_openai_endpoint", portal)
    monkeypatch.setattr(settings, "azure_openai_api_key", "k")
    client = llm.get_client()
    assert not isinstance(client, AzureOpenAI)
    assert str(client.base_url) == "https://res.services.ai.azure.com/openai/v1/"


def test_temperature_only_sent_to_classic_models(monkeypatch):
    from app.config import settings
    from app.services import llm

    monkeypatch.setattr(settings, "llm_send_temperature", None)
    assert llm._sampling("gpt-4o", 0.2) == {"temperature": 0.2}
    assert llm._sampling("gpt-6.1-sol", 0.2) == {}
    monkeypatch.setattr(settings, "llm_send_temperature", True)
    assert llm._sampling("gpt-6.1-sol", 0.2) == {"temperature": 0.2}
