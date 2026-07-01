def test_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200


def test_seed_and_costs(client):
    seed_res = client.post("/api/costs/seed")
    assert seed_res.status_code == 200
    assert seed_res.json()["records"] > 0

    costs_res = client.get("/api/costs")
    assert costs_res.status_code == 200
    assert len(costs_res.json()) > 0

    by_service = client.get("/api/costs/by-service")
    assert by_service.status_code == 200
    assert len(by_service.json()) == 6

    trend = client.get("/api/costs/trend")
    assert trend.status_code == 200
