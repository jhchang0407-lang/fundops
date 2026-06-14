# Deterministic Archive Retrieval Before Vector Indexes

Archive Q&A in the baseline platform retrieves candidate sources deterministically — known-ticker resolution, typed artifact and verdict lookups, screener history, portfolio records, and learning records — and composes answers from compact summaries of those records with citation identifiers, rather than introducing embeddings or vector stores. ADR-0028 already establishes that retrieval indexes are rebuildable projections; this decision sequences them after the deterministic path proves the citation and action contract.

We chose this because the workspace corpus is small and fully structured at baseline, deterministic retrieval is auditable and free, and adding semantic indexes later only widens candidate discovery without changing how claims must resolve to retained evidence and artifacts.
