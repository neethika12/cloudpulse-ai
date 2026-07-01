import random
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models import CloudAccount, CostRecord

SERVICES = {
    "EC2": (40, 90),
    "S3": (5, 15),
    "RDS": (20, 45),
    "Lambda": (2, 8),
    "CloudFront": (3, 10),
    "VPC": (1, 4),
}

SPIKE_DAYS_AGO = [12, 45]  # days in the past that get an artificial spike


def seed_mock_data(db: Session, days: int = 90) -> CloudAccount:
    account = db.query(CloudAccount).filter_by(aws_account_id="123456789012").first()
    if not account:
        account = CloudAccount(
            name="Demo AWS Account",
            provider="aws",
            aws_account_id="123456789012",
        )
        db.add(account)
        db.flush()

    today = date.today()
    for offset in range(days):
        day = today - timedelta(days=offset)
        for service, (low, high) in SERVICES.items():
            amount = round(random.uniform(low, high), 2)
            if offset in SPIKE_DAYS_AGO and service in ("EC2", "RDS"):
                amount = round(amount * random.uniform(3, 5), 2)
            db.add(CostRecord(account_id=account.id, service=service, date=day, amount_usd=amount))

    db.commit()
    return account
