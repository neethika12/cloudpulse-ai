# CloudPulse eval report

Run 2026-11-20 · chat `gpt-6.1-sol` · embeddings `none (keyword-only)` · rerank `gpt-6.1-sol` · judge `gpt-6.1-sol` · Azure OpenAI

> **Self-grading:** the judge is the same model as the chat model, and models tend to rate their own answers generously. Set `OPENAI_JUDGE_MODEL` to a different model for an independent judge, and spot-check a few scores by hand.

## Retrieval (k=5, scored by source guide)

The app currently uses **keyword+rerank**. *Hard* questions are paraphrases that avoid the guides' wording.

| Config | Set | hit@1 | hit@5 | recall@5 | MRR |
|---|---|---|---|---|---|
| keyword | standard | 0.80 | 0.97 | 0.97 | 0.87 |
| keyword | hard | 0.50 | 0.83 | 0.83 | 0.66 |
| **keyword+rerank** | standard | 0.93 | 1.00 | 1.00 | 0.95 |
| **keyword+rerank** | hard | 1.00 | 1.00 | 1.00 | 1.00 |
| vector | standard | skipped: no embedding model configured | | | |
| vector | hard | skipped: no embedding model configured | | | |
| hybrid | standard | skipped: no embedding model configured | | | |
| hybrid | hard | skipped: no embedding model configured | | | |
| hybrid+rerank | standard | skipped: no embedding model configured | | | |
| hybrid+rerank | hard | skipped: no embedding model configured | | | |

## Answers (10 questions, judged by `gpt-6.1-sol`)

| Arm | Faithfulness | Correctness | Citation rate | Avg latency | Avg tokens | Avg cost |
|---|---|---|---|---|---|---|
| RAG (search tool) | 0.90 | 0.93 | 1.00 | 16.5s | 4,874 | - |
| Full context (no retrieval) | 0.90 | 0.97 | 1.00 | 10.1s | 11,350 | - |

### RAG (search tool)

| Case | Kind | Faithful | Correct | Tools | Cited | Judge's reason |
|---|---|---|---|---|---|---|
| nat-gateway | knowledge | 0.75 | 1.00 | search_knowledge_base, search_knowledge_base | yes | The answer correctly recommends a free S3 gateway endpoint to bypass NAT processing fees, but its route-table association, policy checks, and advice to retain NAT for other outbound access are not explicitly supported by the context. |
| spot-fit | knowledge | 1.00 | 0.75 | search_knowledge_base | yes | The answer is supported by the context and correctly explains Spot suitability, interruption notices, and resilience strategies, but omits the reference’s savings of up to 90%. |
| s3-archive | knowledge | 1.00 | 1.00 | search_knowledge_base, search_knowledge_base | yes | The answer correctly recommends S3 Glacier Deep Archive with lifecycle rules, states the supported 180-day minimum and 12-hour standard or 48-hour bulk retrieval times, and appropriately distinguishes storage selection from retention enforcement. |
| commitment-size | knowledge | 0.75 | 1.00 | search_knowledge_base, search_knowledge_base | yes | The answer fully matches the reference’s conservative baseline sizing, flexibility, incremental purchasing, and monitoring guidance, but its claim that the available cost tools expose only daily and service-level spend is unsupported by the context. |
| rds-dev | knowledge | 1.00 | 0.75 | get_cost_summary, search_knowledge_base | yes | All factual claims are supported by the context, and the answer covers most recommended savings measures but omits Aurora Serverless v2 for spiky workloads and explicitly scheduling re-stops after the seven-day automatic restart. |
| spike-runbook | knowledge | 1.00 | 0.75 | get_daily_costs, get_anomalies, search_knowledge_base | yes | The answer accurately uses the daily costs and supported investigation guidance, but omits an explicit containment step before adding budgets and anomaly detection. |
| top-service | data | 1.00 | 1.00 | get_cost_summary | - | The answer correctly identifies EC2 as the highest-cost service at $6,200.66, and its stated date range is supported by the tool arguments. |
| last-7-days | data | 1.00 | 1.00 | get_cost_summary | - | The answer accurately reports the supported total of $809.86 for November 14–20, 2026, matching the reference and the requested seven-day period including today. |
| anomalies | data | 0.50 | 1.00 | get_anomalies | - | The answer correctly states that there were no spending anomalies, but the August 23–November 20, 2026 date range is not supported by the context. |
| spike-advice | mixed | 1.00 | 1.00 | get_daily_costs, get_anomalies, get_cost_summary, get_cost_summary, search_knowledge_base, get_daily_costs, get_daily_costs | yes | The answer accurately identifies EC2’s November 8 spike using the supplied costs, distinguishes it from the empty detector results and largest total-bill spike, and provides supported Cost Explorer, deployment, Auto Scaling, and CloudTrail investigation steps. |

