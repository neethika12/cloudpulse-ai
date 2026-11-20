# EC2 Spot Instances

Spot Instances use spare EC2 capacity at discounts of up to 90% compared with On-Demand prices. The trade-off is that AWS can reclaim the capacity when it needs it back.

## Interruptions

When AWS reclaims a Spot Instance it sends a two-minute interruption notice, available through instance metadata and as an Amazon EventBridge event. Applications should use the notice to checkpoint work, drain connections or deregister from a load balancer. An EC2 rebalance recommendation can arrive earlier, signalling elevated interruption risk.

## Good and bad fits

Spot suits workloads that are fault tolerant, stateless or flexible about when they run: batch processing, CI/CD build agents, big data and analytics jobs, rendering, machine learning training with checkpoints, and horizontally scaled web tiers behind a load balancer.

Spot is a poor fit for workloads that cannot tolerate interruption, such as a single-instance database, long jobs without checkpointing, or anything stateful that cannot be quickly restarted elsewhere.

## Getting reliable Spot capacity

Diversify: request several instance types and sizes across multiple Availability Zones, so one capacity pool running out does not stop the workload. Use attribute-based instance type selection to describe what you need (vCPUs, memory) rather than listing exact types.

Use the price-capacity-optimized allocation strategy in Auto Scaling groups and EC2 Fleet. It launches from the pools least likely to be interrupted while still favouring lower prices.

## Mixing purchase options

A common pattern is a mixed-instances Auto Scaling group: a base of On-Demand capacity (covered by a Savings Plan) for the minimum the service needs, with Spot for everything above it. Managed services such as EKS managed node groups, ECS capacity providers, AWS Batch and EMR support Spot directly.
