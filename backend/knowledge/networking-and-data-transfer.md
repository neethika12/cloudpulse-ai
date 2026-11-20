# Networking and Data Transfer Costs

Data transfer is the cost line teams most often fail to predict, because it depends on architecture rather than on any single resource. Prices below are us-east-1 list prices at time of writing; check the AWS pricing pages for current figures.

## Data transfer out to the internet

Data coming into AWS from the internet is free. Data going out to the internet is billed per GB, starting at about $0.09/GB for the first 10 TB per month, with the first 100 GB per month free across services. Serving large files or media directly from EC2 or S3 to users is a common cause of high transfer bills.

## CloudFront

Serving content through Amazon CloudFront usually reduces transfer cost. Transfer from AWS origins such as S3, EC2 or an Application Load Balancer to CloudFront is free, and CloudFront's own per-GB rates and caching reduce how much data leaves the origin. Raise cache hit ratios with sensible TTLs and by not forwarding unnecessary headers, cookies or query strings to the origin.

## Cross-AZ traffic

Traffic between Availability Zones in the same Region costs about $0.01/GB in each direction, so $0.02 per GB moved. Chatty microservices, database replicas and Kafka or Elasticsearch clusters spread across AZs can generate surprising inter-AZ charges. Keep high-volume traffic within one AZ where availability requirements allow, and use topology-aware routing in Kubernetes.

## NAT gateways

A NAT gateway costs about $0.045 per hour plus about $0.045 per GB of data processed, on top of any data transfer charges. Instances in private subnets that pull large amounts of data from S3 or DynamoDB through a NAT gateway pay the processing fee on every GB.

VPC gateway endpoints for S3 and DynamoDB are free and route that traffic privately without the NAT gateway, which is often the single quickest networking saving. Interface endpoints (AWS PrivateLink) for other services have their own hourly and per-GB charges, but can still be cheaper than NAT processing for high-volume traffic.

## Public IPv4 addresses

AWS charges $0.005 per hour (about $3.60 per month) for every public IPv4 address, whether attached to a running instance, a load balancer, a NAT gateway, or left unattached as an Elastic IP. Release unused Elastic IPs and avoid assigning public IPs to instances that do not need them.

## Finding the source

In Cost Explorer, group data transfer costs by usage type: names containing DataTransfer-Out-Bytes are internet egress, DataTransfer-Regional-Bytes are cross-AZ, and NatGateway-Bytes are NAT processing. VPC Flow Logs show which resources generate the traffic.
