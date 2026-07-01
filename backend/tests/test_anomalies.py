"""
Anomaly detection tests. Unlike the chat tests, these exercise the real
scikit-learn IsolationForest logic and a real SQLite-backed database - no
pgvector or model downloads involved, so it's safe to run for real. The Slack
alert call itself is mocked so tests never make a real network request.
"""
from app.routes import anomalies as anomalies_route


def test_detect_anomalies_after_seed(client):
    seed_res = client.post("/api/costs/seed")
    assert seed_res.status_code == 200

    detect_res = client.post("/api/anomalies/detect")
    assert detect_res.status_code == 200
    detected = detect_res.json()
    assert isinstance(detected, list)
    # contamination=0.1 guarantees roughly 10% of each service's days get flagged
    assert len(detected) > 0

    list_res = client.get("/api/anomalies")
    assert list_res.status_code == 200
    assert len(list_res.json()) == len(detected)


def test_alert_without_webhook_configured(client, monkeypatch):
    monkeypatch.setattr(
        anomalies_route, "send_anomaly_alert", lambda anomalies: (False, "No webhook configured.")
    )
    res = client.post("/api/anomalies/alert")
    assert res.status_code == 200
    body = res.json()
    assert body["sent"] is False
    assert "count" in body