<details><summary>Full answers, for checking the judge by hand</summary>

**nat-gateway**: Instances in private subnets pull a lot of data from S3 and our NAT gateway bill is high. What can we do?

> Reference: Add a VPC gateway endpoint for S3 (free) so S3 traffic bypasses the NAT gateway and avoids its per-GB processing fee (about $0.045/GB in us-east-1).

**Add an S3 gateway VPC endpoint.** Private-subnet instances accessing S3 through a NAT gateway incur NAT processing fees for that traffic. A gateway endpoint routes S3 traffic privately without using NAT—and the endpoint itself is free. [K1]

1. **Create a gateway endpoint for S3** in your VPC and associate it with the route tables used by the private subnets. Choose **Gateway**, not an S3 interface endpoint, for this cost-saving approach; interface endpoints have their own charges. [K1] Check endpoint and bucket policies, then test S3 access from an instance before rolling it out broadly.

2. **Verify the savings.** In Cost Explorer, track the `NatGateway-Bytes` usage type before and after the change; use VPC Flow Logs to identify any remaining high-volume traffic through NAT. [K2]

This targets **NAT processing charges for S3 traffic**, not the NAT gateway’s hourly charge or S3’s own charges. [K1][K4] Keep the NAT gateway if instances still need it for other outbound access.

I can’t quantify your savings without a breakdown of how much S3 traffic currently passes through NAT.

---

**spot-fit**: Can we run our CI build agents on Spot Instances, and what happens if AWS reclaims them?

> Reference: Yes, CI agents are a good Spot fit (fault tolerant). Spot saves up to 90%; AWS gives a two-minute interruption notice; diversify instance types/AZs and use price-capacity-optimized allocation.

**Yes—Spot is a good fit for CI build agents if builds can tolerate interruption and be retried.** It is less suitable for long builds that cannot checkpoint or restart cheaply. [K2]

**If AWS reclaims an agent:**
- AWS sends a **two-minute interruption notice**, available through instance metadata and Amazon EventBridge. An EC2 rebalance recommendation may arrive earlier, indicating elevated interruption risk. [K1]
- Treat the agent as disposable: use the notice to stop accepting jobs and save any useful progress; an unfinished build needs to be retried on another agent unless it supports resuming from a checkpoint. [K1][K2] Whether that retry happens automatically depends on your CI configuration.

**Two practical steps:**
1. Make agents replaceable and configure interrupted-job retries; use the notice to drain the agent and checkpoint work where possible. [K1][K2]
2. Keep a small On-Demand baseline for essential builds and use Spot for additional capacity. Diversify across instance types and Availability Zones, using the **price-capacity-optimized** allocation strategy. [K3][K5]

Which CI system are you using? That will determine how to implement draining and retries.

---

**s3-archive**: We must keep audit logs for seven years but almost never read them. What storage class should we use?

> Reference: S3 Glacier Deep Archive, the lowest-cost class, via a lifecycle rule; minimum storage duration 180 days; retrieval takes up to 12 hours (or 48 for bulk).

Use **Amazon S3 Glacier Deep Archive**, provided you can wait hours to retrieve logs. It’s the lowest-cost S3 storage class for data retained for years and almost never read. [K4]

Key considerations:
- **Retrieval time:** up to 12 hours for standard retrieval or 48 hours for bulk retrieval. If audits require immediate access, consider Glacier Instant Retrieval instead. [K4]
- **Minimum storage duration:** 180 days—well within your seven-year retention requirement. [K1]
- **Retention automation:** use S3 Lifecycle rules to archive logs and expire them only after the required retention period. [K2]

