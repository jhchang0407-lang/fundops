"""Artifact store: shared completed-artifact identity plus typed workflow rows
(ADR-0020, ADR-0037). Artifacts are append-only; newer versions supersede."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class ArtifactStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def save_artifact(
        self, kind: str, payload: dict, ticker: str | None = None,
        entity_id: str | None = None, run_id: str | None = None,
        rendered_md: str | None = None, evidence_bundle_id: str | None = None,
        constitution_version_id: str | None = None, supersedes: str | None = None,
    ) -> str:
        aid = new_id("art")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO artifacts (id, kind, entity_id, ticker, run_id, schema_version, payload, "
                "rendered_md, evidence_bundle_id, constitution_version_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (aid, kind, entity_id, ticker.upper() if ticker else None, run_id,
                 payload.get("schema_version", "1.0"), dumps(payload), rendered_md,
                 evidence_bundle_id, constitution_version_id, now_iso()),
            )
            if supersedes:
                conn.execute("UPDATE artifacts SET superseded_by = ? WHERE id = ?", (aid, supersedes))
        return aid

    def get(self, artifact_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        if not row:
            return None
        d = dict(row)
        d["payload"] = loads(d["payload"], {})
        return d

    def for_ticker(self, ticker: str, kind: str | None = None, limit: int = 100) -> list[dict]:
        clauses, params = ["ticker = ?"], [ticker.upper()]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        rows = self.ws.query(
            f"SELECT id, kind, ticker, entity_id, run_id, schema_version, created_at, superseded_by, "
            f"constitution_version_id FROM artifacts WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(r) for r in rows]

    def for_run(self, run_id: str) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)
        )
        return [{**dict(r), "payload": loads(r["payload"], {})} for r in rows]

    def latest_for_ticker(self, ticker: str, kind: str) -> dict | None:
        row = self.ws.query_one(
            "SELECT id FROM artifacts WHERE ticker = ? AND kind = ? AND superseded_by IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (ticker.upper(), kind),
        )
        return self.get(row["id"]) if row else None

    def recent(self, kind: str | None = None, limit: int = 50) -> list[dict]:
        sql = ("SELECT id, kind, ticker, entity_id, run_id, created_at FROM artifacts")
        params: tuple = ()
        if kind:
            sql += " WHERE kind = ?"
            params = (kind,)
        rows = self.ws.query(sql + " ORDER BY created_at DESC LIMIT ?", (*params, limit))
        return [dict(r) for r in rows]

    # --- typed screener rows --------------------------------------------------------
    def save_screener_result(
        self, run_id: str, ticker: str, passed: bool, entity_id: str | None = None,
        rank: int | None = None, score: float | None = None,
        ranking_components: list | None = None, pass_evidence: list | None = None,
        fail_reasons: list | None = None, selected: bool = False,
        selection_order: int | None = None, snapshot_artifact_id: str | None = None,
    ) -> str:
        rid = new_id("scr")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO screener_results (id, run_id, entity_id, ticker, passed, rank, score, "
                "ranking_components, pass_evidence, fail_reasons, selected, selection_order, "
                "snapshot_artifact_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, run_id, entity_id, ticker.upper(), 1 if passed else 0, rank, score,
                 dumps(ranking_components), dumps(pass_evidence), dumps(fail_reasons),
                 1 if selected else 0, selection_order, snapshot_artifact_id),
            )
        return rid

    def screener_results(self, run_id: str, passed_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM screener_results WHERE run_id = ?"
        if passed_only:
            sql += " AND passed = 1"
        rows = self.ws.query(sql + " ORDER BY rank IS NULL, rank", (run_id,))
        out = []
        for r in rows:
            d = dict(r)
            for k in ("ranking_components", "pass_evidence", "fail_reasons"):
                d[k] = loads(d.get(k), [])
            out.append(d)
        return out

    def set_screener_selection(self, run_id: str, ticker: str, selected: bool,
                               selection_order: int | None = None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE screener_results SET selected = ?, selection_order = ? "
                "WHERE run_id = ? AND ticker = ?",
                (1 if selected else 0, selection_order, run_id, ticker.upper()),
            )

    def screener_history_for_ticker(self, ticker: str, limit: int = 20) -> list[dict]:
        rows = self.ws.query(
            "SELECT s.*, r.started_at AS run_started_at, r.constitution_version_id "
            "FROM screener_results s JOIN workflow_runs r ON r.id = s.run_id "
            "WHERE s.ticker = ? ORDER BY r.started_at DESC LIMIT ?",
            (ticker.upper(), limit),
        )
        out = []
        for r in rows:
            d = dict(r)
            for k in ("ranking_components", "pass_evidence", "fail_reasons"):
                d[k] = loads(d.get(k), [])
            out.append(d)
        return out

    # --- typed IC verdict rows ----------------------------------------------------------
    def save_ic_verdict(
        self, ticker: str, verdict: str, run_id: str | None = None,
        entity_id: str | None = None, thesis_artifact_id: str | None = None,
        conviction: float | None = None, constitution_fit: float | None = None,
        data_quality: float | None = None, gate_score: float | None = None,
        blend: dict | None = None, cutoff: float | None = None,
        components: dict | None = None, hurdle_findings: list | None = None,
        rationale: str | None = None, is_override: bool = False,
        prior_verdict: str | None = None, constitution_version_id: str | None = None,
        artifact_id: str | None = None,
    ) -> str:
        vid = new_id("icv")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO ic_verdicts (id, run_id, ticker, entity_id, thesis_artifact_id, verdict, "
                "conviction, constitution_fit, data_quality, gate_score, blend, cutoff, components, "
                "hurdle_findings, rationale, is_override, prior_verdict, constitution_version_id, "
                "artifact_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (vid, run_id, ticker.upper(), entity_id, thesis_artifact_id, verdict,
                 conviction, constitution_fit, data_quality, gate_score, dumps(blend), cutoff,
                 dumps(components), dumps(hurdle_findings), rationale, 1 if is_override else 0,
                 prior_verdict, constitution_version_id, artifact_id, now_iso()),
            )
        return vid

    def ic_verdicts_for_run(self, run_id: str) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM ic_verdicts WHERE run_id = ? ORDER BY created_at", (run_id,)
        )
        return [self._verdict_dict(r) for r in rows]

    def latest_ic_verdict(self, ticker: str, run_id: str | None = None) -> dict | None:
        clauses, params = ["ticker = ?"], [ticker.upper()]
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        row = self.ws.query_one(
            # rowid breaks ties for verdicts created within the same second
            # (e.g. an immediate user override of a fresh verdict).
            f"SELECT * FROM ic_verdicts WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC, rowid DESC LIMIT 1",
            params,
        )
        return self._verdict_dict(row) if row else None

    @staticmethod
    def _verdict_dict(row) -> dict:
        d = dict(row)
        for k in ("blend", "components", "hurdle_findings"):
            d[k] = loads(d.get(k))
        return d
