# Markdown Export Ships Before the PDF Rendering Pipeline

The baseline platform exports completed artifacts as rendered markdown generated from the Structured Workflow Artifact, while the versioned PDF Rendering Pipeline (ADR-0038, ADR-0039) is deferred to a later slice. Artifact export still flows from stored structured artifacts rather than re-running workflows, and the export path is shaped so a PDF renderer can replace the markdown serializer without changing artifact contracts.

We chose this sequencing because PDF typography and pagination are polish-heavy and easy to add against a stable structured-artifact contract, while shipping the spine, workflows, and surfaces end to end is what proves the contract. PDF remains the primary retail export target; markdown is explicitly an internal/supporting representation in the meantime.
