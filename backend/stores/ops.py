"""Operational store: durable work queue (ADR-0048), execution provenance
(ADR-0034), AI usage records."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class OpsStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- work queue --------------------------------------------------------------
    def enqueue(self, kind: str, payload: dict | None = None, priority: int = 5,
                run_after: str | None = None, max_attempts: int = 3) -> str:
        wid = new_id("work")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO work_queue (id, kind, priority, status, payload, max_attempts, "
                "run_after, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (wid, kind, priority, "queued", dumps(payload), max_attempts, run_after, now_iso()),
            )
        return wid

    def claim_next(self, kind: str | None = None) -> dict | None:
        """Claim the highest-priority due queued item (lower number = higher
        priority); `kind` restricts claiming to one work kind so a processor
        never steals unrelated work."""
        sql = ("SELECT * FROM work_queue WHERE status = 'queued' "
               "AND (run_after IS NULL OR run_after <= ?)")
        params: list = [now_iso()]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        row = self.ws.query_one(sql + " ORDER BY priority, created_at LIMIT 1", params)
        if not row:
            return None
        with self.ws.transaction() as conn:
            cur = conn.execute(
                "UPDATE work_queue SET status = 'running', attempts = attempts + 1 "
                "WHERE id = ? AND status = 'queued'",
                (row["id"],),
            )
            if cur.rowcount == 0:
                return None
        d = dict(row)
        d["payload"] = loads(d.get("payload"), {})
        d["attempts"] = d["attempts"] + 1
        return d

    def reconcile_orphans(self) -> dict:
        """Recover work items left 'running' by a previous process (a claim
        can't outlive the process that made it). Items with attempts left go
        back to 'queued'; exhausted ones become terminal failures."""
        with self.ws.transaction() as conn:
            failed = conn.execute(
                "UPDATE work_queue SET status = 'failed', "
                "last_error = 'orphaned: process exited mid-run', finished_at = ? "
                "WHERE status = 'running' AND attempts >= max_attempts",
                (now_iso(),),
            ).rowcount
            requeued = conn.execute(
                "UPDATE work_queue SET status = 'queued' WHERE status = 'running'"
            ).rowcount
        return {"requeued": requeued, "failed": failed}

    def complete_work(self, work_id: str) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE work_queue SET status = 'completed', finished_at = ? WHERE id = ?",
                (now_iso(), work_id),
            )

    def fail_work(self, work_id: str, error: str) -> None:
        row = self.ws.query_one("SELECT attempts, max_attempts FROM work_queue WHERE id = ?", (work_id,))
        if not row:
            return
        terminal = row["attempts"] >= row["max_attempts"]
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE work_queue SET status = ?, last_error = ?, finished_at = ? WHERE id = ?",
                ("failed" if terminal else "queued", error[:2000],
                 now_iso() if terminal else None, work_id),
            )

    def queue_state(self, limit: int = 50) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM work_queue WHERE status IN ('queued','running','failed') "
            "ORDER BY status, priority, created_at LIMIT ?",
            (limit,),
        )
        return [{**(d := dict(r)), "payload": loads(d.get("payload"), {})} for r in rows]

    # --- execution provenance ----------------------------------------------------------
    def record_provenance(
        self, step: str, kind: str, run_id: str | None = None, model: str | None = None,
        prompt_version: str | None = None, inputs_ref: str | None = None,
        outputs_ref: str | None = None, validation: dict | None = None,
        usage: dict | None = None, rejected_output: str | None = None,
    ) -> str:
        pid = new_id("prov")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO execution_provenance (id, run_id, step, kind, model, prompt_version, "
                "inputs_ref, outputs_ref, validation, usage, rejected_output, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, run_id, step, kind, model, prompt_version, inputs_ref, outputs_ref,
                 dumps(validation), dumps(usage), rejected_output, now_iso()),
            )
        return pid

    def provenance_for_run(self, run_id: str) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM execution_provenance WHERE run_id = ? ORDER BY created_at", (run_id,)
        )
        return [{**(d := dict(r)), "validation": loads(d.get("validation")), "usage": loads(d.get("usage"))}
                for r in rows]

    # --- AI usage records ------------------------------------------------------------
    def record_ai_usage(
        self, capability: str, model: str, tokens_in: int, tokens_out: int,
        est_cost: float | None = None, run_id: str | None = None,
    ) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO ai_usage (id, ts, capability, model, tokens_in, tokens_out, est_cost, run_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (new_id("aiu"), now_iso(), capability, model, tokens_in, tokens_out, est_cost, run_id),
            )

    def ai_usage_summary(self) -> dict:
        rows = self.ws.query(
            "SELECT capability, model, COUNT(*) AS calls, SUM(tokens_in) AS tokens_in, "
            "SUM(tokens_out) AS tokens_out, SUM(est_cost) AS est_cost "
            "FROM ai_usage GROUP BY capability, model ORDER BY tokens_out DESC"
        )
        groups = [dict(r) for r in rows]
        return {
            "groups": groups,
            "total_calls": sum(g["calls"] for g in groups),
            "total_tokens_in": sum(g["tokens_in"] or 0 for g in groups),
            "total_tokens_out": sum(g["tokens_out"] or 0 for g in groups),
            "total_est_cost": sum(g["est_cost"] or 0 for g in groups),
            "note": "Estimated cost is approximate; token counts are the canonical usage record.",
        }
