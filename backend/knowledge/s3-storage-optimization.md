# S3 Storage Cost Optimization

Amazon S3 bills for storage (GB-month, by storage class), requests, data retrieval for infrequent-access and archive classes, and data transfer out. Most S3 savings come from putting data in the right storage class and deleting what is no longer needed.

## Storage classes

- S3 Standard: frequently accessed data, millisecond access, no retrieval fee. The default and most expensive per GB.
- S3 Intelligent-Tiering: moves objects between access tiers automatically based on access patterns, for a small per-object monitoring fee. Good when access patterns are unknown or change. Objects smaller than 128 KB are not monitored and always stay in the frequent access tier.
- S3 Standard-Infrequent Access (Standard-IA): cheaper storage for data accessed less than about once a month, with a per-GB retrieval fee.
- S3 One Zone-IA: like Standard-IA but stored in a single Availability Zone, cheaper, for data you can recreate.
- S3 Glacier Instant Retrieval: archive data that still needs millisecond access, accessed about once a quarter.
- S3 Glacier Flexible Retrieval: archive data retrieved in minutes to hours.
- S3 Glacier Deep Archive: the lowest-cost class, for data retained for years and rarely if ever read; retrieval takes up to 12 hours (standard) or up to 48 hours (bulk).

## Minimum durations and object sizes

Infrequent-access and archive classes have minimum storage durations: 30 days for Standard-IA and One Zone-IA, 90 days for Glacier Instant Retrieval and Glacier Flexible Retrieval, and 180 days for Glacier Deep Archive. Deleting or transitioning an object earlier still bills the remaining days. Standard-IA, One Zone-IA and Glacier Instant Retrieval also bill a minimum object size of 128 KB, so moving many tiny objects there can raise costs instead of lowering them.

## Lifecycle rules

Lifecycle configuration automates transitions and expiration. A typical rule for logs: keep in Standard for 30 days, transition to Standard-IA or Glacier Instant Retrieval, transition to Glacier Deep Archive after 180 days, and expire after the retention period required by policy.

Two lifecycle rules almost every bucket should have: abort incomplete multipart uploads after a few days (their parts are billed but invisible in normal listings), and, on versioned buckets, expire noncurrent object versions after a set number of days. Versioning without noncurrent-version expiration silently keeps every overwritten and deleted object forever.

## Request costs

Request charges matter for workloads with very many small objects or chatty access patterns. Batch small objects together, cache hot objects with CloudFront, and avoid listing large buckets repeatedly; S3 Inventory provides a scheduled list of objects much more cheaply than repeated LIST calls.

## Visibility

S3 Storage Lens shows storage by bucket, storage class, noncurrent versions and incomplete multipart uploads across the organization, and is the quickest way to find the buckets that are worth optimizing.
