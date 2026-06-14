# Completed Workflows Share Artifact Identity

FundOps will use one shared artifact identity model for completed workflow outputs rather than letting Screener, Thesis, IC Review, Memo, Thesis Health, Portfolio, Portfolio Review, Library, and Learning/Evals each create independent artifact stores. Workflow-specific tables may still hold typed state and behavior, but any readable or reopenable completed output should be addressable through a stable Workflow Artifact Identifier so Company Page, Library, Archive Q&A, Dashboard, and workflow surfaces open the same exact historical artifact.

This keeps Library and Company Page as projections over retained workflow history rather than duplicate archives. It also preserves the ability to add workflow-specific renderers and detail tables without losing a canonical path back to the completed output that was seen, generated, judged, or cited at the time.
