# Cost Spike Investigation Runbook

Use this runbook when daily spend for a service jumps well above its normal range. The goal is to find the cause quickly, stop ongoing waste, and prevent a repeat.

## 1. Confirm the spike is real

Check the daily cost for the service at daily granularity, not monthly. Compare the spike day with the previous two to four weeks. Rule out expected causes first: a planned launch, a load test, a data migration, the start of a new month (some charges such as Reserved Instance or support fees post on the first), or an upfront commitment purchase.

## 2. Narrow it down

In Cost Explorer, filter to the service and group by, in turn: usage type, Region, linked account, and resource tags. The usage type usually names the cause directly, for example BoxUsage (instance hours), EBS:VolumeUsage, DataTransfer-Out-Bytes, NatGateway-Bytes or Requests-Tier1. A new Region in the breakdown can point to resources launched by mistake or by a compromised credential.

## 3. Find what changed

Correlate the start of the spike with recent changes: deployments, infrastructure-as-code changes, Auto Scaling activity, and new scheduled jobs. AWS CloudTrail shows who created resources and when; search it for RunInstances, CreateNatGateway, CreateDBInstance or similar calls around the start of the spike. Unexpected large instances or GPU instances in unused Regions are a classic sign of leaked access keys: rotate the credentials immediately and contact AWS Support.

## 4. Contain it

Stop the waste before writing the postmortem: scale down a runaway Auto Scaling group, stop forgotten instances, fix a recursive Lambda trigger, add a missing VPC endpoint, or roll back the change that introduced it. Snapshot before deleting anything that might hold data.

## 5. Prevent a repeat

Add an AWS Budgets alert or AWS Cost Anomaly Detection monitor for the service or team so the next spike is caught within a day, not at the end of the month. Tag the resources involved so ownership is clear, and record the cause and fix so the next investigation is faster.

## How CloudPulse flags anomalies

CloudPulse runs a scikit-learn IsolationForest over each service's daily spend history to shortlist unusual days, then keeps only shortlisted days whose spend is more than two standard deviations above that service's mean. Detection runs per service because services have very different normal ranges. Re-run detection after loading new cost data.
