import requests
from app.config import settings
from app.models import Anomaly


def send_anomaly_alert(anomalies: list[Anomaly]) -> tuple[bool, str]:
    """Posts a formatted summary of detected anomalies to Slack via an incoming webhook.

    Returns (sent, detail) rather than raising, so a missing/misconfigured webhook
    degrades gracefully instead of breaking the API response.
    """
    if not settings.slack_webhook_url:
        return False, "No SLACK_WEBHOOK_URL configured - skipped."

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
        response = requests.post(settings.slack_webhook_url, json={"text": text}, timeout=10)
    except requests.RequestException as exc:
        return False, f"Slack request failed: {exc}"

    if response.status_code == 200:
        return True, "Alert sent."
    return False, f"Slack returned {response.status_code}: {response.text}"
