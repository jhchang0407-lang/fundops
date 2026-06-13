"""Bulk-first data ingestion (ADR-0059).

Breadth data comes from official bulk products — SEC companyfacts.zip for
reported fundamentals, daily form-index files for filing detection, batched
price downloads, quarterly insider data sets — instead of per-company API
calls. Raw dumps live in opconfig.cache_dir(); only universe-scoped,
decision-relevant rows land in workspace tables, always through the stores.
Live provider calls stay reserved for interactive evidence work and the
targeted top-ups the daily index triggers.
"""
