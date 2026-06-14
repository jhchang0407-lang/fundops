# Atomic Canonical Writes, Rebuildable Projections

FundOps will treat a completed workflow output as one canonical unit of work: workflow status, evidence references or records, evidence bundle manifest, completed artifact identity and payload, key typed workflow records, and timeline/history entries should commit atomically. If the canonical write fails, the output should not appear as a partially completed artifact or decision.

Derived projections such as Library indexes, Dashboard items, current-view caches, search indexes, embeddings, and other retrieval helpers may update after the canonical transaction commits because they are rebuildable. This keeps user-visible truth consistent while allowing projection updates to be retried, repaired, or regenerated without corrupting workflow history.
