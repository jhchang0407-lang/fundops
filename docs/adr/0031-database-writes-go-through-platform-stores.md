# Database Writes Go Through Platform Stores

FundOps workflow modules, agents, API routes, and UI-facing handlers should not hand-roll persistence or write arbitrary SQL against the workspace database. Database writes should flow through explicit platform stores or services that own stable boundaries such as investment identity, evidence, sources, artifacts, workflow runs, evidence bundle manifests, portfolio records, projections, and retrieval indexes.

This keeps the new architecture coherent as the platform grows. Workflow code may produce domain outputs, but persistence should be centralized enough that identity, provenance, point-in-time evidence, artifact links, and projection rebuild behavior stay consistent across capabilities.
