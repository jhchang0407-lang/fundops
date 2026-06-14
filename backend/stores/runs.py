"""Workflow run store: durable runs, steps, workbench state, selection events
(ADR-0036)."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso


class RunStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    def start_run(
        self, kind: str, trigger: str = "user",
        constitution_version_id: str | None = None,
        universe_version_id: str | None = None,
    ) -> str:
        rid = new_id("run")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO workflow_runs (id, kind, status, trigger, constitution_version_id, "
                "universe_version_id, server_session_id, started_at) VALUES (?,?,?,?,?,?,?,?)",
                (rid, kind, "running", trigger, constitution_version_id,
                 universe_version_id, self.ws.server_session_id, now_iso()),
            )
        return rid

    def finish_run(self, run_id: str, status: str = "completed",
                   stats: dict | None = None, error: str | None = None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE workflow_runs SET status = ?, stats = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, dumps(stats), error, now_iso(), run_id),
            )
            # No finalized run may keep a dangling non-terminal step. In the happy
            # path every step is already finished (this matches 0 rows); it closes
            # steps left behind when a run is finalized while one is still in flight.
            if status in ("completed", "failed", "cancelled"):
                conn.execute(
                    "UPDATE workflow_steps SET status = 'failed', "
                    "error = COALESCE(error, 'run finalized while step non-terminal'), "
                    "finished_at = ? "
                    "WHERE run_id = ? AND status IN ('pending','running','retrying')",
                    (now_iso(), run_id),
                )

    def get_run(self, run_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
        if not row:
            return None
        d = dict(row)
        d["stats"] = loads(d.get("stats"), {})
        return d

    def latest_run(self, kind: str, status: str | None = "completed",
                   session_only: bool = False) -> dict | None:
        clauses, params = ["kind = ?"], [kind]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if session_only:
            clauses.append("server_session_id = ?")
            params.append(self.ws.server_session_id)
        row = self.ws.query_one(
            f"SELECT id FROM workflow_runs WHERE {' AND '.join(clauses)} "
            f"ORDER BY started_at DESC LIMIT 1",
            params,
        )
        return self.get_run(row["id"]) if row else None

    def recent_runs(self, limit: int = 30) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [{**(d := dict(r)), "stats": loads(d.get("stats"), {})} for r in rows]

    def active_run_id(self, kind: str) -> str | None:
        """A genuinely in-flight run of this kind — scoped to the current server
        session, since a run can't outlive the process that owns its coroutine."""
        row = self.ws.query_one(
            "SELECT id FROM workflow_runs WHERE kind = ? AND status = 'running' "
            "AND server_session_id = ? ORDER BY started_at DESC LIMIT 1",
            (kind, self.ws.server_session_id),
        )
        return row["id"] if row else None

    def reconcile_orphans(self) -> int:
        """Fail any run left 'running' by a previous server session (the process
        owning its coroutine is gone, so it will never finish) AND cascade-close
        its still-non-terminal steps. Called on startup so stale runs/steps don't
        show as forever-running or block new ones — without the step cascade the
        Runs live-stage-map shows perpetual in-progress on an already-dead run.
        (Steps go to 'failed', not 'cancelled': that is the only terminal status
        the workflow_steps CHECK allows and it matches the run-level sweep.)"""
        with self.ws.transaction() as conn:
            cur = conn.execute(
                "UPDATE workflow_runs SET status = 'failed', "
                "error = 'interrupted — server restarted while running', finished_at = ? "
                "WHERE status = 'running' AND server_session_id != ?",
                (now_iso(), self.ws.server_session_id),
            )
            conn.execute(
                "UPDATE workflow_steps SET status = 'failed', "
                "error = COALESCE(error, 'interrupted — server restarted while running'), "
                "finished_at = ? "
                "WHERE status IN ('pending','running','retrying') AND run_id IN "
                "(SELECT id FROM workflow_runs WHERE status != 'running' "
                " AND server_session_id != ?)",
                (now_iso(), self.ws.server_session_id),
            )
            return cur.rowcount

    # --- steps -------------------------------------------------------------------
    def add_step(self, run_id: str, name: str, item_ref: str | None = None) -> str:
        sid = new_id("step")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO workflow_steps (id, run_id, name, item_ref, status, started_at) "
                "VALUES (?,?,?,?,?,?)",
                (sid, run_id, name, item_ref, "running", now_iso()),
            )
        return sid

    def finish_step(self, step_id: str, status: str = "completed",
                    detail: dict | None = None, error: str | None = None) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE workflow_steps SET status = ?, detail = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, dumps(detail), error, now_iso(), step_id),
            )

    def retry_step(self, step_id: str) -> int:
        """Mark a step retrying; returns the new attempt count."""
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE workflow_steps SET status = 'retrying', attempt = attempt + 1 WHERE id = ?",
                (step_id,),
            )
        row = self.ws.query_one("SELECT attempt FROM workflow_steps WHERE id = ?", (step_id,))
        return row["attempt"] if row else 0

    def steps_for(self, run_id: str) -> list[dict]:
        rows = self.ws.query(
            # rowid (insertion order) breaks ties between steps started within
            # the same second; random ids would scramble them.
            "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY started_at, rowid",
            (run_id,),
        )
        return [{**(d := dict(r)), "detail": loads(d.get("detail"))} for r in rows]

    # --- workbench state (live server session only) ---------------------------------
    def get_workbench(self, capability: str) -> dict | None:
        """Current-session state first; else the newest prior-session state.
        Stage output is durable ("leave anytime, completed work persists") —
        a backend restart must not blank the stage pages."""
        row = self.ws.query_one(
            "SELECT payload FROM workbench_state WHERE server_session_id = ? AND capability = ?",
            (self.ws.server_session_id, capability),
        )
        if row is None:
            row = self.ws.query_one(
                "SELECT payload FROM workbench_state WHERE capability = ? "
                "ORDER BY updated_at DESC LIMIT 1",
                (capability,),
            )
        data = loads(row["payload"], None) if row else None
        # Never present a dead run as live: inherited state may predate a
        # restart that failed its run (reconcile_orphans).
        if isinstance(data, dict) and data.get("status") == "running" and data.get("run_id"):
            run = self.get_run(data["run_id"])
            if run and run.get("status") != "running":
                data["status"] = run["status"]
        return data

    def set_workbench(self, capability: str, payload: dict) -> None:
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workbench_state (server_session_id, capability, payload, updated_at) "
                "VALUES (?,?,?,?)",
                (self.ws.server_session_id, capability, dumps(payload), now_iso()),
            )

    def clear_workbench(self, capability: str | None = None) -> None:
        with self.ws.transaction() as conn:
            if capability:
                conn.execute(
                    "DELETE FROM workbench_state WHERE server_session_id = ? AND capability = ?",
                    (self.ws.server_session_id, capability),
                )
            else:
                conn.execute(
                    "DELETE FROM workbench_state WHERE server_session_id = ?",
                    (self.ws.server_session_id,),
                )

    # --- selection feedback -----------------------------------------------------------
    def record_selection(self, capability: str, run_id: str | None, ticker: str, action: str) -> str:
        sid = new_id("sel")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO selection_events (id, capability, run_id, ticker, action, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (sid, capability, run_id, ticker.upper(), action, now_iso()),
            )
        return sid

    def selection_events(self, capability: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM selection_events"
        params: tuple = ()
        if capability:
            sql += " WHERE capability = ?"
            params = (capability,)
        rows = self.ws.query(sql + " ORDER BY created_at DESC LIMIT ?", (*params, limit))
        return [dict(r) for r in rows]
