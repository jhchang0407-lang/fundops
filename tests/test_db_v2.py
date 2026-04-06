"""Tests for v2 database tables: strategy profiles, versions, feedback, outcomes."""

import os
import tempfile
import pytest
from backend.core.db_v2 import ScreenerV2DB


@pytest.fixture
def v2db():
    """Create a temporary v2 database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = ScreenerV2DB(db_path=db_path)
    yield db
    db.close()
    os.unlink(db_path)


# --- Strategy Profiles ---

def test_create_strategy(v2db):
    s = v2db.create_strategy("s1", "Test Strategy", north_star="Find cheap stocks",
                              dimensions={"cheapness": "PE < 15"})
    assert s["id"] == "s1"
    assert s["name"] == "Test Strategy"
    assert s["north_star"] == "Find cheap stocks"
    assert s["dimensions"]["cheapness"] == "PE < 15"


def test_get_strategy(v2db):
    v2db.create_strategy("s1", "Test", north_star="test")
    s = v2db.get_strategy("s1")
    assert s is not None
    assert s["north_star"] == "test"


def test_get_strategy_not_found(v2db):
    assert v2db.get_strategy("nonexistent") is None


def test_update_strategy(v2db):
    v2db.create_strategy("s1", "Original")
    v2db.update_strategy("s1", name="Updated", north_star="new goal")
    s = v2db.get_strategy("s1")
    assert s["name"] == "Updated"
    assert s["north_star"] == "new goal"


def test_get_active_strategy(v2db):
    v2db.create_strategy("s1", "First")
    v2db.create_strategy("s2", "Second")
    active = v2db.get_active_strategy()
    assert active["id"] == "s2"  # Most recently created


def test_list_strategies(v2db):
    v2db.create_strategy("s1", "First")
    v2db.create_strategy("s2", "Second")
    strategies = v2db.list_strategies()
    assert len(strategies) == 2


# --- Strategy Versions ---

def test_create_version(v2db):
    v2db.create_strategy("s1", "Test")
    v = v2db.create_version("v1", "s1", 1, "def score(s): return {'score': 5}",
                             label_map={"score": {"label": "Score"}},
                             explanation="Simple scorer")
    assert v["id"] == "v1"
    assert v["scoring_code"] == "def score(s): return {'score': 5}"
    assert v["label_map"]["score"]["label"] == "Score"


def test_version_updates_active(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code1")
    s = v2db.get_strategy("s1")
    assert s["active_version_id"] == "v1"


def test_get_version_history(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code1", change_reason="initial")
    v2db.create_version("v2", "s1", 2, "code2", change_reason="updated")
    history = v2db.get_version_history("s1")
    assert len(history) == 2
    assert history[0]["version_number"] == 2  # Descending order


def test_get_latest_version(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code1")
    v2db.create_version("v2", "s1", 2, "code2")
    latest = v2db.get_latest_version("s1")
    assert latest["id"] == "v2"


# --- Screener Runs ---

def test_record_screener_run(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    v2db.record_screener_run("run1", "v1", universe_size=500, scored_count=480)
    run = v2db.get_screener_run("run1")
    assert run is not None
    assert run["universe_size"] == 500
    assert run["scored_count"] == 480


def test_get_runs_by_strategy(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    v2db.record_screener_run("run1", "v1")
    v2db.record_screener_run("run2", "v1")
    runs = v2db.get_runs_by_strategy("v1")
    assert len(runs) == 2


# --- Feedback Records ---

def test_record_feedback(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    v2db.record_screener_run("run1", "v1")
    # Need ticker in tickers table
    v2db.conn.execute("CREATE TABLE IF NOT EXISTS tickers (ticker TEXT PRIMARY KEY)")
    v2db.conn.execute("INSERT OR IGNORE INTO tickers (ticker) VALUES (?)", ("AAPL",))
    v2db.conn.commit()

    v2db.record_feedback("run1", "AAPL", "promoted", score_at_feedback=8.2, rank_at_feedback=1)
    fb = v2db.get_feedback_for_run("run1")
    assert len(fb) == 1
    assert fb[0]["feedback"] == "promoted"
    assert fb[0]["ticker"] == "AAPL"


def test_record_dismiss_feedback(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    v2db.record_screener_run("run1", "v1")
    v2db.conn.execute("CREATE TABLE IF NOT EXISTS tickers (ticker TEXT PRIMARY KEY)")
    v2db.conn.execute("INSERT OR IGNORE INTO tickers (ticker) VALUES (?)", ("BBY",))
    v2db.conn.commit()

    v2db.record_feedback("run1", "BBY", "dismissed", dismiss_reason="Too much debt")
    fb = v2db.get_feedback_by_ticker("BBY")
    assert len(fb) == 1
    assert fb[0]["dismiss_reason"] == "Too much debt"


# --- Outcome Snapshots ---

def test_record_outcome_snapshot(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    v2db.record_screener_run("run1", "v1")
    v2db.conn.execute("CREATE TABLE IF NOT EXISTS tickers (ticker TEXT PRIMARY KEY)")
    v2db.conn.execute("INSERT OR IGNORE INTO tickers (ticker) VALUES (?)", ("PAYC",))
    v2db.conn.commit()

    v2db.record_outcome_snapshot(
        screener_run_id="run1", ticker="PAYC",
        screened_at="2025-12-01", check_at="2026-03-01",
        days_elapsed=90, price_at_screen=260, price_at_check=310,
        return_pct=19.2, benchmark_return_pct=4.5, alpha_pct=14.7,
        thesis_integrity={"score": 95, "gross_margin_held": True},
    )
    outcomes = v2db.get_outcomes_for_strategy(ticker="PAYC")
    assert len(outcomes) == 1
    assert outcomes[0]["return_pct"] == 19.2
    assert outcomes[0]["thesis_integrity"]["score"] == 95


def test_get_due_checks(v2db):
    v2db.create_strategy("s1", "Test")
    v2db.create_version("v1", "s1", 1, "code")
    # Create a run from 91 days ago
    import datetime
    old_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=91)).isoformat()
    v2db.conn.execute(
        "INSERT INTO screener_runs (id, strategy_version_id, run_at, status, top_results) VALUES (?, ?, ?, ?, ?)",
        ("old-run", "v1", old_date, "complete", '[{"ticker": "AAPL", "score": 8.0}]')
    )
    v2db.conn.commit()

    due = v2db.get_due_checks([90])
    assert len(due) == 1
    assert due[0]["run_id"] == "old-run"
    assert due[0]["check_days"] == 90


def test_get_due_checks_none_due(v2db):
    due = v2db.get_due_checks([90])
    assert len(due) == 0
