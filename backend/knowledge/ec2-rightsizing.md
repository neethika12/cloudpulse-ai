# EC2 Rightsizing and Idle Resources

Compute is usually the largest line on an AWS bill, and the most common reason is instances that are bigger than the workload needs or that run when nobody uses them. Rightsizing means matching instance type and size to observed demand.

## Finding oversized instances

Look at at least two weeks of CloudWatch metrics, including a busy period, before changing anything. An instance whose maximum CPU utilization stays under about 40% is a candidate to drop one size; one that averages under 5% CPU and has little network traffic is likely idle.

CloudWatch does not collect memory utilization by default. Install the CloudWatch agent to publish memory metrics, otherwise you risk downsizing a memory-bound workload based on CPU alone.

AWS Compute Optimizer analyzes utilization history and recommends instance types and sizes for EC2, Auto Scaling groups, EBS volumes, Lambda functions and ECS on Fargate. The basic recommendations are free. Treat each recommendation as a hypothesis: test the smaller size in a non-production environment and watch latency and error rates after the change.

## Instance families and Graviton

Moving to a newer generation (for example m5 to m7g or m6i) often gives better performance per dollar at the same or lower price. AWS Graviton (Arm-based) instances offer up to 40% better price performance than comparable x86 instances for many workloads, according to AWS. Interpreted languages and containers usually move easily; native binaries need an Arm build.

Choose the family by the bottleneck: compute-optimized (c) for CPU-heavy work, memory-optimized (r, x) for caches and in-memory databases, general purpose (m) when unsure, and burstable (t) for spiky low-average workloads. Burstable instances in unlimited mode bill extra CPU credits when they run hot for long periods, which can make them more expensive than a fixed-performance instance.

## Idle and forgotten resources

Stop or terminate instances that serve no traffic. Development and test environments rarely need to run nights and weekends: scheduling them to run only 50 hours a week instead of 168 cuts their compute cost by about 70%. AWS Instance Scheduler or a simple EventBridge rule can automate start and stop.

Stopped instances do not incur compute charges, but their attached EBS volumes and any Elastic IP addresses still bill. Delete unattached EBS volumes and old snapshots, and release unused Elastic IPs; AWS charges for every public IPv4 address, attached or not.

## EBS volumes

Migrate gp2 volumes to gp3. gp3 is about 20% cheaper per GB than gp2 and lets you provision IOPS and throughput independently of size, so you no longer need to over-provision capacity just to get performance. The migration can be done in place with Elastic Volumes and no downtime.

## Use Auto Scaling instead of peak sizing

A fleet sized for its peak wastes money the rest of the day. Auto Scaling groups with target tracking (for example keeping average CPU at 50%) add capacity during peaks and remove it afterwards. Combine Auto Scaling for variable load with commitment discounts for the steady baseline.