Storage-class selection alone does not enforce seven-year retention; separately verify your retention and deletion-protection controls meet your audit requirements.

---

**commitment-size**: How should we size a Savings Plan purchase?

> Reference: Commit only to the steady baseline (e.g. most of the lowest hourly compute spend over 30-60 days), not to peaks or anomalies; prefer Compute Savings Plans for flexibility; buy incrementally and watch utilization and coverage.

**Size the purchase to your durable hourly compute baseline—not average monthly spend or peak demand.** Commit only to usage you’re confident will persist throughout the plan’s term. [K1]

A practical approach:

1. **Review 30–60 days of hourly eligible compute usage.** Identify the low, recurring baseline; exclude anomalies, temporary workloads, and migration periods from the sizing window. [K1]
2. **Buy conservatively at first.** Cover most—not all—of that dependable baseline, then add commitments in small increments as usage proves stable. [K1]
3. **Prioritize utilization over coverage.** Utilization measures how much purchased commitment you actually use; coverage measures how much eligible usage is covered. Aim for utilization close to 100% before increasing coverage. [K2]
4. **Choose the flexibility you need.** Compute Savings Plans are the safer default if workloads may move between EC2 families, Regions, Fargate, or Lambda; EC2 Instance Savings Plans are narrower, tied to one instance family and Region. [K3][K5]
5. **Validate the purchase in Cost Explorer.** Use its Savings Plans recommendations and coverage/utilization reports to check the proposed commitment. [K2]

**I can’t give you a defensible $/hour purchase amount from the data available here.** These cost tools expose daily and service-level spend, not hourly eligible usage or existing commitment coverage. Share your Cost Explorer Savings Plans recommendation and current coverage/utilization reports, and I can help assess the proposed size.

---

**rds-dev**: How can we reduce the cost of our development RDS databases?

> Reference: Turn off Multi-AZ for non-production, rightsize, stop instances when idle (they auto-start after 7 days, so schedule re-stops), consider Aurora Serverless v2 for spiky dev use, use gp3 storage, clean old snapshots.

Your total RDS spend was **$1,002.81 over October 22–November 20, 2026**. The available cost data doesn’t separate development from production, so I can’t quantify development-only savings yet.

For development databases, prioritize:

1. **Stop databases outside working hours.** Schedule eligible instances to stop overnight and on weekends. This pauses instance charges, but storage still bills. RDS automatically restarts stopped instances after seven days; for longer idle periods, consider taking a snapshot and deleting the instance if restore time is acceptable. [K1]

2. **Right-size and remove unnecessary redundancy.** Check CPU, freeable memory, IOPS, and Performance Insights before choosing a smaller instance. [K2] Where development doesn’t require high availability or replica testing, consider Single-AZ and remove unused read replicas. [K5]

Then review storage: use gp3 where supported and appropriate, shorten backup retention to your actual needs, and delete obsolete manual snapshots. [K3]

**Avoid committing too early:** Savings Plans don’t cover RDS; consider RDS Reserved Instances only after rightsizing, for databases you expect to keep running for at least a year. [K4]

If you share the development instances’ **engine, instance class, region, Single-/Multi-AZ configuration, storage, and required operating hours**, we can narrow this to a concrete plan.

---

**spike-runbook**: EC2 spend suddenly tripled. Walk me through investigating it.

> Reference: Confirm at daily granularity; group by usage type, Region, account and tags; correlate with deployments/Auto Scaling; check CloudTrail for RunInstances; if unknown Regions or GPU instances, suspect leaked credentials and rotate them; contain, then add budgets/anomaly detection.

**The daily data shows a one-day EC2 spike, not a sustained tripling.** The latest spike was **November 8, 2026**:

| Period | EC2 spend |
|---|---:|
| November 1–7 daily average | $72.35 |
| November 8 | **$259.75** |
| November 9 | $85.49 |

November 8 was about **3.6×** the preceding week’s average. There was also an earlier spike on **October 6: $243.78**. The anomaly tool returned **no flagged days**, despite these visible spikes.

Here’s how I’d investigate, starting with November 8.

### 1. Confirm whether it was expected
Compare the spike with the previous two to four weeks, and check for a planned launch, load test, migration, or upfront commitment purchase. [K2] Ask the workload owner specifically: **“What ran on November 8, and was anything similar run on October 6?”**

