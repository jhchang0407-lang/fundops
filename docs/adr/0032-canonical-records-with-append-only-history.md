# Canonical Records With Append-Only History

FundOps will use canonical relational records for durable state and identity, with append-only records or history tables where evidence, completed artifacts, workflow decisions, user responses, portfolio events, and Learning/Evals need auditability. It will not use pure event sourcing as the baseline architecture.

This keeps the important benefits of evented systems: lineage, replayable decisions, historical timelines, and learning evidence. It avoids forcing every current view, portfolio read, or thesis-health status to be rebuilt from an event log when canonical records and rebuildable projections are simpler and more reliable for a local-first investment research platform.
