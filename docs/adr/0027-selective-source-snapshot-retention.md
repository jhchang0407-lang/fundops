# Selective Source Snapshot Retention

FundOps will retain durable Evidence Source Records for source identity, provenance, timing, integrity, and locator information, while retaining raw or normalized Evidence Source Snapshots selectively rather than storing every provider payload or source document forever. Canonical Evidence Records should link back to source records, excerpts, hashes, normalized payloads, external locators, or snapshots sufficient to audit the evidence they support.

Full source snapshots should be kept when the source is material to a completed artifact, expensive or unreliable to reacquire, needed for replay, or important for citation integrity. Otherwise FundOps may keep a lighter retention tier such as source identity, hash, fetch metadata, extracted excerpts, and derived canonical evidence so the local workspace stays portable without losing provenance.