### 2. Identify which charge actually increased
In **AWS Cost Explorer**, filter to EC2, use daily granularity, and compare November 8 against the preceding weeks; group first by **usage type**, then **Region**, **linked account**, and **resource tags**. [K1][K2]

The usage-type breakdown distinguishes instance-hour charges such as `BoxUsage` from storage or networking charges such as `EBS:VolumeUsage` and `DataTransfer-Out-Bytes`. [K1] Don’t assume that an EC2 cost spike necessarily means more instances.

### 3. Trace the increase to a change
For the account and Region responsible, review deployments, infrastructure-as-code changes, Auto Scaling activity, and scheduled jobs around the spike. [K3] Search CloudTrail for `RunInstances` and other relevant resource-creation events to establish who created resources and when. [K3]

Unexpected large or GPU instances in an unused Region can indicate leaked credentials; if that is what you find, rotate the credentials immediately and contact AWS Support. [K3]

### 4. Prevent a repeat once the cause is known
Add an EC2 AWS Budgets alert or Cost Anomaly Detection monitor, and tag the affected resources so ownership is clear. [K5]

**My two immediate next steps:** get the November 8 usage-type/account/Region breakdown, then correlate the largest increase with change logs and CloudTrail. [K1][K3] The data available here confirms the timing and size, but **does not identify the responsible resources or root cause**.

---

**top-service**: Which service has cost the most across all my data, and how much did it cost?

> Reference: EC2 costs the most, $6,200.66 in total.

**EC2** cost the most: **$6,200.66 USD** across all your data, from August 23 to November 20, 2026.

---

**last-7-days**: What was my total AWS spend over the last 7 days, including today?

> Reference: Total spend from 2026-11-14 to today is $809.86.

Your total AWS spend over the last 7 days, including today (**November 14–20, 2026**), was **$809.86 USD**.

---

**anomalies**: Were there any spending anomalies? List each service and date.

> Reference: There are no anomalies.

No spending anomalies were flagged for any service during **August 23–November 20, 2026**.

---

**spike-advice**: Which service had the biggest anomaly, and what should I check to find the cause?

> Reference: Names the service and date of the largest anomaly from the data, and suggests runbook steps such as grouping by usage type, checking recent deployments/Auto Scaling and CloudTrail.

**EC2 had the largest observed service-level spike: $259.75 on November 8, 2026**, up from $59.75 the day before—a **$200.00 increase**. It fell to $85.49 the following day.

One caveat: **the anomaly detector returned no flagged anomalies**, so this is an observed spike, not a detector-confirmed anomaly. The largest *total-bill* spike was October 6 at $440.86, including EC2 at $243.78 and RDS at $169.23.

To investigate EC2’s November 8 spike:

1. **Identify the charge category.** In Cost Explorer, filter to EC2 and compare November 8 with the preceding two to four weeks. Group by usage type, then Region, linked account, and resource tags to distinguish instance hours, EBS storage, or data transfer. [K3][K1]
2. **Find what changed.** Check deployments, infrastructure changes, Auto Scaling activity, and scheduled jobs around November 8. Search CloudTrail for `RunInstances` to identify who launched instances and when. [K2]

The available cost data shows **when and which service spiked**, but not the resource or underlying cause.

---

</details>

### Full context (no retrieval)

