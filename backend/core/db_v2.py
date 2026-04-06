"""FundOps Database v2 — Constitution, judgment events, strategy, and outcome tracking.

Extends the core DB with tables for:
- constitution: The investor's living document (north star, signals, doctrine)
- constitution_changelog: Versioned evolution history
- judgment_events: Unified event stream linking every decision to outcomes
- strategy_profiles: User investment strategies (legacy, reads fall through to constitution)
- strategy_versions: Versioned scoring code + label maps
- screener_runs: Per-run results linked to strategy version
- feedback_records: User feedback on screener results
- outcome_snapshots: Periodic checks on screened stocks (90d-1095d)
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional
from pathlib import Path


V2_SCHEMA_SQL = """
-- Constitution: the investor's living document.
-- This is the primary system object. strategy_profiles is kept for backward compat.
CREATE TABLE IF NOT EXISTS constitution (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Identity
    north_star TEXT,
    north_star_summary TEXT,
    style_identity TEXT,
    time_horizon TEXT,

    -- Approval criteria (what IC checks against)
    must_have_signals JSON,
    anti_signals JSON,
    ic_hurdles JSON,
    disqualifiers JSON,

    -- Portfolio doctrine
    position_sizing JSON,
    concentration_rules JSON,
    sell_discipline JSON,

    -- Scoring dimensions (flows to screener codegen)
    dimensions JSON,
    sector_routing JSON,

    -- Agent profiles (how each agent adapts)
    agent_profiles JSON,

    -- Universe
    universe_type TEXT DEFAULT 'preset',
    universe_name TEXT DEFAULT 'us_largecap_200',
    universe_custom JSON,

    -- Autonomy
    autonomy_mode TEXT DEFAULT 'suggest',

    -- Link to active scoring code
    active_version_id TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS constitution_changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    constitution_id TEXT NOT NULL,
    version_from INTEGER,
    version_to INTEGER,
    change_type TEXT,
    change_summary TEXT,
    changed_fields JSON,
    trigger TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (constitution_id) REFERENCES constitution(id)
);

-- Judgment events: unified stream linking every decision to outcomes.
-- Every important action in the system produces a linked event.
CREATE TABLE IF NOT EXISTS judgment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    ticker TEXT,
    constitution_version INTEGER,
    agent TEXT,
    data JSON,
    rationale TEXT,
    parent_event_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_event_id) REFERENCES judgment_events(id)
);

