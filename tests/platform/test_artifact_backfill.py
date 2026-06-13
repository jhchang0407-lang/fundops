"""RC9: the one-time stored-artifact backfill (backend/core/workspace.py).

The artifact read path serves stored payload/rendered_md verbatim, so generator
fixes never reach already-stored records. The migration re-validates and repairs
them in place: id scrub, score-based hurdle note for empty-hurdle ic_verdicts,
and kernel-field stamping for legacy industry_note payloads. These tests pin the
repair on directly-inserted "legacy" rows and the idempotency guarantee.
"""

from __future__ import annotations

import json

from backend.core import workspace as ws_mod
from backend.core.workspace import new_id, now_iso
from backend.domain.artifact_schemas import SCORE_ONLY_HURDLE_NOTE
from scripts.quality_audit import audit_artifact


def _insert_artifact(stores, kind, payload, rendered_md, created_at, ticker=None):
    aid = new_id("art")
    with stores.ws.transaction() as conn:
        conn.execute(
            "INSERT INTO artifacts (id, kind, entity_id, ticker, run_id, schema_version, "
            "payload, rendered_md, evidence_bundle_id, constitution_version_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (aid, kind, None, ticker, None, payload.get("schema_version", "1.0"),
             json.dumps(payload), rendered_md, None, None, created_at),
        )
    return aid


def test_backfill_repairs_legacy_records(stores):
    created = now_iso()
    # (a) legacy thematic industry_note: payload has only {schema_version, body}.
    note_id = _insert_artifact(
        stores, "industry_note",
        {"schema_version": "1.0",
         "body": {"kind": "thematic_report", "title": "Widget Landscape",
                  "theme": "widgets", "sources": []}},
        rendered_md="## Widgets\n\nThe market grew 12%.", created_at=created)
    # (b) ic_verdict with an empty hurdle list and no explanation.
    verdict_id = _insert_artifact(
        stores, "ic_verdict",
        {"kind": "ic_verdict", "schema_version": "1.0", "generated_at": created,
         "citations": [], "validation": {"ok": True, "errors": [], "warnings": []},
         "body": {"verdict": "pass", "conviction": 70, "constitution_fit": 65,
                  "data_quality": 80, "gate_score": 72, "hurdle_findings": [],
                  "rationale": "Solid compounder."}},
        rendered_md="Solid compounder.", created_at=created, ticker="AAA")
    # (c) ic_verdict leaking raw metric ids in prose.
    leak_id = _insert_artifact(
        stores, "ic_verdict",
        {"kind": "ic_verdict", "schema_version": "1.0", "generated_at": created,
         "citations": [], "validation": {"ok": True, "errors": [], "warnings": []},
         "body": {"verdict": "pass", "conviction": 70, "constitution_fit": 65,
                  "data_quality": 80, "gate_score": 72,
                  "hurdle_findings": [{"criterion_id": "x", "met": True}],
                  "rationale": "Strong fcf_yield and gross_margin support the call."}},
        rendered_md="Strong fcf_yield and gross_margin support the call.",
        created_at=created, ticker="BBB")

    ws_mod.backfill_artifacts(stores.ws.conn)
    stores.ws.conn.commit()

    # (a) kernel fields stamped onto the legacy payload.
    note = stores.artifacts.get(note_id)
    assert note["payload"]["kind"] == "industry_note"
    assert note["payload"]["generated_at"] == created
    assert audit_artifact(note) == [] or "schema" not in str(audit_artifact(note))

    # (b) score-based hurdle note added to body and rendered_md tail.
    verdict = stores.artifacts.get(verdict_id)
    assert verdict["payload"]["body"]["hurdle_note"] == SCORE_ONLY_HURDLE_NOTE
    assert verdict["rendered_md"].rstrip().endswith(f"_{SCORE_ONLY_HURDLE_NOTE}_")
    assert not any("no hurdle findings" in p for p in audit_artifact(verdict))

    # (c) leaked ids scrubbed from both rationale and rendered_md.
    leak = stores.artifacts.get(leak_id)
    assert "fcf_yield" not in leak["payload"]["body"]["rationale"]
    assert "gross_margin" not in leak["payload"]["body"]["rationale"]
    assert "fcf_yield" not in leak["rendered_md"]
    assert "gross_margin" not in leak["rendered_md"]


def test_backfill_is_idempotent(stores):
    created = now_iso()
    vid = _insert_artifact(
        stores, "ic_verdict",
        {"kind": "ic_verdict", "schema_version": "1.0", "generated_at": created,
         "citations": [], "validation": {"ok": True, "errors": [], "warnings": []},
         "body": {"verdict": "pass", "conviction": 70, "constitution_fit": 65,
                  "data_quality": 80, "gate_score": 72, "hurdle_findings": [],
                  "rationale": "Clean."}},
        rendered_md="Clean.", created_at=created, ticker="AAA")
    ws_mod.backfill_artifacts(stores.ws.conn)
    stores.ws.conn.commit()
    once = stores.artifacts.get(vid)
    ws_mod.backfill_artifacts(stores.ws.conn)
    stores.ws.conn.commit()
    twice = stores.artifacts.get(vid)
    assert once["payload"] == twice["payload"]
    assert once["rendered_md"] == twice["rendered_md"]


def test_backfill_migration_is_registered(stores):
    # Migration 6 runs on every workspace boot (no-op on an empty artifacts table).
    rows = stores.ws.query(
        "SELECT name FROM schema_migrations WHERE version = 6")
    assert rows and rows[0]["name"] == "backfill_artifacts_rc9"