| Case | Kind | Faithful | Correct | Tools | Cited | Judge's reason |
|---|---|---|---|---|---|---|
| nat-gateway | knowledge | 0.75 | 1.00 | - | yes | The answer correctly recommends a free S3 gateway endpoint to bypass NAT processing fees, but its route-table association instructions are not explicitly supported by the context. |
| spot-fit | knowledge | 1.00 | 1.00 | - | yes | The answer accurately reflects the context and reference on CI suitability, up to 90% savings, two-minute interruption notices, and diversified price-capacity-optimized capacity, with supported practical interruption-handling guidance. |
| s3-archive | knowledge | 1.00 | 1.00 | - | yes | The answer matches the reference and context by recommending S3 Glacier Deep Archive via lifecycle rules, noting its lowest cost, 180-day minimum duration, and 12-hour standard or 48-hour bulk retrieval times. |
| commitment-size | knowledge | 0.75 | 1.00 | - | yes | The answer matches the reference’s baseline sizing, Compute Savings Plan flexibility, incremental purchasing, and utilization monitoring guidance, but its claim that the available tools provide only daily service totals is not supported by the context. |
| rds-dev | knowledge | 1.00 | 0.75 | - | yes | All factual claims are supported by the context, and the answer covers the reference recommendations except considering Aurora Serverless v2 for spiky development workloads. |
| spike-runbook | knowledge | 1.00 | 1.00 | get_daily_costs, get_anomalies | yes | The answer accurately describes the daily spike and empty anomaly results, follows the supported investigation runbook, and covers all reference steps including attribution, CloudTrail, credential rotation, containment, and preventive alerts. |
| top-service | data | 1.00 | 1.00 | get_cost_summary | - | The answer correctly identifies EC2 as the highest-cost service at $6,200.66, and its stated date range matches the tool query. |
| last-7-days | data | 1.00 | 1.00 | get_cost_summary | - | The answer reports the exact total and inclusive date range supported by the tool output and matches the reference. |
| anomalies | data | 0.50 | 1.00 | get_anomalies | - | The answer correctly reports no anomalies and no services or dates to list, but the August 23–November 20, 2026 date range is unsupported by the context. |
| spike-advice | mixed | 1.00 | 1.00 | get_anomalies, get_daily_costs, get_cost_summary, get_daily_costs, get_daily_costs, get_cost_summary | yes | The answer correctly identifies EC2’s largest observed spike on November 8 at $259.75, distinguishes it from detector-confirmed anomalies, and provides investigation steps supported by the runbook. |

<details><summary>Full answers, for checking the judge by hand</summary>

**nat-gateway**: Instances in private subnets pull a lot of data from S3 and our NAT gateway bill is high. What can we do?

> Reference: Add a VPC gateway endpoint for S3 (free) so S3 traffic bypasses the NAT gateway and avoids its per-GB processing fee (about $0.045/GB in us-east-1).

**Add an S3 gateway VPC endpoint** so your private-subnet instances access S3 without sending that traffic through the NAT gateway. Gateway endpoints for S3 are free and avoid NAT data-processing fees for that traffic—often the quickest networking saving. [K24]

1. **Route S3 traffic through the endpoint:** create it in the VPC and associate it with the route tables used by those private subnets. Keep the NAT gateway for traffic that still needs it. [K24]
2. **Verify the impact:** in Cost Explorer, look for usage types containing `NatGateway-Bytes`; use VPC Flow Logs to identify which resources generate the traffic. [K26]

This should reduce NAT processing charges, but it won’t eliminate the gateway’s hourly charge while the gateway remains provisioned. [K24] I haven’t checked your bill, so I can’t quantify your savings yet.

---

**spot-fit**: Can we run our CI build agents on Spot Instances, and what happens if AWS reclaims them?

> Reference: Yes, CI agents are a good Spot fit (fault tolerant). Spot saves up to 90%; AWS gives a two-minute interruption notice; diversify instance types/AZs and use price-capacity-optimized allocation.

Yes—**CI/CD build agents are a good fit for Spot Instances** if builds can tolerate interruption and be retried on another agent. Spot offers discounts of up to 90% versus On-Demand; that is general AWS guidance, not an estimate of your savings. [K47][K49]

**If AWS reclaims an instance**, it sends a **two-minute interruption notice**, available through instance metadata and Amazon EventBridge. Your agent should use that window to stop accepting jobs, checkpoint work where possible, and drain connections; unfinished builds need to be retried. An EC2 rebalance recommendation may arrive earlier, signalling increased interruption risk. [K48][K49]

For a practical setup:
- **Keep a small On-Demand baseline and use Spot for extra build capacity**, so interruptions do not remove your entire agent pool. [K51]
- **Use several instance types across multiple Availability Zones**, with the `price-capacity-optimized` allocation strategy to reduce interruption risk. [K50]

Keep long builds that cannot checkpoint or tolerate a restart on On-Demand agents. [K49]

---

**s3-archive**: We must keep audit logs for seven years but almost never read them. What storage class should we use?

