"""FundOps Database — SQLite storage with async support.

All writes are additive.
Agents still produce JSON files as primary output; DB is the audit trail and
query layer for the dashboard.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = Path.home() / ".fundops" / "fundops.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickers (
    ticker TEXT PRIMARY KEY,
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    first_seen_at TEXT,
    current_lifecycle TEXT,
    is_owned INTEGER DEFAULT 0,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    agent TEXT NOT NULL,
    run_at TEXT NOT NULL,
    run_type TEXT,
    scores JSON,
    fair_value REAL,
    price_at_run REAL,
    verdict TEXT,
    summary TEXT,
    full_output JSON,
    output_path TEXT,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    total_value REAL,
    cash REAL,
    holdings JSON,
    alerts JSON,
    daily_pnl REAL,
    UNIQUE(snapshot_date)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,
    added_reason TEXT,
    entry_price REAL,
    target_price REAL,
    status TEXT DEFAULT 'active',
    removed_at TEXT,
    notes TEXT,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    action TEXT NOT NULL,
    acted_at TEXT NOT NULL,
    reason TEXT,
    context JSON,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    title TEXT,
    content TEXT,
    metadata JSON,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    shares REAL,
    price REAL,
    date TEXT NOT NULL,
    source_agent TEXT,
    scout_lens TEXT,
    val_expected_return REAL,
    judge_verdict TEXT,
    notes TEXT,
    FOREIGN KEY (ticker) REFERENCES tickers(ticker)
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_ticker ON agent_runs(ticker, agent, run_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent, run_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_date ON portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status, ticker);
CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker, doc_type);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON outcomes(ticker, date);
"""


