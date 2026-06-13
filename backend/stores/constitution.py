"""Constitution store: versions, criteria, proposals, projections, universes,
strategy memory, chat sessions (ADR-0006..0011)."""

from __future__ import annotations

from backend.core.workspace import Workspace, dumps, loads, new_id, now_iso
from backend.domain.criteria import Criterion


class ConstitutionStore:
    def __init__(self, ws: Workspace):
        self.ws = ws

    # --- versions -----------------------------------------------------------
    def active_version(self) -> dict | None:
        row = self.ws.query_one(
            "SELECT * FROM constitution_versions WHERE status = 'active' "
            "ORDER BY version_number DESC LIMIT 1"
        )
        return self._version_dict(row) if row else None

    def get_version(self, version_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM constitution_versions WHERE id = ?", (version_id,))
        return self._version_dict(row) if row else None

    def list_versions(self) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM constitution_versions ORDER BY version_number DESC"
        )
        return [self._version_dict(r, include_criteria=False) for r in rows]

    def _version_dict(self, row, include_criteria: bool = True) -> dict:
        d = dict(row)
        d["style_blend"] = loads(d.get("style_blend"), {})
        if include_criteria:
            d["criteria"] = self.criteria_for(d["id"])
        return d

    def criteria_for(self, version_id: str) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM strategy_criteria WHERE version_id = ? ORDER BY criterion_id",
            (version_id,),
        )
        out = []
        for r in rows:
            d = dict(r)
            d["value"] = loads(d.get("value"))
            out.append(d)
        return out

    def criteria_objects(self, version_id: str) -> list[Criterion]:
        return [Criterion.from_dict(d) for d in self.criteria_for(version_id)]

    def activate_version(
        self,
        north_star: str | None,
        style_blend: dict | None,
        narrative: str | None,
        version_rationale: str,
        criteria: list[Criterion],
        projections: dict[str, dict],
        source_proposal_id: str | None = None,
        universe: dict | None = None,
    ) -> dict:
        """Create and activate a new immutable Constitution Version atomically:
        supersede prior active, insert criteria, persist settings projections
        and durable wiring summaries, snapshot universe version."""
        prev = self.active_version()
        # The universe persists across strategy changes unless explicitly
        # changed: without this, a proposal that doesn't restate the universe
        # would leave the new version universe-less and the screener would
        # silently fall back to the config default preset.
        if universe is None:
            inherited = self.active_universe()
            if inherited:
                universe = {"name": inherited.get("name"),
                            "tickers": inherited.get("tickers") or [],
                            "exclusions": inherited.get("exclusions") or [],
                            "source": inherited.get("source") or "inherited"}
        version_number = (prev["version_number"] + 1) if prev else 1
        vid = new_id("cv")
        ts = now_iso()
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE constitution_versions SET status = 'superseded' WHERE status = 'active'"
            )
            conn.execute(
                "INSERT INTO constitution_versions (id, version_number, status, north_star, "
                "style_blend, narrative, version_rationale, source_proposal_id, created_at, activated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (vid, version_number, "active", north_star, dumps(style_blend), narrative,
                 version_rationale, source_proposal_id, ts, ts),
            )
            for c in criteria:
                conn.execute(
                    "INSERT INTO strategy_criteria (id, version_id, criterion_id, kind, metric, "
                    "operator, value, weight, data_support_level, rule_rationale, rule_source, interpretation) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id("crit"), vid, c.criterion_id, c.kind, c.metric, c.operator,
                     dumps(c.value), c.weight, c.data_support_level, c.rule_rationale,
                     c.rule_source, c.interpretation),
                )
            for capability, proj in projections.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings_projections "
                    "(version_id, capability, settings, summary_text, review_items, generated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (vid, capability, dumps(proj["settings"]), proj["summary"],
                     dumps(proj.get("review_items") or []), ts),
                )
            if universe:
                conn.execute(
                    "INSERT INTO universe_versions (id, constitution_version_id, name, tickers, "
                    "exclusions, source, created_at) VALUES (?,?,?,?,?,?,?)",
                    (new_id("uv"), vid, universe.get("name", "custom"),
                     dumps(universe.get("tickers") or []),
                     dumps(universe.get("exclusions") or []),
                     universe.get("source"), ts),
                )
        return self.get_version(vid)

    # --- settings projections -------------------------------------------------
    def projection(self, capability: str, version_id: str | None = None) -> dict | None:
        if version_id is None:
            active = self.active_version()
            if not active:
                return None
            version_id = active["id"]
        row = self.ws.query_one(
            "SELECT * FROM settings_projections WHERE version_id = ? AND capability = ?",
            (version_id, capability),
        )
        if not row:
            return None
        d = dict(row)
        d["settings"] = loads(d["settings"], {})
        d["review_items"] = loads(d.get("review_items"), [])
        return d

    def projections_for(self, version_id: str) -> list[dict]:
        rows = self.ws.query(
            "SELECT * FROM settings_projections WHERE version_id = ? ORDER BY capability", (version_id,)
        )
        out = []
        for r in rows:
            d = dict(r)
            d["settings"] = loads(d["settings"], {})
            d["review_items"] = loads(d.get("review_items"), [])
            out.append(d)
        return out

    # --- universe ----------------------------------------------------------------
    def active_universe(self) -> dict | None:
        active = self.active_version()
        params: tuple = ()
        sql = "SELECT * FROM universe_versions"
        if active:
            sql += " WHERE constitution_version_id = ?"
            params = (active["id"],)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = self.ws.query_one(sql, params)
        if not row:
            return None
        d = dict(row)
        d["tickers"] = loads(d["tickers"], [])
        d["exclusions"] = loads(d.get("exclusions"), [])
        return d

    # --- proposals ----------------------------------------------------------------
    def create_proposal(
        self, payload: dict, validation: dict | None, rationale: str | None,
        chat_session_id: str | None, kind: str = "strategy",
    ) -> dict:
        # Only one pending draft at a time: cancel older pending proposals.
        pid = new_id("prop")
        ts = now_iso()
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE strategy_proposals SET status = 'cancelled', decided_at = ? "
                "WHERE status = 'pending'",
                (ts,),
            )
            conn.execute(
                "INSERT INTO strategy_proposals (id, status, kind, payload, validation, rationale, "
                "chat_session_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (pid, "pending", kind, dumps(payload), dumps(validation), rationale,
                 chat_session_id, ts),
            )
        return self.get_proposal(pid)

    def get_proposal(self, proposal_id: str) -> dict | None:
        row = self.ws.query_one("SELECT * FROM strategy_proposals WHERE id = ?", (proposal_id,))
        if not row:
            return None
        d = dict(row)
        d["payload"] = loads(d["payload"], {})
        d["validation"] = loads(d.get("validation"))
        return d

    def pending_proposal(self) -> dict | None:
        row = self.ws.query_one(
            "SELECT id FROM strategy_proposals WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1"
        )
        return self.get_proposal(row["id"]) if row else None

    def decide_proposal(self, proposal_id: str, status: str, resulting_version_id: str | None = None) -> None:
        assert status in ("accepted", "rejected", "cancelled")
        with self.ws.transaction() as conn:
            conn.execute(
                "UPDATE strategy_proposals SET status = ?, decided_at = ?, resulting_version_id = ? "
                "WHERE id = ?",
                (status, now_iso(), resulting_version_id, proposal_id),
            )

    # --- strategy memory ------------------------------------------------------------
    def remember(self, kind: str, content: dict, source: str | None = None) -> str:
        mid = new_id("mem")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO strategy_memory (id, kind, content, source, created_at) VALUES (?,?,?,?,?)",
                (mid, kind, dumps(content), source, now_iso()),
            )
        return mid

    def memory(self, kind: str | None = None) -> list[dict]:
        sql = "SELECT * FROM strategy_memory WHERE superseded_by IS NULL"
        params: tuple = ()
        if kind:
            sql += " AND kind = ?"
            params = (kind,)
        rows = self.ws.query(sql + " ORDER BY created_at DESC", params)
        return [{**dict(r), "content": loads(r["content"], {})} for r in rows]

    def forget_memory(self, memory_id: str) -> bool:
        """User-directed forget: the row is retained (append-only history)
        but excluded from every active read via the supersede marker."""
        with self.ws.transaction() as conn:
            cur = conn.execute(
                "UPDATE strategy_memory SET superseded_by = ? "
                "WHERE id = ? AND superseded_by IS NULL",
                (f"forgotten:{now_iso()}", memory_id),
            )
            return cur.rowcount > 0

    # --- chat (conversation evidence) ----------------------------------------------
    def latest_chat_session(self) -> str | None:
        """Server-side session anchor: the most recent chat session, so a
        client with no local session id resumes the conversation instead of
        silently minting a new one."""
        row = self.ws.query_one(
            "SELECT id FROM chat_sessions ORDER BY started_at DESC, rowid DESC LIMIT 1"
        )
        return row["id"] if row else None

    def ensure_chat_session(self, session_id: str | None) -> str:
        if session_id:
            row = self.ws.query_one("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
            if row:
                return session_id
        sid = session_id or new_id("chat")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_sessions (id, started_at, server_session_id) VALUES (?,?,?)",
                (sid, now_iso(), self.ws.server_session_id),
            )
        return sid

    def add_chat_message(
        self, session_id: str, role: str, content: str,
        mode: str | None = None, refs: dict | None = None,
    ) -> str:
        mid = new_id("msg")
        with self.ws.transaction() as conn:
            conn.execute(
                "INSERT INTO chat_messages (id, session_id, role, mode, content, refs, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (mid, session_id, role, mode, content, dumps(refs), now_iso()),
            )
        return mid

    def chat_history(self, session_id: str, limit: int = 100) -> list[dict]:
        # rowid breaks same-second ties in insertion order; random message ids
        # would otherwise make intra-second ordering nondeterministic.
        rows = self.ws.query(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at, rowid LIMIT ?",
            (session_id, limit),
        )
        return [{**(d := dict(r)), "refs": loads(d.get("refs"))} for r in rows]

    def chat_threads(self, limit: int = 30) -> list[dict]:
        """Sessions as durable, browsable objects: message count, span, and
        the opening user message as a title seed."""
        rows = self.ws.query(
            "SELECT s.id, s.started_at, COUNT(m.id) AS message_count, "
            "MAX(m.created_at) AS last_at, "
            "(SELECT content FROM chat_messages "
            " WHERE session_id = s.id AND role = 'user' "
            " ORDER BY created_at, rowid LIMIT 1) AS first_user_message "
            "FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id "
            "GROUP BY s.id, s.started_at "
            "ORDER BY COALESCE(MAX(m.created_at), s.started_at) DESC, s.rowid DESC "
            "LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]