> Reference: S3 Glacier Deep Archive, the lowest-cost class, via a lifecycle rule; minimum storage duration 180 days; retrieval takes up to 12 hours (or 48 for bulk).

**S3 Glacier Deep Archive** is the best fit for audit logs you must retain for seven years and almost never read: it is the lowest-cost S3 storage class for long-term, rarely accessed data. [K35]

Two caveats:
- **Retrieval is slow:** allow up to 12 hours for standard retrieval or 48 hours for bulk retrieval—confirm those delays meet your audit requirements. [K35]
- **Minimum storage duration is 180 days:** deleting or transitioning objects sooner still incurs charges for the remaining days, though your seven-year retention fits comfortably. [K36]

Use an **S3 Lifecycle rule** to automate archiving and expire logs only after your required retention period. [K37]

---

**commitment-size**: How should we size a Savings Plan purchase?

> Reference: Commit only to the steady baseline (e.g. most of the lowest hourly compute spend over 30-60 days), not to peaks or anomalies; prefer Compute Savings Plans for flexibility; buy incrementally and watch utilization and coverage.

**Size a Savings Plan to your steady baseline—not your average spend or peak usage.** Commit only to usage you’re confident will persist, excluding anomalies and migrations. [K45]

A practical approach:

1. **Optimize first.** Rightsize compute and remove idle resources before locking in a commitment. [K8][K11][K45]
2. **Review 30–60 days of hourly eligible compute spend.** Use the lowest recurring hourly spend as a starting point, commit to most—not all—of that baseline, and add purchases incrementally as sustained usage grows. [K45]
3. **Account for existing commitments.** Check Cost Explorer’s coverage, utilization, and purchase recommendations; prioritize near-100% utilization before increasing coverage. [K46]
4. **Choose flexibility and term carefully.** A Compute Savings Plan is the safest default when instance families or Regions may change, and also covers Fargate and Lambda. [K41] Choose a term you’re confident about: the commitment is billed whether you use it or not. [K44]

**I can’t give a defensible $/hour purchase amount from the available data:** these tools provide daily service totals, not hourly eligible usage or existing commitment coverage. Use Cost Explorer’s Savings Plans recommendations and hourly usage to establish the amount, then validate it against planned downsizing or workload changes. [K45][K46]

---

**rds-dev**: How can we reduce the cost of our development RDS databases?

> Reference: Turn off Multi-AZ for non-production, rightsize, stop instances when idle (they auto-start after 7 days, so schedule re-stops), consider Aurora Serverless v2 for spiky dev use, use gp3 storage, clean old snapshots.

For development RDS databases, prioritize these changes:

1. **Stop databases outside working hours.** Automate a start/stop schedule for nights and weekends. Stopping pauses instance charges, but storage still bills; RDS also automatically restarts stopped instances after seven days, so longer pauses need automation to stop them again. [K30]

2. **Review Multi-AZ and read replicas.** Development databases usually don’t need Multi-AZ, which roughly doubles instance cost. Remove read replicas that serve little traffic, provided your testing requirements allow it. [K29]

3. **Rightsize using utilization metrics.** Check CloudWatch CPU, freeable memory, and read/write IOPS alongside Performance Insights. Low CPU with ample free memory suggests a smaller instance may be appropriate; also consider Graviton-based classes for better price performance. [K28]

4. **Trim storage and backups.** Use gp3 where available unless you need higher provisioned-IOPS guarantees. Review backup retention and delete manual snapshots you no longer need. [K32]

**Start with scheduling and reviewing Multi-AZ** before committing to discounts. For databases you expect to run for at least a year, consider RDS Reserved Instances—but rightsize first; Savings Plans don’t cover RDS. [K33]

I haven’t checked your bill or database configurations, so I can’t yet quantify savings or confirm which changes apply.

---

**spike-runbook**: EC2 spend suddenly tripled. Walk me through investigating it.

> Reference: Confirm at daily granularity; group by usage type, Region, account and tags; correlate with deployments/Auto Scaling; check CloudTrail for RunInstances; if unknown Regions or GPU instances, suspect leaked credentials and rotate them; contain, then add budgets/anomaly detection.

**The daily data shows a one-day EC2 spike on November 8, not a sustained tripling.** Here’s how I’d investigate it.

