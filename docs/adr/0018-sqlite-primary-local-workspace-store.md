# SQLite Is the Primary Local Workspace Store

FundOps will use SQLite as the primary durable store for the Local FundOps Workspace. This matches the local-first, single-user product shape: one portable database file, no required database daemon, simple backup/export, and enough concurrency for one local app server plus UI requests when configured with WAL and forward-only migrations.

Postgres remains a future option if FundOps becomes hosted, multi-user, or needs materially stronger write concurrency, but it should not be introduced as a local runtime dependency now. DuckDB may be useful later as an analytical sidecar, but it should not own operational workflow truth.
