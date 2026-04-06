"""Test that both v1 and v2 database schemas create correctly and coexist."""

import sqlite3
import pytest


class TestV1Schema:
    """v1 schema (db.py) creates all expected tables and indexes."""

    def test_core_tables_exist(self, db):
        tables = {r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for t in ["tickers", "agent_runs", "portfolio_snapshots", "watchlist",
                   "actions", "documents", "outcomes"]:
            assert t in tables, f"Missing v1 table: {t}"

    def test_tickers_columns(self, db):
        info = db.conn.execute("PRAGMA table_info(tickers)").fetchall()
        cols = {row[1] for row in info}
        assert cols >= {"ticker", "company_name", "sector", "industry",
                        "first_seen_at", "current_lifecycle", "is_owned", "metadata"}

    def test_agent_runs_columns(self, db):
        info = db.conn.execute("PRAGMA table_info(agent_runs)").fetchall()
        cols = {row[1] for row in info}
        assert cols >= {"id", "ticker", "agent", "run_at", "run_type", "scores",
                        "fair_value", "price_at_run", "verdict", "summary", "full_output"}

    def test_portfolio_snapshots_columns(self, db):
        info = db.conn.execute("PRAGMA table_info(portfolio_snapshots)").fetchall()
        cols = {row[1] for row in info}
        assert cols >= {"id", "snapshot_date", "total_value", "cash", "holdings",
                        "alerts", "daily_pnl"}

    def test_indexes_exist(self, db):
        indexes = {r[1] for r in db.conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}
        for idx in ["idx_agent_runs_ticker", "idx_agent_runs_agent",
                     "idx_portfolio_date", "idx_watchlist_status"]:
            assert idx in indexes, f"Missing v1 index: {idx}"


class TestV2Schema:
    """v2 schema (db_v2.py) creates all expected tables and indexes."""

    def test_v2_tables_exist(self, v2db):
        tables = {r[0] for r in v2db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for t in ["constitution", "constitution_changelog", "judgment_events",
                   "conversation_history", "library_entries", "refinement_proposals",
                   "strategy_profiles", "strategy_versions", "screener_runs",
                   "feedback_records", "outcome_snapshots", "ticker_financials"]:
            assert t in tables, f"Missing v2 table: {t}"

    def test_constitution_columns(self, v2db):
        info = v2db.conn.execute("PRAGMA table_info(constitution)").fetchall()
        cols = {row[1] for row in info}
        assert cols >= {"id", "name", "version", "north_star", "must_have_signals",
                        "anti_signals", "ic_hurdles", "dimensions", "autonomy_mode",
                        "active_version_id", "created_at", "updated_at"}

    def test_judgment_events_columns(self, v2db):
        info = v2db.conn.execute("PRAGMA table_info(judgment_events)").fetchall()
        cols = {row[1] for row in info}
        assert cols >= {"id", "event_type", "ticker", "constitution_version",
                        "agent", "data", "rationale", "parent_event_id", "created_at"}

    def test_v2_indexes_exist(self, v2db):
        indexes = {r[1] for r in v2db.conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}
        for idx in ["idx_je_ticker", "idx_je_type", "idx_je_chain",
                     "idx_lib_ticker", "idx_lib_sector", "idx_rp_status"]:
            assert idx in indexes, f"Missing v2 index: {idx}"

    def test_v1_and_v2_coexist(self, db, v2db):
        """Both schemas share one connection and don't conflict."""
        tables = {r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        # v1 tables
        assert "agent_runs" in tables
        assert "portfolio_snapshots" in tables
        # v2 tables
        assert "constitution" in tables
        assert "judgment_events" in tables
        assert "library_entries" in tables
