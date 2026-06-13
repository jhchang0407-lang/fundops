# Normalize Workflow Records, Keep Artifact Payloads Flexible

FundOps will use normalized SQLite tables for workflow identity, relationships, queryable state, provenance, user responses, and current projections, while using JSON or text payloads for generated artifact bodies, provider responses, model outputs, and point-in-time audit snapshots. This keeps the Local FundOps Workspace queryable and durable without forcing every AI-generated memo, SEC-derived payload, or source-shaped record into a prematurely rigid schema.

The rule of thumb is that fields needed for filtering, joining, replay, lineage, Dashboard surfacing, Company Page history, Portfolio state, Thesis Health, or Learning/Evals should graduate into typed columns or child tables. Fields needed mainly to preserve what was seen, generated, cited, or exported may remain in payloads with stable identifiers, hashes, timestamps, and source metadata around them.
