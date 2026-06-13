"""Canonical evidence store: sources and frozen bundles (ADR-0021/25/26/27)."""

from __future__ import annotations

import hashlib

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class EvidenceStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def add_source(
        self, kind: str, locator: str | None = None, title: str | None = None,
        publisher: str | None = None, content: str | None = None,
        retention_tier: str = "identity", excerpt: str | None = None,
    ) -> str:
        sid = new_id("src")
        content_hash = hashlib.sha256(content.encode()).hexdigest() if content else None
        snapshot = content if retention_tier == "snapshot" else None
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence_sources (id, kind, locator, title, publisher, content_hash, "
                "retention_tier, excerpt, snapshot, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, kind, locator, title, publisher, content_hash,
                 retention_tier, excerpt, snapshot, now_iso()),
            )
        return sid

    def get_source(self, source_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM evidence_sources WHERE id = ?", (source_id,))
        return dict(row) if row else None

    def freeze_bundle(self, manifest: dict) -> str:
        """Freeze a Workflow Evidence Bundle manifest (ADR-0026): evidence ids,
        versions, constitution/universe versions, prompt versions, inclusion notes."""
        bid = new_id("bundle")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence_bundles (id, manifest, created_at) VALUES (?,?,?)",
                (bid, dumps(manifest), now_iso()),
            )
        return bid

    def get_bundle(self, bundle_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM evidence_bundles WHERE id = ?", (bundle_id,))
        if not row:
            return None
        d = dict(row)
        d["manifest"] = loads(d["manifest"], {})
        return d

    def gc_orphan_bundles(self) -> int:
        """Delete frozen bundles no artifact references. A bundle is frozen
        BEFORE the artifact write (thesis/ic_review/memo/screener), so a run that
        aborts after the freeze but before the save strands it. Reclaim those on
        the startup sweep — never mid-run, where a bundle is legitimately frozen-
        but-not-yet-written. Returns the number of bundles removed."""
        with self.ws.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM evidence_bundles WHERE id NOT IN "
                "(SELECT evidence_bundle_id FROM artifacts WHERE evidence_bundle_id IS NOT NULL)"
            )
            return cur.rowcount
