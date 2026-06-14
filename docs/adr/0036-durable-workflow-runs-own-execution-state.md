# Durable Workflow Runs Own Execution State

FundOps will model long-running work as durable Workflow Run Records with Workflow Step Records, status, retries, failures, evidence bundle links, handoffs, and produced artifacts. HTTP/API calls, UI actions, and schedules may start, inspect, pause, resume, cancel, or retry runs, but they should not be the durable workflow state themselves.

This applies to workflows such as Screener, Thesis, IC Review, Memo, Thesis Health, Portfolio refresh, Learning/Evals, and Pipeline runs. Durable orchestration makes progress, failures, replay, evidence boundaries, Dashboard surfacing, and artifact lineage explicit instead of hiding them inside route handlers or transient tasks.
