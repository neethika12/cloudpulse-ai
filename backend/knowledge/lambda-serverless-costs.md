# AWS Lambda and Serverless Costs

Lambda bills per request and per unit of compute time, measured in GB-seconds: the memory configured for the function multiplied by its run time. There is no charge when a function is not running, which makes Lambda cheap for spiky or low-volume work and potentially expensive for constant high-volume work.

## Tune memory, not just code

CPU is allocated in proportion to memory, so raising memory can make a function finish faster and sometimes cost less overall. The only way to know is to measure: AWS Lambda Power Tuning runs a function at several memory sizes and charts cost against duration so you can pick the cheapest or fastest setting. Compute Optimizer also produces Lambda memory recommendations.

## Arm (Graviton) functions

Functions on the arm64 architecture are billed at a lower price per GB-second than x86_64, about 20% lower, and AWS cites up to 34% better price performance. Most Python, Node.js and Java functions run unchanged; functions with native dependencies need Arm builds.

## Provisioned concurrency

Provisioned concurrency keeps execution environments warm to remove cold starts, and is billed for as long as it is configured, whether or not requests arrive. Use it only for latency-sensitive paths, and schedule it with Application Auto Scaling to match traffic rather than leaving it on around the clock.

## Common cost traps

- Recursive loops: a function that writes to the same S3 bucket or queue that triggers it can invoke itself endlessly. Lambda recursive loop detection stops some of these loops, but design triggers so outputs go to a different location.
- Retries and dead letters: asynchronous invocations retry on error, multiplying cost when a downstream dependency fails. Configure maximum retry attempts and a failure destination.
- Logs: every function writes to CloudWatch Logs, which charges for ingestion and storage. Set a retention period on log groups (they never expire by default) and avoid verbose debug logging in production.
- Waiting: Lambda bills while a function waits on network calls. Long synchronous waits on other services are cheaper as Step Functions workflows or asynchronous patterns.

## When Lambda stops being cheap

For steady traffic that keeps functions busy most of the time, containers on Fargate or EC2 with a Savings Plan can be cheaper. Compute Savings Plans apply to Lambda as well, which reduces the cost of steady serverless usage.