CREATE INDEX IF NOT EXISTS idx_je_ticker ON judgment_events(ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_je_type ON judgment_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_je_chain ON judgment_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_je_constitution ON judgment_events(constitution_version);
CREATE INDEX IF NOT EXISTS idx_cl_constitution ON constitution_changelog(constitution_id, version_to);

-- Conversation history: persists strategy conversations across sessions.
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    constitution_id TEXT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    extracted JSON,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ch_constitution ON conversation_history(constitution_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ch_session ON conversation_history(session_id, created_at);

-- Library entries: unified research archive with metrics for similarity search.
CREATE TABLE IF NOT EXISTS library_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    constitution_version INTEGER,
    verdict TEXT,
    conviction INTEGER,
    expected_return REAL,
    discount_pct REAL,
    sector TEXT,
    industry TEXT,
    gross_margin REAL,
    roic REAL,
    revenue_growth REAL,
    debt_equity REAL,
    key_assumptions JSON,
    judgment_event_id INTEGER,
    data JSON,
    created_at TEXT NOT NULL,
    FOREIGN KEY (judgment_event_id) REFERENCES judgment_events(id)
);

CREATE INDEX IF NOT EXISTS idx_lib_ticker ON library_entries(ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_lib_sector ON library_entries(sector, entry_type);
CREATE INDEX IF NOT EXISTS idx_lib_verdict ON library_entries(verdict, entry_type);
CREATE INDEX IF NOT EXISTS idx_lib_type ON library_entries(entry_type, created_at);

-- Refinement proposals: AI-suggested changes to scoring code based on feedback patterns.
CREATE TABLE IF NOT EXISTS refinement_proposals (
    id TEXT PRIMARY KEY,
    constitution_id TEXT,
    pattern_type TEXT NOT NULL,
    pattern_tag TEXT,
    pattern_count INTEGER,
    pattern_tickers JSON,
    proposal TEXT NOT NULL,
    analysis TEXT,
    code_change TEXT,
    confidence REAL,
    risk TEXT,
    evidence_summary TEXT,
    status TEXT DEFAULT 'pending',
    user_response TEXT,
    applied_version_id TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (constitution_id) REFERENCES constitution(id)
);

CREATE INDEX IF NOT EXISTS idx_rp_status ON refinement_proposals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_rp_constitution ON refinement_proposals(constitution_id);

-- Legacy strategy_profiles table (kept for backward compat with screener v2 flow)
CREATE TABLE IF NOT EXISTS strategy_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    autonomy_mode TEXT DEFAULT 'copilot',
    north_star TEXT,
    dimensions JSON,
    sector_routing JSON,
    universe_type TEXT DEFAULT 'preset',
    universe_name TEXT DEFAULT 'us_largecap_200',
    universe_custom JSON,
    active_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_versions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    scoring_code TEXT NOT NULL,
    label_map JSON,
    explanation TEXT,
    change_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES strategy_profiles(id)
);

CREATE TABLE IF NOT EXISTS tickers (
    ticker TEXT PRIMARY KEY,
    added_at TEXT,
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    first_seen_at TEXT,
    current_lifecycle TEXT,
    is_owned INTEGER DEFAULT 0,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS screener_runs (
    id TEXT PRIMARY KEY,
    strategy_version_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    universe_size INTEGER,
    scored_count INTEGER,
    failed_count INTEGER,
    top_results JSON,
    all_results JSON,
    duration_s REAL,
    status TEXT DEFAULT 'complete',
    error_message TEXT,
    FOREIGN KEY (strategy_version_id) REFERENCES strategy_versions(id)
);

CREATE TABLE IF NOT EXISTS feedback_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screener_run_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    feedback TEXT NOT NULL,
    dismiss_reason TEXT,
    note TEXT,
    score_at_feedback REAL,
    rank_at_feedback INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (screener_run_id) REFERENCES screener_runs(id),
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS outcome_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screener_run_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    screened_at TEXT NOT NULL,
    check_at TEXT NOT NULL,
    days_elapsed INTEGER NOT NULL,
    price_at_screen REAL,
    price_at_check REAL,
    return_pct REAL,
    benchmark_return_pct REAL,
    alpha_pct REAL,
    thesis_integrity JSON,
    goal_alignment JSON,
    status TEXT DEFAULT 'complete',
    error_message TEXT,
    FOREIGN KEY (screener_run_id) REFERENCES screener_runs(id),
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE INDEX IF NOT EXISTS idx_sv_strategy ON strategy_versions(strategy_id, version_number);
CREATE INDEX IF NOT EXISTS idx_sr_version ON screener_runs(strategy_version_id, run_at);
CREATE INDEX IF NOT EXISTS idx_fb_run ON feedback_records(screener_run_id, ticker);
CREATE INDEX IF NOT EXISTS idx_fb_ticker ON feedback_records(ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_os_run ON outcome_snapshots(screener_run_id, ticker);
CREATE INDEX IF NOT EXISTS idx_os_due ON outcome_snapshots(screened_at, days_elapsed);

-- Ticker financials: versioned SEC-enriched financial snapshots per ticker.
-- Screener persists after Phase 2 enrichment. All downstream agents read from here.
-- Old snapshots archived (is_latest=0) for library trend analysis.
CREATE TABLE IF NOT EXISTS ticker_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    financial_data JSON NOT NULL,
    source TEXT DEFAULT 'sec+yfinance',
    screener_run_id TEXT,
    fetched_at TEXT NOT NULL,
    is_latest INTEGER DEFAULT 1,
    FOREIGN KEY (screener_run_id) REFERENCES screener_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_tf_ticker_latest ON ticker_financials(ticker, is_latest);
CREATE INDEX IF NOT EXISTS idx_tf_fetched ON ticker_financials(fetched_at);
"""


class ScreenerV2DB:
    """Database layer for Screener v2 tables.

    Shares a SQLite connection with the core FundOpsDB. Initialize with
    the same db_path to share the database file.
    """

    def __init__(self, conn: sqlite3.Connection = None, db_path: Path | str = None):
        if conn:
            self.conn = conn
            self._owns_conn = False
        else:
            db_path = Path(db_path) if db_path else (Path.home() / ".fundops" / "fundops.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(db_path), timeout=30)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=30000")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self._owns_conn = True
        self.conn.executescript(V2_SCHEMA_SQL)
        self.conn.commit()

        # Apply any pending schema migrations
        from backend.core.migrations import run_migrations
        try:
            run_migrations(self.conn)
        except Exception:
            pass  # Migrations may have already been applied by v1 DB

        # Ensure archived_at columns exist for archive-based reset
        for tbl in ("constitution", "strategy_profiles"):
            try:
                self.conn.execute(f"ALTER TABLE {tbl} ADD COLUMN archived_at TEXT")
                self.conn.commit()
            except Exception:
                pass  # Column already exists

    def close(self):
        if self._owns_conn and self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json(self, obj: Any) -> Optional[str]:
        return json.dumps(obj, default=str) if obj is not None else None

    def _rows_to_dicts(self, cursor) -> list[dict]:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # --- Constitution ---

    _CONSTITUTION_JSON_FIELDS = frozenset({
        "must_have_signals", "anti_signals", "ic_hurdles", "disqualifiers",
        "position_sizing", "concentration_rules", "sell_discipline",
        "dimensions", "sector_routing", "agent_profiles", "universe_custom",
    })

    def _parse_constitution(self, row: dict) -> dict:
        for key in self._CONSTITUTION_JSON_FIELDS:
            if row.get(key) and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    def create_constitution(self, constitution_id: str, name: str, *,
                            north_star: str = None, north_star_summary: str = None,
                            style_identity: str = None, time_horizon: str = None,
                            must_have_signals: list = None, anti_signals: list = None,
                            ic_hurdles: dict = None, disqualifiers: list = None,
                            position_sizing: dict = None, concentration_rules: dict = None,
                            sell_discipline: dict = None, dimensions: dict = None,
                            sector_routing: dict = None, agent_profiles: dict = None,
                            universe_type: str = "preset", universe_name: str = "us_largecap_200",
                            autonomy_mode: str = "suggest") -> dict:
        now = self._now()
        self.conn.execute(
            """INSERT INTO constitution
               (id, name, version, north_star, north_star_summary, style_identity,
                time_horizon, must_have_signals, anti_signals, ic_hurdles, disqualifiers,
                position_sizing, concentration_rules, sell_discipline, dimensions,
                sector_routing, agent_profiles, universe_type, universe_name,
                autonomy_mode, created_at, updated_at)
               VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (constitution_id, name, north_star, north_star_summary, style_identity,
             time_horizon, self._json(must_have_signals), self._json(anti_signals),
             self._json(ic_hurdles), self._json(disqualifiers),
             self._json(position_sizing), self._json(concentration_rules),
             self._json(sell_discipline), self._json(dimensions),
             self._json(sector_routing), self._json(agent_profiles),
             universe_type, universe_name, autonomy_mode, now, now)
        )
        self.conn.commit()
        return self.get_constitution(constitution_id)

    def get_constitution(self, constitution_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM constitution WHERE id = ?", (constitution_id,)
        ))
        if not rows:
            return None
        return self._parse_constitution(rows[0])

    def get_active_constitution(self) -> Optional[dict]:
        """Get the most recently updated non-archived constitution."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM constitution WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 1"
        ))
        if not rows:
            # Fall through to strategy_profiles for backward compat
            strategy = self.get_active_strategy()
            if strategy:
                return self._strategy_to_constitution(strategy)
            return None
        return self._parse_constitution(rows[0])

    def get_changelog(self, constitution_id: str, limit: int = 50) -> list[dict]:
        """Get the changelog for a constitution."""
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM constitution_changelog WHERE constitution_id = ? ORDER BY created_at DESC LIMIT ?",
            (constitution_id, limit),
        ))

    def get_constitution_by_version(self, version: int) -> Optional[dict]:
        """Get a constitution by its version number.

        Falls back to active constitution if version not found.
        """
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM constitution WHERE version = ? ORDER BY updated_at DESC LIMIT 1",
            (version,)
        ))
        if not rows:
            return None
        return self._parse_constitution(rows[0])

    def _strategy_to_constitution(self, strategy: dict) -> dict:
        """Convert a legacy strategy_profiles row to constitution format."""
        return {
            "id": strategy["id"],
            "name": strategy["name"],
            "version": 1,
            "north_star": strategy.get("north_star"),
            "north_star_summary": None,
            "style_identity": None,
            "time_horizon": None,
            "must_have_signals": None,
            "anti_signals": None,
            "ic_hurdles": None,
            "disqualifiers": None,
            "position_sizing": None,
            "concentration_rules": None,
            "sell_discipline": None,
            "dimensions": strategy.get("dimensions"),
            "sector_routing": strategy.get("sector_routing"),
            "agent_profiles": None,
            "universe_type": strategy.get("universe_type", "preset"),
            "universe_name": strategy.get("universe_name", "us_largecap_200"),
            "universe_custom": strategy.get("universe_custom"),
            "autonomy_mode": strategy.get("autonomy_mode", "suggest"),
            "active_version_id": strategy.get("active_version_id"),
            "created_at": strategy.get("created_at"),
            "updated_at": strategy.get("updated_at"),
        }

    def update_constitution(self, constitution_id: str, **kwargs) -> dict:
        allowed = {
            "name", "north_star", "north_star_summary", "style_identity", "time_horizon",
            "must_have_signals", "anti_signals", "ic_hurdles", "disqualifiers",
            "position_sizing", "concentration_rules", "sell_discipline",
            "dimensions", "sector_routing", "agent_profiles",
            "universe_type", "universe_name", "universe_custom",
            "autonomy_mode", "active_version_id",
        }
        updates = {}
        changed_fields = []
        for k, v in kwargs.items():
            if k in allowed:
                changed_fields.append(k)
                if k in self._CONSTITUTION_JSON_FIELDS and not isinstance(v, str):
                    updates[k] = self._json(v)
                else:
                    updates[k] = v
        if not updates:
            return self.get_constitution(constitution_id)

        # Bump version
        current = self.get_constitution(constitution_id)
        old_version = current["version"] if current else 0
        new_version = old_version + 1
        updates["version"] = new_version
        updates["updated_at"] = self._now()

        set_clause = ", ".join(f"{col} = ?" for col in updates)
        params = list(updates.values()) + [constitution_id]
        self.conn.execute(f"UPDATE constitution SET {set_clause} WHERE id = ?", params)

        # Record changelog
        self.record_changelog(
            constitution_id=constitution_id,
            version_from=old_version,
            version_to=new_version,
            change_type=kwargs.get("_change_type", "conversation"),
            change_summary=kwargs.get("_change_summary", f"Updated: {', '.join(changed_fields)}"),
            changed_fields=changed_fields,
            trigger=kwargs.get("_trigger", "user"),
        )
        self.conn.commit()
        return self.get_constitution(constitution_id)

    # --- Constitution Changelog ---

    def record_changelog(self, constitution_id: str, version_from: int = None,
                         version_to: int = None, change_type: str = None,
                         change_summary: str = None, changed_fields: list = None,
                         trigger: str = None) -> None:
        self.conn.execute(
            """INSERT INTO constitution_changelog
               (constitution_id, version_from, version_to, change_type,
                change_summary, changed_fields, trigger, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (constitution_id, version_from, version_to, change_type,
             change_summary, self._json(changed_fields), trigger, self._now())
        )

    def get_changelog(self, constitution_id: str, limit: int = 50) -> list[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM constitution_changelog WHERE constitution_id = ? ORDER BY created_at DESC LIMIT ?",
            (constitution_id, limit)
        ))
        for row in rows:
            if row.get("changed_fields") and isinstance(row["changed_fields"], str):
                row["changed_fields"] = json.loads(row["changed_fields"])
        return rows

    # --- Judgment Events ---

    def record_judgment_event(self, event_type: str, *, ticker: str = None,
                              constitution_version: int = None, agent: str = None,
                              data: dict = None, rationale: str = None,
                              parent_event_id: int = None) -> int:
        """Record a judgment event and return its ID for chaining."""
        cursor = self.conn.execute(
            """INSERT INTO judgment_events
               (event_type, ticker, constitution_version, agent, data,
                rationale, parent_event_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, ticker, constitution_version, agent,
             self._json(data), rationale, parent_event_id, self._now())
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_event_chain(self, event_id: int) -> list[dict]:
        """Walk the event chain backward from event_id to the root."""
        chain = []
        current_id = event_id
        seen = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM judgment_events WHERE id = ?", (current_id,)
            ))
            if not rows:
                break
            row = rows[0]
            if row.get("data") and isinstance(row["data"], str):
                row["data"] = json.loads(row["data"])
            chain.append(row)
            current_id = row.get("parent_event_id")
        chain.reverse()
        return chain

    def get_events_by_ticker(self, ticker: str, limit: int = 50) -> list[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM judgment_events WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
            (ticker, limit)
        ))
        for row in rows:
            if row.get("data") and isinstance(row["data"], str):
                row["data"] = json.loads(row["data"])
        return rows

    def get_events_by_type(self, event_type: str, limit: int = 50) -> list[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM judgment_events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit)
        ))
        for row in rows:
            if row.get("data") and isinstance(row["data"], str):
                row["data"] = json.loads(row["data"])
        return rows

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM judgment_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ))
        for row in rows:
            if row.get("data") and isinstance(row["data"], str):
                row["data"] = json.loads(row["data"])
        return rows

    # --- Thesis Health Queries ---

    def get_latest_thesis_health(self, ticker: str) -> dict | None:
        """Get most recent thesis health score and checks for a ticker."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM judgment_events WHERE event_type = 'thesis_health_score' "
            "AND ticker = ? ORDER BY created_at DESC LIMIT 1",
            (ticker,)
        ))
        if not rows:
            return None
        row = rows[0]
        if row.get("data") and isinstance(row["data"], str):
            row["data"] = json.loads(row["data"])
        return row

    def get_thesis_health_history(self, ticker: str, limit: int = 10) -> list[dict]:
        """Get thesis health score history for trend display."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT data, created_at FROM judgment_events "
            "WHERE event_type = 'thesis_health_score' AND ticker = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (ticker, limit)
        ))
        result = []
        for row in rows:
            data = row.get("data")
            if isinstance(data, str):
                data = json.loads(data)
            score = data.get("score") if isinstance(data, dict) else None
            result.append({
                "score": score,
                "label": row["created_at"][:10] if row.get("created_at") else "",
            })
        result.reverse()  # Oldest first for trend display
        return result

    def get_web_signal_count(self, ticker: str, assumption: str, days: int = 90) -> int:
        """Count how many times a web search flagged this assumption negatively in the last N days."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        # Use LIKE for assumption matching (substring match)
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM judgment_events "
            "WHERE event_type = 'thesis_web_signal' AND ticker = ? "
            "AND created_at >= ? AND data LIKE ?",
            (ticker, cutoff, f'%{assumption[:60]}%')
        ).fetchone()
        return rows[0] if rows else 0

    def record_web_signal_accuracy(self, ticker: str, assumption: str,
                                    web_predicted: str, sec_confirmed: str) -> int:
        """Record whether a web search signal was validated by subsequent SEC data.

        This feeds the learning loop: after each SEC filing, compare what web
        search predicted vs what SEC confirmed.
        """
        return self.record_judgment_event(
            event_type="web_signal_accuracy",
            ticker=ticker,
            agent="portfolio",
            data={
                "assumption": assumption,
                "web_predicted": web_predicted,
                "sec_confirmed": sec_confirmed,
                "accurate": web_predicted == sec_confirmed,
            },
            rationale=f"Web predicted '{web_predicted}', SEC confirmed '{sec_confirmed}' for '{assumption[:60]}'",
        )

    # --- Conversation History ---

    def save_conversation_message(self, session_id: str, role: str, content: str,
                                   constitution_id: str = None, extracted: dict = None) -> None:
        self.conn.execute(
            """INSERT INTO conversation_history
               (constitution_id, session_id, role, content, extracted, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (constitution_id, session_id, role, content, self._json(extracted), self._now())
        )
        self.conn.commit()

    def get_conversation_history(self, constitution_id: str = None,
                                  session_id: str = None, limit: int = 100) -> list[dict]:
        if session_id:
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM conversation_history WHERE session_id = ? ORDER BY created_at LIMIT ?",
                (session_id, limit)
            ))
        elif constitution_id:
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM conversation_history WHERE constitution_id = ? ORDER BY created_at DESC LIMIT ?",
                (constitution_id, limit)
            ))
            rows.reverse()
        else:
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM conversation_history ORDER BY created_at DESC LIMIT ?", (limit,)
            ))
            rows.reverse()
        for row in rows:
            if row.get("extracted") and isinstance(row["extracted"], str):
                row["extracted"] = json.loads(row["extracted"])
        return rows

    def get_latest_session_id(self, constitution_id: str) -> Optional[str]:
        """Get the most recent conversation session for a constitution."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT session_id FROM conversation_history WHERE constitution_id = ? ORDER BY created_at DESC LIMIT 1",
            (constitution_id,)
        ))
        return rows[0]["session_id"] if rows else None

    # --- Library Entries ---

    def store_library_entry(self, ticker: str, entry_type: str, *,
                            constitution_version: int = None, verdict: str = None,
                            conviction: int = None, expected_return: float = None,
                            discount_pct: float = None, sector: str = None,
                            industry: str = None, gross_margin: float = None,
                            roic: float = None, revenue_growth: float = None,
                            debt_equity: float = None, key_assumptions: list = None,
                            judgment_event_id: int = None, data: dict = None) -> int:
        cursor = self.conn.execute(
            """INSERT INTO library_entries
               (ticker, entry_type, constitution_version, verdict, conviction,
                expected_return, discount_pct, sector, industry, gross_margin,
                roic, revenue_growth, debt_equity, key_assumptions,
                judgment_event_id, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, entry_type, constitution_version, verdict, conviction,
             expected_return, discount_pct, sector, industry, gross_margin,
             roic, revenue_growth, debt_equity, self._json(key_assumptions),
             judgment_event_id, self._json(data), self._now())
        )
        self.conn.commit()
        return cursor.lastrowid

    def find_similar(self, ticker: str, sector: str = None,
                     gross_margin: float = None, roic: float = None,
                     top_k: int = 5) -> list[dict]:
        """Find similar library entries by sector and metric ranges.

        Uses SQL-based similarity (no vector embeddings needed for v1).
        Matches on: same sector, similar GM range (±10pp), similar ROIC range (±5pp).
        """
        conditions = ["ticker != ?"]
        params: list = [ticker]

        if sector:
            conditions.append("sector = ?")
            params.append(sector)

        if gross_margin is not None:
            conditions.append("gross_margin BETWEEN ? AND ?")
            params.extend([gross_margin - 10, gross_margin + 10])

        if roic is not None:
            conditions.append("roic BETWEEN ? AND ?")
            params.extend([roic - 5, roic + 5])

        where = " AND ".join(conditions)
        params.append(top_k)

        rows = self._rows_to_dicts(self.conn.execute(
            f"""SELECT * FROM library_entries
                WHERE {where}
                ORDER BY created_at DESC LIMIT ?""",
            params
        ))
        for row in rows:
            for key in ("key_assumptions", "data"):
                if row.get(key) and isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        return rows

    def get_library_by_ticker(self, ticker: str, limit: int = 20) -> list[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM library_entries WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
            (ticker, limit)
        ))
        for row in rows:
            for key in ("key_assumptions", "data"):
                if row.get(key) and isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        return rows

    def get_library_stats(self) -> dict:
        """Summary stats for the library."""
        total = self.conn.execute("SELECT COUNT(*) FROM library_entries").fetchone()[0]
        by_type = {}
        for row in self.conn.execute("SELECT entry_type, COUNT(*) FROM library_entries GROUP BY entry_type").fetchall():
            by_type[row[0]] = row[1]
        by_verdict = {}
        for row in self.conn.execute("SELECT verdict, COUNT(*) FROM library_entries WHERE verdict IS NOT NULL GROUP BY verdict").fetchall():
            by_verdict[row[0]] = row[1]
        return {"total": total, "by_type": by_type, "by_verdict": by_verdict}

    def get_library_by_sector(self, sector: str, verdict: str = None,
                              limit: int = 20) -> list[dict]:
        """Get library entries filtered by sector and optionally by verdict."""
        query = "SELECT * FROM library_entries WHERE sector = ?"
        params: list = [sector]
        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._rows_to_dicts(self.conn.execute(query, params))
        for row in rows:
            for key in ("key_assumptions", "data"):
                if row.get(key) and isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        return rows

    # --- Refinement Proposals ---

    def store_proposal(self, proposal_id: str, constitution_id: str = None,
                       pattern_type: str = "", pattern_tag: str = "",
                       pattern_count: int = 0, pattern_tickers: list = None,
                       proposal: str = "", analysis: str = "",
                       code_change: str = "", confidence: float = 0,
                       risk: str = "", evidence_summary: str = "") -> dict:
        self.conn.execute(
            """INSERT INTO refinement_proposals
               (id, constitution_id, pattern_type, pattern_tag, pattern_count,
                pattern_tickers, proposal, analysis, code_change, confidence,
                risk, evidence_summary, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (proposal_id, constitution_id, pattern_type, pattern_tag,
             pattern_count, self._json(pattern_tickers), proposal, analysis,
             code_change, confidence, risk, evidence_summary, self._now())
        )
        self.conn.commit()
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM refinement_proposals WHERE id = ?", (proposal_id,)
        ))
        if not rows:
            return None
        row = rows[0]
        if row.get("pattern_tickers") and isinstance(row["pattern_tickers"], str):
            row["pattern_tickers"] = json.loads(row["pattern_tickers"])
        return row

    def get_pending_proposals(self, constitution_id: str = None) -> list[dict]:
        if constitution_id:
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM refinement_proposals WHERE status = 'pending' AND constitution_id = ? ORDER BY created_at DESC",
                (constitution_id,)
            ))
        else:
            rows = self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM refinement_proposals WHERE status = 'pending' ORDER BY created_at DESC"
            ))
        for row in rows:
            if row.get("pattern_tickers") and isinstance(row["pattern_tickers"], str):
                row["pattern_tickers"] = json.loads(row["pattern_tickers"])
        return rows

    def resolve_proposal(self, proposal_id: str, user_response: str,
                          applied_version_id: str = None) -> dict:
        self.conn.execute(
            """UPDATE refinement_proposals
               SET status = ?, user_response = ?, applied_version_id = ?, resolved_at = ?
               WHERE id = ?""",
            (user_response, user_response, applied_version_id, self._now(), proposal_id)
        )
        self.conn.commit()
        return self.get_proposal(proposal_id)

    def get_proposal_stats(self) -> dict:
        """Stats on proposal acceptance rate (for autonomy graduation)."""
        total = self.conn.execute("SELECT COUNT(*) FROM refinement_proposals WHERE status != 'pending'").fetchone()[0]
        accepted = self.conn.execute("SELECT COUNT(*) FROM refinement_proposals WHERE user_response = 'accepted'").fetchone()[0]
        rejected = self.conn.execute("SELECT COUNT(*) FROM refinement_proposals WHERE user_response = 'rejected'").fetchone()[0]
        return {
            "total_resolved": total,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": round(accepted / total, 2) if total > 0 else None,
        }

    # --- Strategy Profiles (legacy, kept for backward compat) ---

    def create_strategy(self, strategy_id: str, name: str, north_star: str = None,
                        dimensions: dict = None, sector_routing: dict = None,
                        universe_type: str = "preset", universe_name: str = "us_largecap_200",
                        autonomy_mode: str = "copilot") -> dict:
        now = self._now()
        self.conn.execute(
            """INSERT INTO strategy_profiles
               (id, name, autonomy_mode, north_star, dimensions, sector_routing,
                universe_type, universe_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (strategy_id, name, autonomy_mode, north_star,
             self._json(dimensions), self._json(sector_routing),
             universe_type, universe_name, now, now)
        )
        self.conn.commit()
        return self.get_strategy(strategy_id)

    def get_strategy(self, strategy_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM strategy_profiles WHERE id = ?", (strategy_id,)
        ))
        if not rows:
            return None
        row = rows[0]
        for key in ("dimensions", "sector_routing", "universe_custom"):
            if row.get(key) and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    def get_active_strategy(self) -> Optional[dict]:
        """Get the most recently updated non-archived strategy."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM strategy_profiles WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 1"
        ))
        if not rows:
            return None
        row = rows[0]
        for key in ("dimensions", "sector_routing", "universe_custom"):
            if row.get(key) and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    def update_strategy(self, strategy_id: str, **kwargs) -> dict:
        allowed = {"name", "north_star", "dimensions", "sector_routing",
                    "universe_type", "universe_name", "universe_custom",
                    "autonomy_mode", "active_version_id"}
        updates = {}
        for k, v in kwargs.items():
            if k in allowed:
                if k in ("dimensions", "sector_routing", "universe_custom") and isinstance(v, (dict, list)):
                    updates[k] = self._json(v)
                else:
                    updates[k] = v
        if not updates:
            return self.get_strategy(strategy_id)
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        params = list(updates.values()) + [strategy_id]
        self.conn.execute(f"UPDATE strategy_profiles SET {set_clause} WHERE id = ?", params)
        self.conn.commit()
        return self.get_strategy(strategy_id)

    def list_strategies(self) -> list[dict]:
        return self._rows_to_dicts(self.conn.execute(
            "SELECT id, name, autonomy_mode, north_star, active_version_id, created_at, updated_at "
            "FROM strategy_profiles ORDER BY updated_at DESC"
        ))

    # --- Strategy Versions ---

    def create_version(self, version_id: str, strategy_id: str, version_number: int,
                       scoring_code: str, label_map: dict = None, explanation: str = None,
                       change_reason: str = None) -> dict:
        # Let SQLite auto-generate the integer id (AUTOINCREMENT column).
        # version_id is a codegen label (e.g. "v-437fb468"), not the row PK.
        cursor = self.conn.execute(
            """INSERT INTO strategy_versions
               (strategy_id, version_number, scoring_code, label_map, explanation,
                change_reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (strategy_id, version_number, scoring_code,
             self._json(label_map), explanation, change_reason, self._now())
        )
        row_id = cursor.lastrowid
        # Update the active version on the strategy (use integer row id)
        self.conn.execute(
            "UPDATE strategy_profiles SET active_version_id = ?, updated_at = ? WHERE id = ?",
            (row_id, self._now(), strategy_id)
        )
        self.conn.commit()
        return self.get_version(row_id)

    def get_version(self, version_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM strategy_versions WHERE id = ?", (version_id,)
        ))
        if not rows:
            return None
        row = rows[0]
        if row.get("label_map") and isinstance(row["label_map"], str):
            row["label_map"] = json.loads(row["label_map"])
        return row

    def get_version_history(self, strategy_id: str) -> list[dict]:
        return self._rows_to_dicts(self.conn.execute(
            "SELECT id, strategy_id, version_number, change_reason, created_at "
            "FROM strategy_versions WHERE strategy_id = ? ORDER BY version_number DESC",
            (strategy_id,)
        ))

    def get_latest_version(self, strategy_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM strategy_versions WHERE strategy_id = ? ORDER BY version_number DESC LIMIT 1",
            (strategy_id,)
        ))
        if not rows:
            return None
        row = rows[0]
        if row.get("label_map") and isinstance(row["label_map"], str):
            row["label_map"] = json.loads(row["label_map"])
        return row

    # --- Screener Runs ---

    def record_screener_run(self, run_id: str = None, strategy_version_id=None,
                            universe_size: int = 0, scored_count: int = 0,
                            failed_count: int = 0, top_results: list = None,
                            all_results: list = None, duration_s: float = 0,
                            status: str = "complete", error_message: str = None) -> int:
        """Save screener run results. Returns the run ID (lastrowid for auto-generated)."""
        if run_id:
            cursor = self.conn.execute(
                """INSERT INTO screener_runs
                   (id, strategy_version_id, run_at, universe_size, scored_count,
                    failed_count, top_results, all_results, duration_s, status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, strategy_version_id, self._now(), universe_size, scored_count,
                 failed_count, self._json(top_results), self._json(all_results),
                 duration_s, status, error_message)
            )
        else:
            cursor = self.conn.execute(
                """INSERT INTO screener_runs
                   (strategy_version_id, run_at, universe_size, scored_count,
                    failed_count, top_results, all_results, duration_s, status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (strategy_version_id, self._now(), universe_size, scored_count,
                 failed_count, self._json(top_results), self._json(all_results),
                 duration_s, status, error_message)
            )
        self.conn.commit()
        return cursor.lastrowid

    def get_screener_run(self, run_id: str) -> Optional[dict]:
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM screener_runs WHERE id = ?", (run_id,)
        ))
        if not rows:
            return None
        row = rows[0]
        for key in ("top_results", "all_results"):
            if row.get(key) and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    def get_runs_by_strategy(self, strategy_version_id: str = None, limit: int = 20) -> list[dict]:
        if strategy_version_id:
            return self._rows_to_dicts(self.conn.execute(
                "SELECT id, strategy_version_id, run_at, universe_size, scored_count, "
                "failed_count, duration_s, status FROM screener_runs "
                "WHERE strategy_version_id = ? ORDER BY run_at DESC LIMIT ?",
                (strategy_version_id, limit)
            ))
        return self._rows_to_dicts(self.conn.execute(
            "SELECT id, strategy_version_id, run_at, universe_size, scored_count, "
            "failed_count, duration_s, status FROM screener_runs ORDER BY run_at DESC LIMIT ?",
            (limit,)
        ))

    def get_latest_screener_results(self) -> Optional[dict]:
        """Get the latest screener run with all results (including all_results JSON)."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM screener_runs ORDER BY run_at DESC LIMIT 1"
        ))
        if not rows:
            return None
        row = rows[0]
        for field in ("all_results", "top_results"):
            if row.get(field) and isinstance(row[field], str):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    pass
        return row

    # --- Feedback Records ---

    def record_feedback(self, screener_run_id: str, ticker: str, feedback: str,
                        dismiss_reason: str = None, note: str = None,
                        score_at_feedback: float = None, rank_at_feedback: int = None) -> None:
        # Temporarily disable FK enforcement so feedback can reference any run/ticker
        self.conn.execute("PRAGMA foreign_keys=OFF")
        try:
            self.conn.execute(
                """INSERT INTO feedback_records
                   (screener_run_id, ticker, feedback, dismiss_reason, note,
                    score_at_feedback, rank_at_feedback, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (screener_run_id, ticker, feedback, dismiss_reason, note,
                 score_at_feedback, rank_at_feedback, self._now())
            )
            self.conn.commit()
        finally:
            self.conn.execute("PRAGMA foreign_keys=ON")

    def get_feedback_for_run(self, screener_run_id: str) -> list[dict]:
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM feedback_records WHERE screener_run_id = ? ORDER BY created_at",
            (screener_run_id,)
        ))

    def get_feedback_by_ticker(self, ticker: str, limit: int = 20) -> list[dict]:
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM feedback_records WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
            (ticker, limit)
        ))

    # --- Outcome Snapshots ---

    def record_outcome_snapshot(self, screener_run_id: str, ticker: str,
                                screened_at: str, check_at: str, days_elapsed: int,
                                price_at_screen: float = None, price_at_check: float = None,
                                return_pct: float = None, benchmark_return_pct: float = None,
                                alpha_pct: float = None, thesis_integrity: dict = None,
                                goal_alignment: dict = None, status: str = "complete",
                                error_message: str = None) -> None:
        self.conn.execute(
            """INSERT INTO outcome_snapshots
               (screener_run_id, ticker, screened_at, check_at, days_elapsed,
                price_at_screen, price_at_check, return_pct, benchmark_return_pct,
                alpha_pct, thesis_integrity, goal_alignment, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (screener_run_id, ticker, screened_at, check_at, days_elapsed,
             price_at_screen, price_at_check, return_pct, benchmark_return_pct,
             alpha_pct, self._json(thesis_integrity), self._json(goal_alignment),
             status, error_message)
        )
        self.conn.commit()

    def get_outcomes_for_run(self, run_id: str) -> list[dict]:
        """Get all outcome snapshots linked to a screener run."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM outcome_snapshots WHERE screener_run_id = ? ORDER BY days_elapsed",
            (run_id,)
        ))
        for row in rows:
            for key in ("thesis_integrity", "goal_alignment"):
                if row.get(key) and isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        return rows

    def get_due_checks(self, check_intervals: list[int] = None) -> list[dict]:
        """Find screener runs that need outcome checks at specified day intervals."""
        if check_intervals is None:
            check_intervals = [90, 180, 365, 730, 1095]

        due = []
        for days in check_intervals:
            rows = self._rows_to_dicts(self.conn.execute(
                """SELECT sr.id as run_id, sr.run_at, sr.top_results, sr.strategy_version_id
                   FROM screener_runs sr
                   WHERE sr.status = 'complete'
                   AND julianday('now') - julianday(sr.run_at) >= ?
                   AND julianday('now') - julianday(sr.run_at) < ? + 7
                   AND NOT EXISTS (
                       SELECT 1 FROM outcome_snapshots os
                       WHERE os.screener_run_id = sr.id AND os.days_elapsed = ?
                   )
                   ORDER BY sr.run_at""",
                (days, days, days)
            ))
            for row in rows:
                row["check_days"] = days
                if row.get("top_results") and isinstance(row["top_results"], str):
                    row["top_results"] = json.loads(row["top_results"])
                due.append(row)
        return due

    def reset_constitution(self) -> dict:
        """Archive the current constitution and start fresh.

        Instead of deleting, marks existing constitution as archived.
        Clears conversation history and feedback so the new experience is clean.
        Preserves: judgment events, library entries, agent runs, portfolio.
        """
        import datetime
        now = datetime.datetime.utcnow().isoformat()
        archived = {}

        # Archive constitution — add archived_at column if missing, then mark
        try:
            self.conn.execute("ALTER TABLE constitution ADD COLUMN archived_at TEXT")
        except Exception:
            pass  # Column already exists
        try:
            cur = self.conn.execute(
                "UPDATE constitution SET archived_at = ? WHERE archived_at IS NULL", (now,)
            )
            archived["constitution"] = cur.rowcount
        except Exception as e:
            import logging
            logging.getLogger("fundops.db").warning(f"reset: archive constitution failed: {e}")
            archived["constitution"] = 0

        # Archive strategy_profiles
        try:
            self.conn.execute("ALTER TABLE strategy_profiles ADD COLUMN archived_at TEXT")
        except Exception:
            pass
        try:
            cur = self.conn.execute(
                "UPDATE strategy_profiles SET archived_at = ? WHERE archived_at IS NULL", (now,)
            )
            archived["strategy_profiles"] = cur.rowcount
        except Exception:
            archived["strategy_profiles"] = 0

        # Clear conversation history (not worth archiving — it's ephemeral chat)
        try:
            cur = self.conn.execute("DELETE FROM conversation_history")
            archived["conversation_history_cleared"] = cur.rowcount
        except Exception:
            archived["conversation_history_cleared"] = 0

        # Clear feedback records for fresh start
        try:
            cur = self.conn.execute("DELETE FROM feedback_records")
            archived["feedback_records_cleared"] = cur.rowcount
        except Exception:
            archived["feedback_records_cleared"] = 0

        self.conn.commit()
        return archived

    def get_outcomes_for_strategy(self, strategy_version_id: str = None,
                                   ticker: str = None, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM outcome_snapshots WHERE 1=1"
        params = []
        if strategy_version_id:
            query += " AND screener_run_id IN (SELECT id FROM screener_runs WHERE strategy_version_id = ?)"
            params.append(strategy_version_id)
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        query += " ORDER BY check_at DESC LIMIT ?"
        params.append(limit)

        rows = self._rows_to_dicts(self.conn.execute(query, params))
        for row in rows:
            for key in ("thesis_integrity", "goal_alignment"):
                if row.get(key) and isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        return rows

    # --- Ticker Financials ---

    def upsert_ticker_financials(self, ticker: str, financial_data: dict,
                                  source: str = "sec+yfinance",
                                  screener_run_id: str = None) -> None:
        """Persist a financial snapshot for a ticker.

        Archives any existing latest snapshot (is_latest=0) and inserts
        the new one as current (is_latest=1).
        """
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(financial_data, default=str)
        # Archive previous latest
        self.conn.execute(
            "UPDATE ticker_financials SET is_latest = 0 WHERE ticker = ? AND is_latest = 1",
            (ticker,)
        )
        self.conn.execute(
            """INSERT INTO ticker_financials
               (ticker, financial_data, source, screener_run_id, fetched_at, is_latest)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (ticker, data_json, source, screener_run_id, now)
        )
        self.conn.commit()

    def upsert_ticker_financials_batch(self, items: list[dict],
                                        screener_run_id: str = None) -> int:
        """Batch persist financial snapshots. Each item has 'ticker' and 'financial_data'.

        Returns count of inserted rows.
        """
        now = datetime.now(timezone.utc).isoformat()
        tickers = [item["ticker"] for item in items]
        # Archive all previous latest in one statement per ticker
        placeholders = ",".join("?" for _ in tickers)
        self.conn.execute(
            f"UPDATE ticker_financials SET is_latest = 0 WHERE ticker IN ({placeholders}) AND is_latest = 1",
            tickers
        )
        for item in items:
            data_json = json.dumps(item["financial_data"], default=str)
            self.conn.execute(
                """INSERT INTO ticker_financials
                   (ticker, financial_data, source, screener_run_id, fetched_at, is_latest)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (item["ticker"], data_json, item.get("source", "sec+yfinance"),
                 screener_run_id, now)
            )
        self.conn.commit()
        return len(items)

    def get_ticker_financials(self, ticker: str) -> dict | None:
        """Get the latest financial snapshot for a ticker."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM ticker_financials WHERE ticker = ? AND is_latest = 1 LIMIT 1",
            (ticker,)
        ))
        if not rows:
            return None
        row = rows[0]
        if isinstance(row.get("financial_data"), str):
            row["financial_data"] = json.loads(row["financial_data"])
        return row

    def get_ticker_financials_batch(self, tickers: list[str]) -> dict[str, dict]:
        """Get latest financial snapshots for multiple tickers. Returns {ticker: row}."""
        if not tickers:
            return {}
        placeholders = ",".join("?" for _ in tickers)
        rows = self._rows_to_dicts(self.conn.execute(
            f"SELECT * FROM ticker_financials WHERE ticker IN ({placeholders}) AND is_latest = 1",
            tickers
        ))
        result = {}
        for row in rows:
            if isinstance(row.get("financial_data"), str):
                row["financial_data"] = json.loads(row["financial_data"])
            result[row["ticker"]] = row
        return result

    def get_ticker_financial_history(self, ticker: str, limit: int = 10) -> list[dict]:
        """Get historical financial snapshots for a ticker (all versions)."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM ticker_financials WHERE ticker = ? ORDER BY fetched_at DESC LIMIT ?",
            (ticker, limit)
        ))
        for row in rows:
            if isinstance(row.get("financial_data"), str):
                row["financial_data"] = json.loads(row["financial_data"])
        return rows
