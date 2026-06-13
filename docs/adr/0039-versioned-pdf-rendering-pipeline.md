# Versioned PDF Rendering Pipeline

FundOps will generate Retail Artifact PDFs through a versioned PDF Rendering Pipeline rather than by printing the current reader UI. The pipeline should render from Structured Workflow Artifacts or controlled rendered snapshots using artifact-type-specific templates, typography, pagination, citations, tables, headers, footers, metadata, and export-version information.

The on-screen Workflow Artifact Reader can optimize for navigation and interaction, while PDF export should optimize for polished retail-investor reading, saving, and sharing. Exporting a PDF should not rerun the underlying workflow or depend on unstable browser presentation state.