class FundOpsDB:
    """SQLite database for FundOps.

    Thread-safe for single-writer usage. Use one instance per process.
    """

    def __init__(self, db_path: Path | str = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

        # Apply any pending schema migrations
        from backend.core.migrations import run_migrations
        try:
            run_migrations(self.conn)
        except Exception as e:
            import logging
            logging.getLogger("fundops.db").warning(f"Migration runner failed: {e}")

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json(self, obj: Any) -> Optional[str]:
        return json.dumps(obj, default=str) if obj is not None else None

    # --- Ticker management ---

    # Safe column whitelist for upsert — prevents SQL injection via column names
    _TICKER_COLUMNS = frozenset({
        "company_name", "sector", "industry", "current_lifecycle", "is_owned", "metadata"
    })

    def upsert_ticker(self, ticker: str, company_name: str = None, sector: str = None,
                      industry: str = None, lifecycle: str = None, is_owned: bool = None,
                      metadata: dict = None) -> None:
        # Map kwargs to safe column names
        field_map = {
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "current_lifecycle": lifecycle,
            "is_owned": int(is_owned) if is_owned is not None else None,
            "metadata": self._json(metadata) if metadata is not None else None,
        }
        # Filter to non-None values with whitelisted columns only
        changes = {
            col: val for col, val in field_map.items()
            if val is not None and col in self._TICKER_COLUMNS
        }

        existing = self.conn.execute(
            "SELECT ticker FROM tickers WHERE ticker = ?", (ticker,)
        ).fetchone()

        if existing:
            if changes:
                set_clause = ", ".join(f"{col} = ?" for col in changes)
                params = list(changes.values()) + [ticker]
                self.conn.execute(f"UPDATE tickers SET {set_clause} WHERE ticker = ?", params)
        else:
            cols = ["ticker", "first_seen_at"] + list(changes.keys())
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            vals = [ticker, self._now()] + list(changes.values())
            self.conn.execute(f"INSERT INTO tickers ({col_names}) VALUES ({placeholders})", vals)
        self.conn.commit()

    # --- Agent runs ---

    def record_run(self, agent: str, ticker: str, run_type: str = None, scores: dict = None,
                   fair_value: float = None, price_at_run: float = None, verdict: str = None,
                   summary: str = None, full_output: dict = None, output_path: str = None,
                   run_at: str = None) -> None:
        self.conn.execute(
            """INSERT INTO agent_runs
               (ticker, agent, run_at, run_type, scores, fair_value,
                price_at_run, verdict, summary, full_output, output_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, agent, run_at or self._now(), run_type,
             self._json(scores), fair_value, price_at_run, verdict,
             summary, self._json(full_output), output_path)
        )
        self.conn.commit()

    # --- Portfolio snapshots ---

    def record_portfolio_snapshot(self, snapshot_date: str, total_value: float = None,
                                  cash: float = None, holdings: list | dict | None = None,
                                  alerts: list = None, daily_pnl: float = None) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO portfolio_snapshots
               (snapshot_date, total_value, cash, holdings, alerts, daily_pnl)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot_date, total_value, cash, self._json(holdings), self._json(alerts), daily_pnl)
        )
        self.conn.commit()

    # --- Outcomes (feedback loop) ---

    def record_outcome(self, ticker: str, action: str, shares: float, price: float,
                       date: str, source_agent: str = None, scout_lens: str = None,
                       val_expected_return: float = None, judge_verdict: str = None,
                       notes: str = None) -> None:
        self.conn.execute(
            """INSERT INTO outcomes
               (ticker, action, shares, price, date, source_agent,
                scout_lens, val_expected_return, judge_verdict, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, action, shares, price, date, source_agent,
             scout_lens, val_expected_return, judge_verdict, notes)
        )
        self.conn.commit()

    # --- Actions ---

    def record_action(self, action: str, ticker: str = None, reason: str = None,
                      context: dict = None) -> None:
        self.conn.execute(
            """INSERT INTO actions (ticker, action, acted_at, reason, context)
               VALUES (?, ?, ?, ?, ?)""",
            (ticker, action, self._now(), reason, self._json(context))
        )
        self.conn.commit()

    # --- Documents ---

    def store_document(self, ticker: str, doc_type: str, content: str,
                       title: str = None, metadata: dict = None) -> None:
        self.conn.execute(
            """INSERT INTO documents (ticker, doc_type, created_at, title, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticker, doc_type, self._now(), title, content, self._json(metadata))
        )
        self.conn.commit()

    # --- Queries ---

    def _rows_to_dicts(self, cursor) -> list[dict]:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_ticker_history(self, ticker: str, agent: str = None, limit: int = 20) -> list[dict]:
        query = "SELECT * FROM agent_runs WHERE ticker = ?"
        params: list = [ticker]
        if agent:
            query += " AND agent = ?"
            params.append(agent)
        query += " ORDER BY run_at DESC LIMIT ?"
        params.append(limit)
        return self._rows_to_dicts(self.conn.execute(query, params))

    def get_latest_run(self, ticker: str, agent: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM agent_runs WHERE ticker = ? AND agent = ? ORDER BY run_at DESC LIMIT 1",
            (ticker, agent)
        )
        rows = self._rows_to_dicts(cur)
        return rows[0] if rows else None

    def get_pipeline_status(self, ticker: str) -> dict:
        """Get the latest run from each agent for a ticker — full pipeline view."""
        agents = ["screener", "thesis", "ic_review", "memo", "library", "portfolio", "allocator"]
        status = {}
        for agent in agents:
            run = self.get_latest_run(ticker, agent)
            if run:
                status[agent] = {
                    "run_at": run["run_at"],
                    "verdict": run.get("verdict"),
                    "fair_value": run.get("fair_value"),
                    "price_at_run": run.get("price_at_run"),
                    "summary": run.get("summary"),
                }
        return status

    def get_dashboard_data(self) -> dict:
        """Aggregate data for the main dashboard."""
        # Recent runs across all agents
        recent = self._rows_to_dicts(self.conn.execute(
            "SELECT ticker, agent, run_at, verdict, fair_value, price_at_run FROM agent_runs ORDER BY run_at DESC LIMIT 50"
        ))

        # Agent run counts
        counts = {}
        for row in self.conn.execute("SELECT agent, COUNT(*) FROM agent_runs GROUP BY agent").fetchall():
            counts[row[0]] = row[1]

        # Latest portfolio snapshot
        portfolio = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        ))

        return {
            "recent_runs": recent,
            "agent_run_counts": counts,
            "latest_portfolio": portfolio[0] if portfolio else None,
        }

    def get_portfolio_history(self, days: int = 30) -> list[dict]:
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT ?", (days,)
        ))

    def get_outcomes(self, ticker: str = None, limit: int = 50) -> list[dict]:
        if ticker:
            return self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM outcomes WHERE ticker = ? ORDER BY date DESC LIMIT ?", (ticker, limit)
            ))
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM outcomes ORDER BY date DESC LIMIT ?", (limit,)
        ))

    def get_latest_runs(self, agent: str, ticker: str = None, limit: int = 10) -> list[dict]:
        """Get latest runs for an agent, optionally filtered by ticker."""
        if ticker:
            return self._rows_to_dicts(self.conn.execute(
                "SELECT * FROM agent_runs WHERE agent = ? AND ticker = ? ORDER BY run_at DESC LIMIT ?",
                (agent, ticker, limit)
            ))
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM agent_runs WHERE agent = ? ORDER BY run_at DESC LIMIT ?",
            (agent, limit)
        ))

    def get_runs_for_ticker(self, ticker: str, limit: int = 50) -> list[dict]:
        """Get all agent runs for a ticker (timeline view)."""
        return self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM agent_runs WHERE ticker = ? ORDER BY run_at DESC LIMIT ?",
            (ticker, limit)
        ))

    def get_latest_portfolio_snapshot(self) -> Optional[dict]:
        """Get the most recent portfolio snapshot."""
        rows = self._rows_to_dicts(self.conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        ))
        return rows[0] if rows else None

    def clear_pipeline_data(self) -> dict:
        """Clear all agent run data while preserving portfolio positions and strategy.

        Deletes: agent_runs, watchlist, actions, documents, outcomes.
        Preserves: tickers, portfolio_snapshots (positions you entered).
        Returns counts of deleted rows per table.
        """
        deleted = {}
        tables = ["agent_runs", "watchlist", "actions", "documents", "outcomes"]
        for tbl in tables:
            try:
                cur = self.conn.execute(f"DELETE FROM {tbl}")
                deleted[tbl] = cur.rowcount
            except Exception:
                deleted[tbl] = 0
        self.conn.commit()
        return deleted
