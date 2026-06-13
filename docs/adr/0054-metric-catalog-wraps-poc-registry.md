# Financial Metric Catalog Wraps the Existing Metric Registry

The Financial Metric Catalog required by ADR-0016 is implemented as a governed wrapper over the proof-of-concept metric schema registry rather than a parallel new registry. The wrapper adds catalog versioning, hard-gate decision authority, missing-data behavior, and the Supported Thesis Health Field Catalog (allowed metric, cadence, and lookback combinations), while reusing the registry's 125 metric definitions, aliases, operators, and sector-specific entries. Every Calculated Financial Observation records the catalog version that governed it.

We chose wrapping over rewriting because ADR-0017 directs strengthening the existing financial pipeline incrementally, and the registry already encodes hard-won alias and range knowledge. The catalog version constant lives in code; bumping it when definitions change is what keeps historical observations replayable.
