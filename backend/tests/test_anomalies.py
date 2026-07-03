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
        anomalies_route,
        "send_anomaly_alert",
        lambda anomalies, webhook_url=None: (False, "No webhook configured."),
    )
    res = client.post("/api/anomalies/alert")
    assert res.status_code == 200
    body = res.json()
    assert body["sent"] is False
    assert "count" in body


def test_alert_with_signed_in_user_webhook(client, monkeypatch):
    """When a signed-in user has a Slack webhook set in Settings, /alert should use
    it - verified here by asserting the webhook_url the route passes through, without
    making a real network call."""
    captured = {}

    def fake_send(anomalies, webhook_url=None):
        captured["webhook_url"] = webhook_url
        return True, "Alert sent."

    monkeypatch.setattr(anomalies_route, "send_anomaly_alert", fake_send)

    signup_res = client.post(
        "/api/auth/signup", json={"email": "sre@example.com", "password": "password123"}
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.patch(
        "/api/auth/me",
        json={"slack_webhook_url": "https://hooks.slack.com/services/real-team"},
        headers=headers,
    )

    res = client.post("/api/anomalies/alert", headers=headers)
    assert res.status_code == 200
    assert res.json()["sent"] is True
    assert captured["webhook_url"] == "https://hooks.slack.com/services/real-team"
