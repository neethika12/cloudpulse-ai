import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session
from app.models import CostRecord, Anomaly

# Upper bound on the fraction of days per service IsolationForest may flag. With a
# fixed contamination, IsolationForest always flags ~10% of points as "most unusual"
# even when nothing is truly abnormal that day - it can't return zero anomalies.
# To avoid reporting borderline-normal days as spikes, we treat contamination as just
# a candidate shortlist and only keep candidates that are also statistically extreme
# (more than STD_THRESHOLD standard deviations above that service's own mean).
CONTAMINATION = 0.1
STD_THRESHOLD = 2.0
MIN_RECORDS_FOR_DETECTION = 10


def detect_anomalies(db: Session) -> list[Anomaly]:
    """
    Runs an IsolationForest per AWS service over its daily spend history to shortlist
    candidate outlier days, then keeps only the candidates that are also more than
    STD_THRESHOLD standard deviations above that service's mean spend. Replaces any
    previously stored results.

    Detection runs independently per service because different services have very
    different normal spend ranges (EC2 vs. VPC, for example) - pooling them together
    would just flag "expensive services" instead of "unusual days".
    """
    db.query(Anomaly).delete()

    services = [row[0] for row in db.query(CostRecord.service).distinct().all()]
    detected: list[Anomaly] = []

    for service in services:
        records = (
            db.query(CostRecord)
            .filter(CostRecord.service == service)
            .order_by(CostRecord.date)
            .all()
        )
        if len(records) < MIN_RECORDS_FOR_DETECTION:
            continue

        values = np.array([r.amount_usd for r in records])
        amounts = values.reshape(-1, 1)

        model = IsolationForest(contamination=CONTAMINATION, random_state=42)
        predictions = model.fit_predict(amounts)  # -1 = candidate anomaly, 1 = normal

        mean, std = values.mean(), values.std()
        threshold = mean + STD_THRESHOLD * std

        for record, prediction, value in zip(records, predictions, values):
            if prediction == -1 and value > threshold:
                anomaly = Anomaly(
                    account_id=record.account_id,
                    service=record.service,
                    date=record.date,
                    amount_usd=record.amount_usd,
                )
                db.add(anomaly)
                detected.append(anomaly)

    db.commit()
    return detected
