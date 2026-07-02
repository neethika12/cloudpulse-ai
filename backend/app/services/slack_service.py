import requests
from app.config import settings
from app.models import Anomaly


def send_anomaly_alert(anomalies: list[Anomaly], webhook_url: str | None = None) -> tuple[bool, str]:
    """Posts a formatted summary of detected anomalies to Slack via an incoming webhook.

    Prefers a per-user webhook (set via Settings in the UI) if provided, falling back
    to the shared SLACK_WEBHOOK_URL env var. Returns (sent, detail) rather than
    raising, so a missing/misconfigured webhook degrades gracefully instead of
    breaking the API response.
    """
    target_url = webhook_url or settings.slack_webhook_url
    if not target_url:
        return False, "No Slack webhook configured - add one in Settings, or set SLACK_WEBHOOK_URL."

    if not anomalies:
        text = "CloudPulse AI: no cost anomalies detected. Spending looks normal."
    else:
        lines = [
            f"- {a.service} on {a.date}: ${a.amount_usd:.2f} (unusual spend)" for a in anomalies
        ]
        text = "CloudPulse AI detected {} cost anomal{}:\n{}".format(
            len(anomalies),
            "y" if len(anomalies) == 1 else "ies",
            "\n".join(lines),
        )

    try:
        response = requests.post(target_url, json={"text": text}, timeout=10)
    except requests.RequestException as exc:
        return False, f"Slack request failed: {exc}"

    if response.status_code == 200:
        return True, "Alert sent."
    return False, f"Slack returned {response.status_code}: {response.text}"
