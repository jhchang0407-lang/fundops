"""Dashboard store: items project from sources; responses + approvals retained.

A dismissed/snoozed item never reappears for the same source version;
resurfacing requires a materially new source version (CONTEXT relationships).
"""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso

# Response sets matched to why each item type exists.
RESPONSE_SETS = {
    "strategy_proposal": ["accept", "reject", "open"],
    "learning_recommendation": ["accept", "dismiss", "keep_watching", "open"],
    "thesis_break": ["open", "reviewed", "not_material", "thesis_still_intact", "already_acted", "snooze"],
    "portfolio_pressure": ["open", "reviewed", "not_material", "thesis_still_intact", "already_acted", "snooze", "dismiss"],
    "constitution_fit": ["open", "interested", "watch", "not_strategy_fit", "too_risky", "already_know", "dismiss"],
    "workflow_failure": ["open", "retry", "dismiss"],
    "data_gap": ["open", "dismiss", "snooze"],
    "coverage_failure": ["open", "retry", "dismiss"],
}
# Responses that reveal investment judgment become learning feedback signals.
FEEDBACK_RESPONSES = {
    "interested", "watch", "not_strategy_fit", "too_risky", "already_know",
    "not_material", "thesis_still_intact", "already_acted", "reviewed",
    "accept", "reject", "dismiss", "keep_watching",
}
HYGIENE_ONLY = {"open", "snooze", "retry"}


class DashboardStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def upsert_item(
        self, kind: str, section: str, source_type: str, source_id: str,
        source_version: str, title: str, body: str | None = None,
        ticker: str | None = None, severity: str = "normal",
        rank_source: str | None = None, evidence_refs: list | None = None,
    ) -> str | None:
        """Project a dashboard item from its source. Returns the item id, or
        None when this exact source version was already responded to."""
        existing = self.ws.query_one(
            "SELECT id, status FROM dashboard_items WHERE source_type = ? AND source_id = ? "
            "AND source_version = ?",
            (source_type, source_id, source_version),
        )
        if existing:
            return existing["id"] if existing["status"] == "open" else None
        # Resolve stale open items for older versions of the same source.
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE dashboard_items SET status = 'resolved', resolved_at = ? "
                "WHERE source_type = ? AND source_id = ? AND status = 'open'",
                (now_iso(), source_type, source_id),
            )
            iid = new_id("dash")
            conn.execute(
                "INSERT INTO dashboard_items (id, kind, section, source_type, source_id, source_version, "
                "ticker, title, body, severity, rank_source, evidence_refs, response_set, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (iid, kind, section, source_type, source_id, source_version,
                 ticker.upper() if ticker else None, title, body, severity, rank_source,
                 dumps(evidence_refs), dumps(RESPONSE_SETS.get(source_type, ["open", "dismiss"])),
                 "open", now_iso()),
            )
        return iid

    def open_items(self, section: str | None = None) -> list[dict]:
        sql = "SELECT * FROM dashboard_items WHERE status = 'open'"
        params: tuple = ()
        if section:
            sql += " AND section = ?"
            params = (section,)
        rows = self.ws.query(sql + " ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'normal' THEN 1 "
                                   "ELSE 2 END, created_at DESC", params)
        return [self._item_dict(r) for r in rows]

    def get_item(self, item_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM dashboard_items WHERE id = ?", (item_id,))
        return self._item_dict(row) if row else None

    @staticmethod
    def _item_dict(row) -> dict:
        d = dict(row)
        d["evidence_refs"] = loads(d.get("evidence_refs"), [])
        d["response_set"] = loads(d.get("response_set"), [])
        return d

    def respond(self, item_id: str, response: str, payload: dict | None = None) -> dict:
        """Record a Dashboard Item Response; classifies hygiene vs feedback and
        updates item status."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"unknown dashboard item {item_id}")
        # Idempotency: a double-click on an already-settled item must not append
        # duplicate response/learning/approval records or re-fire the proposal
        # effect — report the settled state as a no-op instead.
        if item["status"] in ("resolved", "dismissed") and response not in ("open", "retry"):
            return {"id": None, "kind": "hygiene", "status": item["status"],
                    "item": item, "duplicate": True}
        kind = "both" if (response in FEEDBACK_RESPONSES and response in ("dismiss",)) else (
            "feedback" if response in FEEDBACK_RESPONSES else "hygiene")
        rid = new_id("resp")
        new_status = item["status"]
        if response == "snooze":
            new_status = "snoozed"
        elif response in ("dismiss",):
            new_status = "dismissed"
        elif response in ("open", "retry"):
            new_status = item["status"]
        else:
            new_status = "resolved"
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO dashboard_responses (id, item_id, response, kind, payload, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (rid, item_id, response, kind, dumps(payload), now_iso()),
            )
            if new_status != item["status"]:
                conn.execute(
                    "UPDATE dashboard_items SET status = ?, resolved_at = ? WHERE id = ?",
                    (new_status, now_iso() if new_status != "open" else None, item_id),
                )
        return {"id": rid, "kind": kind, "status": new_status, "item": item}

    def resolve_source(self, source_type: str, source_id: str) -> None:
        """Auto-clear items whose source condition no longer holds."""
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE dashboard_items SET status = 'resolved', resolved_at = ? "
                "WHERE source_type = ? AND source_id = ? AND status IN ('open','snoozed')",
                (now_iso(), source_type, source_id),
            )

    # --- approvals --------------------------------------------------------------
    def record_approval(self, target_type: str, target_id: str, action: str,
                        target_version: str | None = None, effect: str | None = None) -> str:
        aid = new_id("appr")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO approval_records (id, target_type, target_id, target_version, action, "
                "effect, created_at) VALUES (?,?,?,?,?,?,?)",
                (aid, target_type, target_id, target_version, action, effect, now_iso()),
            )
        return aid

    def approvals(self, limit: int = 100) -> list[dict]:
        rows = self.ws.query("SELECT * FROM approval_records ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]
