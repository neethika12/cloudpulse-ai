# Tagging, Budgets and FinOps Practice

Cost optimization lasts only when people can see what they spend and who owns it. Tagging, budgets and a regular FinOps rhythm make that possible.

## Cost allocation tags

Tags such as team, service, environment and cost-center let you split the bill by owner. A tag only appears in billing reports and Cost Explorer after it is activated as a cost allocation tag in the Billing console, and it applies only from activation onward, not to past costs. AWS also provides AWS-generated tags such as aws:createdBy.

Enforce tagging with AWS Organizations tag policies (to standardize keys and values) and service control policies or infrastructure-as-code checks (to block untagged resources). Some costs, such as shared data transfer or support, cannot be tagged and need an agreed allocation rule.

## Budgets and alerts

AWS Budgets tracks cost or usage against a threshold and alerts by email or Amazon SNS when actual or forecasted spend crosses it. Set budgets per account, team or tag, with alerts at several thresholds (for example 80% of budget actual and 100% forecasted). Budget actions can apply an IAM or service control policy, or stop specific EC2 or RDS instances, when a threshold is crossed.

AWS Cost Anomaly Detection complements budgets: it uses machine learning to spot unusual spend patterns per service, account or cost category, without needing a fixed threshold.

## Showback and chargeback

Showback reports each team's cloud costs back to it; chargeback actually bills the team's budget. Either one changes behaviour more than a central report nobody reads. Use unit metrics (cost per customer, per order, per 1,000 requests) so teams can see efficiency improve even while total spend grows with the business.

## The FinOps lifecycle

The FinOps Foundation describes three iterative phases. Inform: allocate costs, build visibility and benchmarks. Optimize: rightsize, remove waste, buy commitments and improve architecture. Operate: set policies, budgets and governance, and make cost a regular part of engineering decisions. Teams loop through the phases continuously rather than doing a one-time clean-up.

## A simple monthly review

Each month: review the top five services by spend and their month-over-month change, check commitment coverage and utilization, list idle and unattached resources, review open anomalies, and agree on one or two optimizations with owners and expected savings.
