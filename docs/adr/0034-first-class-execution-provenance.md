# First-Class Execution Provenance

FundOps will retain execution provenance for meaningful model, tool, parser, validation, and workflow steps instead of storing only final artifacts. Provenance should capture the model or tool used, provider and version when available, prompt or template version, input evidence bundle, configuration, output schema version, validation result, errors, retries, usage metadata, and links to produced evidence, findings, artifacts, or rejected outputs.

AI Usage Records are useful for reporting model and token usage, but they are not enough for audit or replay. Execution Provenance Records explain how evidence became a finding, how a finding became an artifact, and which generated outputs were accepted, repaired, rejected, or superseded.