### 1. Confirm the timing and size
- **November 8:** $259.75.
- **October 23–November 7:** daily spend ranged from $40.59 to $88.71.
- **November 9:** spend returned to $85.49; subsequent days through November 20 stayed within the earlier range.

The anomaly tool returned **no flagged days**, despite the visible jump. The daily data is therefore the stronger starting point here. I can confirm the spike, but these tools don’t expose resource-level or usage-type details, so **the cause is not yet established**.

First, check whether November 8 coincided with a planned launch, load test, migration, or upfront commitment purchase. [K2]

### 2. Identify which charge increased
In **Cost Explorer**, filter to EC2, use **daily granularity**, and compare November 8 against the preceding two weeks. [K2] Group by **usage type**, then **Region**, **linked account**, and **resource tags**. [K3]

Look for:
- `BoxUsage`: instance hours.
- `EBS:VolumeUsage`: EBS storage.
- `DataTransfer-Out-Bytes`: internet egress.
- `NatGateway-Bytes`: NAT processing. [K3]

This distinguishes “more or larger instances” from storage or networking charges—don’t assume the EC2 total means compute alone. [K3]

### 3. Find what changed
Correlate the spike’s start with deployments, infrastructure-as-code changes, Auto Scaling activity, and scheduled jobs. [K4] Check **CloudTrail** around November 8 for `RunInstances` or related resource-creation calls, identifying who launched resources and where. [K4]

If you find unexpected large or GPU instances in an unused Region, treat that as possible credential compromise: rotate the affected credentials immediately and contact AWS Support. [K4]

### 4. Contain only the confirmed waste
If the investigation identifies forgotten instances or runaway scaling, stop the unnecessary instances or scale down the affected Auto Scaling group; snapshot anything that might hold data before deleting it. [K5]

Because spend returned to its earlier range, first verify whether the responsible resources still exist rather than making blanket cuts.

### 5. Prevent a repeat
Add an EC2 budget alert or Cost Anomaly Detection monitor, and document the responsible resources, owner, cause, and fix. [K6]

**Your first practical action:** get the November 8 **usage-type and Region breakdown**. That will tell us which investigation branch to follow. [K3]

---

**top-service**: Which service has cost the most across all my data, and how much did it cost?

> Reference: EC2 costs the most, $6,200.66 in total.

**EC2** cost the most: **$6,200.66** across all your data, from August 23 to November 20, 2026.

---

**last-7-days**: What was my total AWS spend over the last 7 days, including today?

> Reference: Total spend from 2026-11-14 to today is $809.86.

Your total AWS spend over the last 7 days, including today (**November 14–20, 2026**), was **$809.86 USD**.

---

**anomalies**: Were there any spending anomalies? List each service and date.

> Reference: There are no anomalies.

No spending anomalies were detected in your cost data for **August 23–November 20, 2026**, so there are no services or dates to list.

---

**spike-advice**: Which service had the biggest anomaly, and what should I check to find the cause?

> Reference: Names the service and date of the largest anomaly from the data, and suggests runbook steps such as grouping by usage type, checking recent deployments/Auto Scaling and CloudTrail.

**EC2 had the largest observed service-level spike: $259.75 on November 8.** However, the anomaly detector returned **no flagged anomalies**, so this is a daily-cost spike—not a detector-confirmed anomaly.

EC2’s daily spend over the preceding four weeks ranged from **$40.59 to $88.71**. It returned to **$85.49 on November 9**, suggesting a short-lived event. The billing data does not identify its cause.

To investigate:

1. **Break down EC2 costs in Cost Explorer** for November 8 by usage type, then Region, linked account, and resource tags. Look for instance-hour charges (`BoxUsage`), EBS storage, or data transfer to identify what increased. [K3]
2. **Check what changed around November 8:** deployments, Auto Scaling activity, scheduled jobs, and CloudTrail `RunInstances` events. Also rule out a planned load test, migration, or upfront commitment purchase. [K4][K2]

If you find unexpected large or GPU instances in an unused Region, investigate possible leaked credentials; rotate affected credentials immediately and contact AWS Support. [K4]

---

</details>

Retrieval, rerank and judge calls: 68 (some models unpriced). Chat calls are counted per arm above and saved in chat_traces.
