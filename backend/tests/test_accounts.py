"""
AWS connect/sync tests. These mock boto3 entirely so the suite never makes real
AWS calls or needs real credentials - they verify our own validation, encryption,
and data-handling logic instead.
"""
from app.services import aws_service


class FakeStsClient:
    def get_caller_identity(self):
        return {"Account": "999988887777"}


class FakeCeClient:
    def get_cost_and_usage(self, **kwargs):
        return {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-06-01", "End": "2026-06-02"},
                    "Groups": [
                        {"Keys": ["EC2"], "Metrics": {"UnblendedCost": {"Amount": "12.50"}}},
                        {"Keys": ["S3"], "Metrics": {"UnblendedCost": {"Amount": "1.25"}}},
                    ],
                }
            ]
        }


def fake_boto3_client(service_name, **kwargs):
    if service_name == "sts":
        return FakeStsClient()
    if service_name == "ce":
        return FakeCeClient()
    raise ValueError(f"unexpected service {service_name}")


class RejectingStsClient:
    def get_caller_identity(self):
        from botocore.exceptions import ClientError

        raise ClientError(
            {"Error": {"Code": "InvalidClientTokenId", "Message": "The security token is invalid"}},
            "GetCallerIdentity",
        )


def rejecting_boto3_client(service_name, **kwargs):
    if service_name == "sts":
        return RejectingStsClient()
    raise ValueError(f"unexpected service {service_name}")


def _signup_and_get_token(client, email="aws-user@example.com"):
    res = client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    return res.json()["access_token"]


def test_connect_aws_requires_auth(client):
    res = client.post(
        "/api/accounts/connect-aws",
        json={"access_key_id": "AKIA...", "secret_access_key": "secret", "region": "us-east-1"},
    )
    assert res.status_code == 401


def test_connect_and_sync_aws(client, monkeypatch):
    monkeypatch.setattr(aws_service, "boto3", type("B", (), {"client": staticmethod(fake_boto3_client)}))

    token = _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    connect_res = client.post(
        "/api/accounts/connect-aws",
        json={"access_key_id": "AKIAFAKE", "secret_access_key": "supersecret", "region": "us-west-2"},
        headers=headers,
    )
    assert connect_res.status_code == 200
    body = connect_res.json()
    assert body["is_connected"] is True
    assert body["aws_account_id"] == "999988887777"

    me_res = client.get("/api/accounts/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["is_connected"] is True

    sync_res = client.post("/api/accounts/sync", headers=headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["synced_records"] == 2


def test_connect_aws_rejects_invalid_credentials(client, monkeypatch):
    monkeypatch.setattr(
        aws_service, "boto3", type("B", (), {"client": staticmethod(rejecting_boto3_client)})
    )

    token = _signup_and_get_token(client, email="badcreds@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/accounts/connect-aws",
        json={"access_key_id": "AKIABAD", "secret_access_key": "wrong", "region": "us-east-1"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "AWS rejected" in res.json()["detail"]

    # Nothing should have been saved - the account stays disconnected.
    me_res = client.get("/api/accounts/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json() is None


def test_update_profile_slack_and_onboarding(client):
    token = _signup_and_get_token(client, email="settings-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        "/api/auth/me",
        json={"slack_webhook_url": "https://hooks.slack.com/services/fake", "onboarding_completed": True},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["slack_webhook_url"] == "https://hooks.slack.com/services/fake"
    assert body["onboarding_completed"] is True
