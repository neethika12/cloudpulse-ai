"""
Health/readiness tests. /health is a pure liveness check (no DB access); /health/ready
actually queries the database, so it doubles as a smoke test that get_db works end to
end through the test fixture.
"""


def test_liveness(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_readiness_ok(client):
    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_metrics_endpoint_exposed(client):
    # Hit a couple of routes first so the instrumentator has something to report.
    client.get("/health")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text
