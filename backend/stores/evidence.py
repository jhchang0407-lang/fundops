"""Canonical evidence store: sources, records, frozen bundles (ADR-0021/25/26/27)."""

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

    def add_record(
        self, family: str, payload: dict, ticker: str | None = None,
        entity_id: str | None = None, as_of: str | None = None,
        source_id: str | None = None, quality: str | None = None,
        run_id: str | None = None,
    ) -> str:
        rid = new_id("ev")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence_records (id, family, entity_id, ticker, as_of, captured_at, "
                "payload, source_id, quality, created_by_run_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rid, family, entity_id, ticker.upper() if ticker else None, as_of,
                 now_iso(), dumps(payload), source_id, quality, run_id),
            )
        return rid

    def get_record(self, record_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM evidence_records WHERE id = ?", (record_id,))
        if not row:
            return None
        d = dict(row)
        d["payload"] = loads(d["payload"], {})
        return d

    def records_for(
        self, ticker: str | None = None, entity_id: str | None = None,
        family: str | None = None, limit: int = 200,
    ) -> list[dict]:
        clauses, params = ["superseded_by IS NULL"], []
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if family:
            clauses.append("family = ?")
            params.append(family)
        rows = self.ws.query(
            f"SELECT * FROM evidence_records WHERE {' AND '.join(clauses)} "
            f"ORDER BY captured_at DESC LIMIT ?",
            (*params, limit),
        )
        return [{**dict(r), "payload": loads(r["payload"], {})} for r in rows]

    def supersede(self, old_record_id: str, new_record_id: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE evidence_records SET superseded_by = ? WHERE id = ?",
                (new_record_id, old_record_id),
            )

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
