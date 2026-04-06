"""Tests for Learning API routes.

Tests the /api/learning/* and /api/library/similar endpoints.
Uses a temporary v2 database and patches _get_db to inject it.
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.core.db_v2 import ScreenerV2DB

app = create_app()
client = TestClient(app)


@pytest.fixture
def v2db():
    """Create a temporary v2 database for testing.

    Uses check_same_thread=False because TestClient runs requests
    in a background thread while tests insert data from the main thread.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    db = ScreenerV2DB(conn=conn)
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture
def patch_db(v2db):
    """Patch _get_db in the learning routes module to return the test db."""
    with patch("backend.api.routes.learning._get_db", return_value=v2db):
        # Also prevent the close() calls in routes from closing our test db
        # by wrapping close as a no-op during tests
        original_close = v2db.close
        v2db.close = lambda: None
        yield v2db
        v2db.close = original_close


# ---------------------------------------------------------------------------
# GET /api/learning/proposals
# ---------------------------------------------------------------------------

def test_get_proposals_empty(patch_db):
    """No proposals returns empty list with stats."""
    resp = client.get("/api/learning/proposals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["proposals"] == []
    assert data["count"] == 0
    assert "stats" in data
    assert data["stats"]["total_resolved"] == 0


def test_get_proposals_with_data(patch_db):
    """Insert test proposals and verify they come back."""
    db = patch_db

    # Create a constitution so proposals can be linked
    db.create_constitution(
        constitution_id="c1",
        name="Test Constitution",
        north_star="Find cheap compounders",
        style_identity="Quality at a discount",
    )

    # Store two pending proposals
    db.store_proposal(
        proposal_id="prop-001",
        constitution_id="c1",
        pattern_type="dismiss_cluster",
        pattern_tag="too_cyclical",
        pattern_count=4,
        pattern_tickers=["F", "GM", "X", "AA"],
        proposal="Penalize cyclical stocks by reducing cheapness score 20%",
        analysis="User consistently dismisses cyclical names despite high scores.",
        code_change="cyclical_penalty = 0.8 if sector in CYCLICAL_SECTORS else 1.0",
        confidence=0.75,
        risk="May under-weight recovery plays",
        evidence_summary="4 dismissals tagged 'too_cyclical'",
    )
    db.store_proposal(
        proposal_id="prop-002",
        constitution_id="c1",
        pattern_type="high_score_dismiss",
        pattern_tag="scoring_mismatch",
        pattern_count=3,
        pattern_tickers=["INTC", "IBM", "VZ"],
        proposal="Increase weight on growth durability in scoring",
        analysis="High-scoring value traps being dismissed.",
        code_change="growth_weight *= 1.5",
        confidence=0.6,
        risk="May miss deep value turnarounds",
        evidence_summary="3 high-scoring stocks dismissed",
    )

    resp = client.get("/api/learning/proposals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["proposals"]) == 2

    # Proposals should be sorted by created_at desc
    ids = [p["id"] for p in data["proposals"]]
    assert "prop-001" in ids
    assert "prop-002" in ids

    # Check proposal structure
    p = next(p for p in data["proposals"] if p["id"] == "prop-001")
    assert p["pattern_type"] == "dismiss_cluster"
    assert p["pattern_tag"] == "too_cyclical"
    assert p["confidence"] == 0.75
    assert p["status"] == "pending"


# ---------------------------------------------------------------------------
# POST /api/learning/proposals/{id} — reject
# ---------------------------------------------------------------------------

def test_reject_proposal(patch_db):
    """POST reject changes status to rejected."""
    db = patch_db

    db.store_proposal(
        proposal_id="prop-rej",
        pattern_type="dismiss_cluster",
        pattern_tag="low_quality",
        pattern_count=3,
        proposal="Lower PE threshold",
        confidence=0.5,
    )

    resp = client.post(
        "/api/learning/proposals/prop-rej",
        json={"action": "reject", "reason": "I like low PE stocks"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "rejected"
    assert data["proposal"]["status"] == "rejected" or data["proposal"]["user_response"] == "rejected"

    # Verify it's no longer in pending
    resp2 = client.get("/api/learning/proposals")
    assert resp2.status_code == 200
    pending_ids = [p["id"] for p in resp2.json()["proposals"]]
    assert "prop-rej" not in pending_ids


def test_reject_proposal_not_found(patch_db):
    """Rejecting a non-existent proposal returns 404."""
    resp = client.post(
        "/api/learning/proposals/nonexistent",
        json={"action": "reject"},
    )
    assert resp.status_code == 404


def test_reject_proposal_already_resolved(patch_db):
    """Cannot reject a proposal that's already resolved."""
    db = patch_db

    db.store_proposal(
        proposal_id="prop-done",
        pattern_type="dismiss_cluster",
        pattern_tag="test",
        pattern_count=3,
        proposal="Test proposal",
        confidence=0.5,
    )
    # Resolve it first
    db.resolve_proposal("prop-done", user_response="rejected")

    resp = client.post(
        "/api/learning/proposals/prop-done",
        json={"action": "reject"},
    )
    assert resp.status_code == 409


def test_invalid_action(patch_db):
    """Invalid action returns 400."""
    patch_db.store_proposal(
        proposal_id="prop-inv",
        pattern_type="dismiss_cluster",
        pattern_tag="test",
        pattern_count=3,
        proposal="Test",
        confidence=0.5,
    )
    resp = client.post(
        "/api/learning/proposals/prop-inv",
        json={"action": "maybe"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/learning/drift — behavioral drift
# ---------------------------------------------------------------------------

def test_get_drift_no_constitution(patch_db):
    """No constitution returns graceful message."""
    resp = client.get("/api/learning/drift")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_enough_data"] is False
    assert "No active constitution" in data["summary"]


def test_get_drift_insufficient_data(patch_db):
    """With constitution but no IC decisions, returns insufficient data message."""
    db = patch_db

    db.create_constitution(
        constitution_id="c1",
        name="Test",
        north_star="Find cheap stocks",
        style_identity="Quality compounder",
        must_have_signals=["ROIC > 15%", "GM > 40%"],
        anti_signals=["D/E > 2x"],
    )

    resp = client.get("/api/learning/drift")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_enough_data"] is False
    assert data["decisions_analyzed"] == 0
    assert "Need at least" in data["summary"]


def test_get_drift_with_decisions(patch_db):
    """With enough IC decisions, drift analysis runs."""
    db = patch_db

    db.create_constitution(
        constitution_id="c1",
        name="Test",
        north_star="Find cheap stocks",
        style_identity="Concentrated quality compounder",
        must_have_signals=["ROIC > 15%"],
        anti_signals=["D/E > 2x"],
    )

    # Insert enough IC pass events
    for i, ticker in enumerate(["MSFT", "AAPL", "GOOG", "AMZN", "META", "NVDA"]):
        db.record_judgment_event(
            event_type="ic_passed",
            ticker=ticker,
            agent="ic_review",
            data={"base_return": 25 + i, "bear_return": 15 + i, "conviction": 4},
        )

    resp = client.get("/api/learning/drift")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_enough_data"] is True
    assert data["decisions_analyzed"] >= 6
    assert "summary" in data


# ---------------------------------------------------------------------------
# GET /api/learning/outcomes
# ---------------------------------------------------------------------------

def test_get_outcomes_empty(patch_db):
    """No outcomes returns empty list."""
    resp = client.get("/api/learning/outcomes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcomes"] == []
    assert data["count"] == 0


def _setup_screener_run(db, run_id="run-1", tickers=None):
    """Helper to set up FK-compliant screener run with tickers."""
    tickers = tickers or ["AAPL", "GOOG"]
    # strategy_profiles -> strategy_versions -> tickers -> screener_runs
    db.create_strategy("s1", "Test Strategy")
    db.create_version("v1", "s1", 1, "def score(s): return {'score': 5}")
    for t in tickers:
        db.conn.execute(
            "INSERT OR IGNORE INTO tickers (ticker, added_at) VALUES (?, ?)",
            (t, "2025-01-01T00:00:00Z"),
        )
    db.conn.execute(
        """INSERT INTO screener_runs (id, strategy_version_id, run_at, universe_size,
           scored_count, failed_count, duration_s, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, "v1", "2025-01-01T00:00:00Z", 200, 50, 0, 10.0, "complete"),
    )
    db.conn.commit()


def test_get_outcomes_with_data(patch_db):
    """Insert outcome snapshots and verify they come back with alpha."""
    db = patch_db
    _setup_screener_run(db, tickers=["AAPL", "GOOG"])

    db.record_outcome_snapshot(
        screener_run_id="run-1",
        ticker="AAPL",
        screened_at="2025-01-01T00:00:00Z",
        check_at="2025-04-01T00:00:00Z",
        days_elapsed=90,
        price_at_screen=150.0,
        price_at_check=165.0,
        return_pct=10.0,
        benchmark_return_pct=5.0,
    )
    db.record_outcome_snapshot(
        screener_run_id="run-1",
        ticker="GOOG",
        screened_at="2025-01-01T00:00:00Z",
        check_at="2025-04-01T00:00:00Z",
        days_elapsed=90,
        price_at_screen=140.0,
        price_at_check=130.0,
        return_pct=-7.14,
        benchmark_return_pct=5.0,
    )

    resp = client.get("/api/learning/outcomes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2

    # Check alpha computation
    aapl = next(o for o in data["outcomes"] if o["ticker"] == "AAPL")
    assert aapl["alpha_pct"] == 5.0
    assert aapl["return_pct"] == 10.0
    assert aapl["days_elapsed"] == 90

    goog = next(o for o in data["outcomes"] if o["ticker"] == "GOOG")
    assert goog["alpha_pct"] == -12.14


def test_get_outcomes_filter_by_ticker(patch_db):
    """Filtering outcomes by ticker works."""
    db = patch_db
    _setup_screener_run(db, tickers=["AAPL", "GOOG"])

    db.record_outcome_snapshot(
        screener_run_id="run-1", ticker="AAPL",
        screened_at="2025-01-01", check_at="2025-04-01",
        days_elapsed=90, price_at_screen=150, price_at_check=165,
        return_pct=10.0, benchmark_return_pct=5.0,
    )
    db.record_outcome_snapshot(
        screener_run_id="run-1", ticker="GOOG",
        screened_at="2025-01-01", check_at="2025-04-01",
        days_elapsed=90, price_at_screen=140, price_at_check=130,
        return_pct=-7.14, benchmark_return_pct=5.0,
    )

    resp = client.get("/api/learning/outcomes?ticker=AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["outcomes"][0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# POST /api/library/similar
# ---------------------------------------------------------------------------

def test_library_similar_empty(patch_db):
    """No library entries returns empty list."""
    resp = client.post(
        "/api/library/similar",
        json={"ticker": "MSFT", "sector": "Technology", "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["count"] == 0


def test_library_similar_with_data(patch_db):
    """Insert library entries and find similar ones."""
    db = patch_db

    # Insert library entries
    for ticker, sector, gm, roic in [
        ("MSFT", "Technology", 68.5, 28.1),
        ("AAPL", "Technology", 45.0, 55.0),   # GM too far (45 vs 68.5 ± 10)
        ("GOOG", "Technology", 62.0, 26.0),   # GM within ± 10, ROIC within ± 5
        ("JNJ", "Healthcare", 68.0, 20.0),    # Different sector
        ("ADBE", "Technology", 88.0, 30.0),   # GM too far (88 vs 68.5 ± 10)
    ]:
        db.conn.execute(
            """INSERT INTO library_entries
               (ticker, entry_type, verdict, conviction, expected_return, discount_pct,
                sector, gross_margin, roic, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, "thesis", "pass", 4, 25.0, 30.0, sector, gm, roic,
             "2025-06-01T00:00:00Z"),
        )
    db.conn.commit()

    # Find stocks similar to MSFT (Tech, GM ~68, ROIC ~28)
    resp = client.post(
        "/api/library/similar",
        json={
            "ticker": "MSFT",
            "sector": "Technology",
            "gross_margin": 68.5,
            "roic": 28.1,
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0

    # MSFT should not be in its own results
    tickers = [r["ticker"] for r in data["results"]]
    assert "MSFT" not in tickers

    # GOOG should match (same sector, GM within 10pp, ROIC within 5pp)
    assert "GOOG" in tickers

    # JNJ should NOT match (different sector)
    assert "JNJ" not in tickers


def test_library_similar_no_sector_filter(patch_db):
    """Without sector filter, cross-sector results are returned."""
    db = patch_db

    for ticker, sector, gm, roic in [
        ("MSFT", "Technology", 68.5, 28.1),
        ("JNJ", "Healthcare", 68.0, 27.0),
    ]:
        db.conn.execute(
            """INSERT INTO library_entries
               (ticker, entry_type, verdict, conviction, expected_return, discount_pct,
                sector, gross_margin, roic, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, "thesis", "pass", 4, 25.0, 30.0, sector, gm, roic,
             "2025-06-01T00:00:00Z"),
        )
    db.conn.commit()

    resp = client.post(
        "/api/library/similar",
        json={"ticker": "MSFT", "gross_margin": 68.5, "roic": 28.1, "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    # JNJ should appear since no sector filter
    tickers = [r["ticker"] for r in data["results"]]
    assert "JNJ" in tickers
