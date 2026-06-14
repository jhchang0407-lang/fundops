"""Learning/Evals store: append-only records with lineage and supersession."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class LearningStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def add_record(
        self, kind: str, payload: dict, ticker: str | None = None,
        entity_id: str | None = None, window_months: int | None = None,
        confidence_label: str | None = None, lineage: dict | None = None,
    ) -> str:
        rid = new_id("learn")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_records (id, kind, entity_id, ticker, window_months, payload, "
                "confidence_label, lineage, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, kind, entity_id, ticker.upper() if ticker else None, window_months,
                 dumps(payload), confidence_label, dumps(lineage), now_iso()),
            )
        return rid

    def supersede(self, old_id: str, new_id_: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute("UPDATE learning_records SET superseded_by = ? WHERE id = ?", (new_id_, old_id))

    def records(
        self, kind: str | None = None, ticker: str | None = None,
        current_only: bool = True, limit: int = 200,
    ) -> list[dict]:
        clauses, params = [], []
        if current_only:
            clauses.append("superseded_by IS NULL")
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.ws.query(
            f"SELECT * FROM learning_records {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [self._dict(r) for r in rows]

    def get(self, record_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM learning_records WHERE id = ?", (record_id,))
        return self._dict(row) if row else None

    @staticmethod
    def _dict(row) -> dict:
        d = dict(row)
        d["payload"] = loads(d["payload"], {})
        d["lineage"] = loads(d.get("lineage"))
        return d

    # --- decision register ---------------------------------------------------------
    def add_decision(
        self, kind: str, title: str, rationale: str | None = None,
        alternatives: list | None = None, evidence_refs: list | None = None,
        links: dict | None = None,
    ) -> str:
        did = new_id("dec")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO decision_register (id, kind, title, rationale, alternatives, "
                "evidence_refs, links, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (did, kind, title, rationale, dumps(alternatives), dumps(evidence_refs),
                 dumps(links), now_iso()),
            )
        return did

    def decisions(self, limit: int = 100) -> list[dict]:
        rows = self.ws.query("SELECT * FROM decision_register ORDER BY created_at DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = dict(r)
            for k in ("alternatives", "evidence_refs", "links"):
                d[k] = loads(d.get(k))
            out.append(d)
        return out
