import boto3
from datetime import date, timedelta
from botocore.exceptions import ClientError, BotoCoreError
from sqlalchemy.orm import Session
from app.models import CloudAccount, CostRecord, User
from app.services.crypto_service import encrypt, decrypt


class AwsCredentialError(Exception):
    """Raised when AWS rejects the provided credentials or they lack permissions."""


def connect_aws_account(
    db: Session,
    user: User,
    access_key_id: str,
    secret_access_key: str,
    region: str,
) -> CloudAccount:
    """Validates the given AWS credentials via STS, then stores them (encrypted)
    against a CloudAccount owned by this user. Raises AwsCredentialError if AWS
    rejects the credentials - we never save anything we haven't verified works."""
    try:
        sts_client = boto3.client(
            "sts",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        identity = sts_client.get_caller_identity()
    except (ClientError, BotoCoreError) as exc:
        raise AwsCredentialError(f"AWS rejected these credentials: {exc}") from exc

    aws_account_id = identity["Account"]

    account = db.query(CloudAccount).filter_by(user_id=user.id).first()
    if account is None:
        account = CloudAccount(user_id=user.id, name=f"{user.email}'s AWS Account")
        db.add(account)

    account.aws_account_id = aws_account_id
    account.provider = "aws"
    account.is_connected = True
    account.aws_access_key_id = access_key_id
    account.aws_secret_access_key_encrypted = encrypt(secret_access_key)
    account.aws_region = region

    db.commit()
    db.refresh(account)
    return account


def sync_real_costs(db: Session, account: CloudAccount, days: int = 90) -> int:
    """Pulls real daily cost data from AWS Cost Explorer, grouped by service, and
    replaces this account's existing cost records with it."""
    if not account.is_connected or not account.aws_secret_access_key_encrypted:
        raise AwsCredentialError("This account isn't connected to AWS yet.")

    secret_key = decrypt(account.aws_secret_access_key_encrypted)

    try:
        ce_client = boto3.client(
            "ce",  # Cost Explorer is a global service, but the SDK still wants a region
            aws_access_key_id=account.aws_access_key_id,
            aws_secret_access_key=secret_key,
            region_name=account.aws_region or "us-east-1",
        )
        end = date.today()
        start = end - timedelta(days=days)
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
    except (ClientError, BotoCoreError) as exc:
        raise AwsCredentialError(f"Cost Explorer request failed: {exc}") from exc

    db.query(CostRecord).filter_by(account_id=account.id).delete()

    count = 0
    for day_result in response.get("ResultsByTime", []):
        day = date.fromisoformat(day_result["TimePeriod"]["Start"])
        for group in day_result.get("Groups", []):
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            if amount == 0:
                continue
            db.add(CostRecord(account_id=account.id, service=service, date=day, amount_usd=amount))
            count += 1

    db.commit()
    return count
