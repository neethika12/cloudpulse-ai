# Savings Plans and Reserved Instances

Commitment discounts trade flexibility for price: you commit to a level of usage for one or three years and AWS discounts it heavily compared with On-Demand. They are the single biggest lever for steady workloads, and the most common way to waste money when bought for the wrong usage.

## Compute Savings Plans

A Compute Savings Plan is a commitment to spend a fixed amount per hour (for example $10/hour) on compute for one or three years. It saves up to 66% compared with On-Demand and applies automatically across EC2 instance families, sizes, operating systems, tenancy and Regions, and also to AWS Fargate and AWS Lambda. Because it follows usage when you change instance types or move to containers, it is the safest default commitment.

## EC2 Instance Savings Plans

An EC2 Instance Savings Plan commits to a specific instance family in a specific Region (for example m7g in us-east-1). It saves up to 72%, more than a Compute Savings Plan, but only applies to that family in that Region. It still flexes across sizes, operating systems and tenancy within the family.

## Reserved Instances

Reserved Instances (RIs) predate Savings Plans and also save up to 72% for EC2. Standard RIs offer the deepest discount; Convertible RIs can be exchanged for other instance types at a smaller discount. For EC2, Savings Plans are generally simpler. RIs remain the commitment model for services Savings Plans do not cover, such as Amazon RDS, Amazon ElastiCache, Amazon OpenSearch Service and Amazon Redshift.

## Term and payment options

Three-year terms discount more than one-year terms. All Upfront payment discounts more than Partial Upfront, which discounts more than No Upfront. Pick a term you are confident about: a commitment is billed whether or not you use it.

## How much to commit

Commit only to the baseline you are confident will persist, not to peaks or one-off spikes. A common approach is to look at the lowest hourly compute spend over the last 30 to 60 days and commit to most of it, then buy more in small increments over time as usage grows. Never size a commitment from a period that contains an anomaly or a migration, because spend that does not recur becomes paid-for but unused commitment.

## Measuring coverage and utilization

Coverage is the share of eligible usage covered by commitments; utilization is the share of purchased commitment actually used. Aim for high utilization (close to 100%) first, then raise coverage gradually. Low utilization means you are paying for commitment you do not use. Cost Explorer has coverage and utilization reports and makes purchase recommendations based on your history.
