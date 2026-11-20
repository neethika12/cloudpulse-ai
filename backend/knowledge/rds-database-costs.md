# Amazon RDS and Aurora Cost Optimization

Managed database costs come from instance hours, storage, provisioned IOPS, backup storage beyond the free allowance, and data transfer. Databases are often sized generously and left running, so they are a frequent source of waste.

## Rightsize the instance

Use CloudWatch metrics (CPUUtilization, FreeableMemory, ReadIOPS/WriteIOPS) and Performance Insights to see whether the instance is busy. A database averaging low CPU with plenty of freeable memory can usually drop a size. Graviton-based instance classes (for example db.r7g, db.m7g) generally give better price performance than comparable x86 classes.

## Multi-AZ and read replicas

A Multi-AZ deployment keeps a standby in another Availability Zone and roughly doubles the instance cost. It is the right choice for production, but development, test and staging databases usually do not need it. Each read replica is billed as a separate instance; remove replicas that serve little read traffic.

## Stop non-production databases

RDS instances can be stopped to pause instance charges (storage still bills). A stopped instance automatically starts again after seven days, so long pauses need a scheduled job to stop it again, or take a snapshot and delete the instance instead.

## Aurora Serverless v2

Aurora Serverless v2 scales capacity in fine-grained Aurora Capacity Units with demand, which suits spiky or unpredictable workloads and development environments. For a steady, busy workload a provisioned instance covered by a Reserved Instance is usually cheaper.

## Storage and backups

Use gp3 storage where available instead of gp2 or provisioned-IOPS (io1/io2) volumes unless you truly need the higher IOPS guarantees. Review automated backup retention and delete manual snapshots that are no longer needed; manual snapshots are kept until deleted and backup storage beyond the free allowance is billed per GB-month.

## Commitments

Savings Plans do not cover RDS. Use RDS Reserved Instances for databases you expect to run for at least a year; they offer significant discounts compared with On-Demand. Rightsize first, then reserve, so you do not lock in an oversized instance.
