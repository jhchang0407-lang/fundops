# Forward Migrations After the New Baseline

FundOps will not migrate the current proof-of-concept schema into the new platform architecture, but once the new Local FundOps Workspace baseline exists, schema evolution must be disciplined and forward-only. User workspaces created on the new architecture should be treated as durable local data that must survive app upgrades.

The new baseline should include schema version tracking, ordered migrations, rebuildable projections and retrieval indexes, repair/backfill commands for derived data, and tests that prove older new-architecture fixtures can migrate to the current schema. The clean break applies only to the current PoC; it is not permission for ad hoc schema churn after the reset.
