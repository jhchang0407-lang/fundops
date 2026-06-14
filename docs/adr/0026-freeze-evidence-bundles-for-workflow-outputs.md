# Freeze Evidence Bundles for Workflow Outputs

FundOps will retain a frozen Workflow Evidence Bundle for meaningful workflow outputs, decisions, and completed artifacts rather than linking those outputs only to whatever canonical evidence is latest. The bundle should be represented by an Evidence Bundle Manifest that records the evidence IDs and versions used, source and timing context, Constitution and configuration versions, prompt/model versions when relevant, and workflow-specific inclusion or exclusion decisions.

The manifest should avoid duplicating every source payload while still making replay and audit possible. Workflow-specific evidence packages, such as IC Review and Investment Memo evidence packages, are specialized bundle forms that curate the evidence a workflow actually used.
