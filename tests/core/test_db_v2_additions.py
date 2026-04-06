"""Tests for db_v2 helper methods added in A3.

Tests the two new query methods:
- get_outcomes_for_run
- get_library_by_sector

Also tests that existing methods (get_feedback_for_run, get_runs_by_strategy,
get_library_stats, get_library_by_ticker, get_recent_events) still work correctly.
"""

import sqlite3
import pytest
import sys
from pathlib import Path

# Allow imports from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from core.db_v2 import ScreenerV2DB


@pytest.fixture
def db():
    """Create an in-memory ScreenerV2DB with test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    sdb = ScreenerV2DB(conn=conn)

    # --- Seed test data ---

    # Tickers (required for FK constraints)
    for ticker in ("AAPL", "GOOG", "MSFT", "JPM", "BAC"):
        conn.execute("INSERT INTO tickers (ticker, added_at) VALUES (?, ?)",
                     (ticker, sdb._now()))
    conn.commit()

    # Strategy + version
    sdb.create_strategy("strat-1", "Test Strategy", north_star="Value investing")
    sdb.create_version("ver-1", "strat-1", 1, "def score(data): return 50", label_map={"A": "Top"})

    # Screener runs
    sdb.record_screener_run("run-1", "ver-1", universe_size=200, scored_count=180,
                            top_results=[{"ticker": "AAPL", "score": 85}], duration_s=12.5)
    sdb.record_screener_run("run-2", "ver-1", universe_size=200, scored_count=190,
                            top_results=[{"ticker": "MSFT", "score": 90}], duration_s=10.0)

    # Feedback records
    sdb.record_feedback("run-1", "AAPL", "interesting", note="looks cheap")
    sdb.record_feedback("run-1", "GOOG", "dismiss", dismiss_reason="value_trap")
    sdb.record_feedback("run-2", "MSFT", "interesting")

    # Outcome snapshots
    sdb.record_outcome_snapshot("run-1", "AAPL", "2025-01-01", "2025-04-01", 90,
                                price_at_screen=150.0, price_at_check=165.0,
                                return_pct=10.0, benchmark_return_pct=5.0, alpha_pct=5.0,
                                thesis_integrity={"score": 80})
    sdb.record_outcome_snapshot("run-1", "GOOG", "2025-01-01", "2025-04-01", 90,
                                price_at_screen=100.0, price_at_check=95.0,
                                return_pct=-5.0, benchmark_return_pct=5.0, alpha_pct=-10.0)

    # Library entries
    sdb.store_library_entry("AAPL", "ic_review", verdict="pass", conviction=8,
                            expected_return=25.0, sector="Technology", industry="Consumer Electronics",
                            gross_margin=45.0, roic=30.0, key_assumptions=["iPhone growth"],
                            data={"thesis": "test"})
    sdb.store_library_entry("MSFT", "ic_review", verdict="pass", conviction=9,
                            expected_return=22.0, sector="Technology", industry="Software",
                            gross_margin=70.0, roic=35.0)
    sdb.store_library_entry("JPM", "ic_review", verdict="no_pass", conviction=4,
                            expected_return=12.0, sector="Financials", industry="Banking",
                            gross_margin=None, roic=15.0)
    sdb.store_library_entry("BAC", "thesis", verdict=None, conviction=5,
                            expected_return=18.0, sector="Financials", industry="Banking")

    # Judgment events
    sdb.record_judgment_event("screener_complete", ticker="AAPL", agent="screener",
                              data={"score": 85})
    sdb.record_judgment_event("ic_decision", ticker="AAPL", agent="ic_review",
                              data={"verdict": "pass"}, rationale="Strong moat")

    yield sdb
    sdb.close()


# --- get_outcomes_for_run ---

class TestGetOutcomesForRun:
    def test_returns_outcomes_for_existing_run(self, db):
        results = db.get_outcomes_for_run("run-1")
        assert len(results) == 2
        tickers = {r["ticker"] for r in results}
        assert tickers == {"AAPL", "GOOG"}

    def test_parses_json_fields(self, db):
        results = db.get_outcomes_for_run("run-1")
        aapl = next(r for r in results if r["ticker"] == "AAPL")
        assert isinstance(aapl["thesis_integrity"], dict)
        assert aapl["thesis_integrity"]["score"] == 80

    def test_returns_empty_for_nonexistent_run(self, db):
        results = db.get_outcomes_for_run("run-nonexistent")
        assert results == []

    def test_returns_empty_for_run_without_outcomes(self, db):
        results = db.get_outcomes_for_run("run-2")
        assert results == []

    def test_ordered_by_days_elapsed(self, db):
        # Add a 180-day outcome for run-1
        db.record_outcome_snapshot("run-1", "AAPL", "2025-01-01", "2025-07-01", 180,
                                    return_pct=20.0)
        results = db.get_outcomes_for_run("run-1")
        days = [r["days_elapsed"] for r in results]
        assert days == sorted(days)


# --- get_library_by_sector ---

class TestGetLibraryBySector:
    def test_returns_entries_for_sector(self, db):
        results = db.get_library_by_sector("Technology")
        assert len(results) == 2
        tickers = {r["ticker"] for r in results}
        assert tickers == {"AAPL", "MSFT"}

    def test_filters_by_verdict(self, db):
        results = db.get_library_by_sector("Financials", verdict="no_pass")
        assert len(results) == 1
        assert results[0]["ticker"] == "JPM"

    def test_returns_empty_for_nonexistent_sector(self, db):
        results = db.get_library_by_sector("Energy")
        assert results == []

    def test_returns_empty_for_sector_with_no_matching_verdict(self, db):
        results = db.get_library_by_sector("Technology", verdict="no_pass")
        assert results == []

    def test_respects_limit(self, db):
        results = db.get_library_by_sector("Technology", limit=1)
        assert len(results) == 1

    def test_parses_json_fields(self, db):
        results = db.get_library_by_sector("Technology")
        aapl = next(r for r in results if r["ticker"] == "AAPL")
        assert isinstance(aapl["key_assumptions"], list)
        assert aapl["key_assumptions"] == ["iPhone growth"]
        assert isinstance(aapl["data"], dict)


# --- Existing methods: verify they still work ---

class TestGetFeedbackForRun:
    def test_returns_feedback_for_run(self, db):
        results = db.get_feedback_for_run("run-1")
        assert len(results) == 2

    def test_returns_empty_for_no_feedback(self, db):
        results = db.get_feedback_for_run("run-nonexistent")
        assert results == []


class TestGetRunsByStrategy:
    def test_returns_runs_for_version(self, db):
        results = db.get_runs_by_strategy("ver-1")
        assert len(results) == 2

    def test_returns_all_runs_without_filter(self, db):
        results = db.get_runs_by_strategy()
        assert len(results) == 2

    def test_returns_empty_for_nonexistent_version(self, db):
        results = db.get_runs_by_strategy("ver-nonexistent")
        assert results == []

    def test_respects_limit(self, db):
        results = db.get_runs_by_strategy(limit=1)
        assert len(results) == 1


class TestGetLibraryStats:
    def test_returns_stats(self, db):
        stats = db.get_library_stats()
        assert stats["total"] == 4
        assert stats["by_type"]["ic_review"] == 3
        assert stats["by_type"]["thesis"] == 1
        assert stats["by_verdict"]["pass"] == 2
        assert stats["by_verdict"]["no_pass"] == 1


class TestGetLibraryByTicker:
    def test_returns_entries(self, db):
        results = db.get_library_by_ticker("AAPL")
        assert len(results) == 1
        assert results[0]["expected_return"] == 25.0

    def test_returns_empty_for_unknown_ticker(self, db):
        results = db.get_library_by_ticker("ZZZZ")
        assert results == []


class TestGetRecentEvents:
    def test_returns_events(self, db):
        results = db.get_recent_events()
        assert len(results) == 2

    def test_parses_data_json(self, db):
        results = db.get_recent_events()
        assert any(isinstance(r["data"], dict) for r in results)

    def test_respects_limit(self, db):
        results = db.get_recent_events(limit=1)
        assert len(results) == 1
