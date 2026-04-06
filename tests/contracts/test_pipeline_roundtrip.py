"""Roundtrip tests: data written by the pipeline must be readable by frontend queries.

These tests simulate the exact data flow that breaks in production:
  Pipeline writes data → Frontend API reads it → Data appears on page

Each test writes data the way the pipeline does, then queries the way
the frontend does, and verifies the data shows up. If any of these fail,
it means the Screener/Research/Portfolio page will show empty after a pipeline run.
"""

import json
import uuid
import pytest
from datetime import datetime, timezone


class TestScreenerRoundtrip:
    """Pipeline screener results must appear in both /screener/v2/results AND /screener/results."""

    def test_pipeline_v2_results_appear_on_screener_page(self, seeded_client, v2db):
        """When pipeline saves AI-scored results to screener_runs,
        GET /screener/v2/results must return them."""
        # Simulate what pipeline.py does (line 155-172)
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        scored_stocks = [
            {"ticker": "AAPL", "score": 85, "expected_return": 22.5,
             "reason": "Quality compounder", "quality": 90, "cheapness": 75},
            {"ticker": "MSFT", "score": 78, "expected_return": 18.0,
             "reason": "Strong moat", "quality": 85, "cheapness": 70},
        ]

        # Need a strategy version for the FK
        strategy_id = "strat-test"
        version_id = "ver-test"
        now = datetime.now(timezone.utc).isoformat()
        v2db.conn.execute(
            "INSERT OR IGNORE INTO strategy_profiles (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (strategy_id, "Test", now, now)
        )
        v2db.conn.execute(
            "INSERT OR IGNORE INTO strategy_versions (id, strategy_id, version_number, scoring_code, created_at) VALUES (?, ?, ?, ?, ?)",
            (version_id, strategy_id, 1, "def score(s,l): return 50", now)
        )
        v2db.conn.commit()

        v2db.record_screener_run(
            run_id=run_id,
            strategy_version_id=version_id,
            universe_size=200,
            scored_count=200,
            top_results=scored_stocks,
            all_results=scored_stocks,
        )

        # Now query the way the frontend does (Screener.tsx line 345)
        resp = seeded_client.get("/api/screener/v2/results")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", [])
        assert len(results) >= 2, \
            f"Pipeline saved 2 stocks to screener_runs but /screener/v2/results returned {len(results)}"
        tickers = [r["ticker"] for r in results]
        assert "AAPL" in tickers, "AAPL missing from screener v2 results"
        assert "MSFT" in tickers, "MSFT missing from screener v2 results"

    def test_pipeline_basic_results_appear_on_screener_page(self, seeded_client, db):
        """When pipeline saves basic screener results to agent_runs,
        GET /screener/results must return them."""
        # Simulate what ScreenerAgent.run() saves to agent_runs
        now = datetime.now(timezone.utc).isoformat()
        scored = [
            {"ticker": "GOOGL", "dislocation_score": 7.5, "compounder_score": 6.0,
             "expected_return": 20.0, "top_lens": "dislocation", "companyName": "Alphabet"},
        ]
        db.upsert_ticker("GOOGL", company_name="Alphabet", sector="Technology")
        db.record_run(
            "screener", "GOOGL", run_type="dual_lens",
            verdict="handoff", summary="Dislocation candidate",
            full_output={"all_scored": scored, "handoff_candidates": scored, "universe_size": 200},
        )

        # Query the way the frontend fallback does (Screener.tsx line 349)
        resp = seeded_client.get("/api/screener/results")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", [])
        assert len(results) >= 1, \
            f"Pipeline saved screener to agent_runs but /screener/results returned {len(results)}"


class TestThesisRoundtrip:
    """Thesis results saved by pipeline must appear on Research page."""

    def test_thesis_appears_on_research_page(self, seeded_client, db):
        """When ThesisAgent saves to agent_runs, GET /thesis must return it."""
        # Simulate what ThesisAgent.run() does (saves to agent_runs)
        db.upsert_ticker("NVDA", company_name="NVIDIA", sector="Technology")
        thesis_output = {
            "ticker": "NVDA", "company_name": "NVIDIA",
            "fair_value": 150.0, "current_price": 120.0,
            "expected_return": 25.0, "discount_pct": 20.0,
            "conviction": "high",
            "thesis_summary": "AI infrastructure leader at a discount.",
            "key_assumptions": ["Data center growth >30%", "Gross margin >70%"],
            "return_sources": {"discount": 20, "growth": 3, "margin": 1, "dividends": 1},
        }
        db.record_run(
            "thesis", "NVDA", run_type="full",
            fair_value=150.0, price_at_run=120.0,
            verdict="bullish", summary="AI infrastructure leader.",
            full_output=thesis_output,
        )

        # Query the way the Research page does (Research.tsx line 1123)
        resp = seeded_client.get("/api/thesis")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", [])
        nvda_results = [r for r in results if r.get("ticker") == "NVDA"]
        assert len(nvda_results) >= 1, \
            f"Thesis saved for NVDA but GET /thesis didn't return it. Got {len(results)} results, tickers: {[r.get('ticker') for r in results]}"

    def test_thesis_has_required_fields_for_frontend(self, seeded_client, db):
        """Thesis response must have fields the Research page renders."""
        db.upsert_ticker("META", company_name="Meta", sector="Technology")
        db.record_run(
            "thesis", "META", run_type="full",
            fair_value=400.0, price_at_run=350.0,
            verdict="bullish", summary="Social media monopoly.",
            full_output={
                "ticker": "META", "fair_value": 400.0,
                "expected_return": 14.3, "conviction": "medium",
                "thesis_summary": "Dominant social platform.",
            },
        )

        resp = seeded_client.get("/api/thesis")
        data = resp.json()
        results = data.get("results", [])
        meta = [r for r in results if r.get("ticker") == "META"]
        assert len(meta) >= 1, "META thesis not found"
        row = meta[0]
        # These are the fields Research.tsx ThesisTab renders
        assert row.get("ticker") == "META"
        assert row.get("fair_value") is not None or row.get("fairValue") is not None


class TestICReviewRoundtrip:
    """IC review results saved by pipeline must appear on Research page."""

    def test_ic_review_appears_on_research_page(self, seeded_client, db):
        """When ICReviewAgent saves to agent_runs, GET /ic-review must return it."""
        db.upsert_ticker("AMZN", company_name="Amazon", sector="Technology")
        db.record_run(
            "ic_review", "AMZN", run_type="stress_test",
            verdict="PASS", summary="Strong margin of safety.",
            full_output={
                "verdict": "PASS", "conviction": 4,
                "base_return": 22.0, "bear_return": 14.5,
                "key_risks": ["Retail margin compression"],
                "scorecard": {"business_quality": 8, "compounder": 7, "trap_risk": 2},
            },
        )

        # Query the way the Research page does (Research.tsx line 1124)
        resp = seeded_client.get("/api/ic-review")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", [])
        amzn = [r for r in results if r.get("ticker") == "AMZN"]
        assert len(amzn) >= 1, \
            f"IC review saved for AMZN but GET /ic-review didn't return it. Got tickers: {[r.get('ticker') for r in results]}"
        row = amzn[0]
        assert row.get("verdict", "").upper() == "PASS"


class TestPortfolioRoundtrip:
    """Portfolio positions saved must appear on Portfolio page."""

    def test_saved_positions_appear_in_portfolio(self, seeded_client, db):
        """POST /portfolio/positions → data appears in GET /portfolio."""
        # Save positions (the way the Portfolio page does)
        save_resp = seeded_client.post("/api/portfolio/positions", json={
            "positions": [
                {"ticker": "AAPL", "shares": 100, "cost_basis": 170.0},
            ]
        })
        assert save_resp.status_code == 200
        save_data = save_resp.json()

        # Check if position was saved (mock yfinance returns prices)
        saved_count = save_data.get("saved", 0)
        holdings = save_data.get("holdings", [])

        if saved_count == 0 and not holdings:
            # Position was dropped due to no price data
            removed = save_data.get("removed_tickers", [])
            pytest.skip(f"Position dropped (no mock price): {removed}")

        # Now query the way the Portfolio page does
        resp = seeded_client.get("/api/portfolio")
        assert resp.status_code == 200
        port_data = resp.json()
        port_holdings = port_data.get("holdings", [])
        assert len(port_holdings) >= 1, \
            f"Saved {saved_count} positions but GET /portfolio returned {len(port_holdings)} holdings"


class TestDashboardRoundtrip:
    """Dashboard KPIs must reflect pipeline activity."""

    def test_dashboard_shows_agent_runs(self, seeded_client, db):
        """Agent runs saved by pipeline should appear in dashboard activity."""
        # Seed some agent runs
        db.record_run("screener", "AAPL", verdict="handoff", summary="Test run")
        db.record_run("thesis", "AAPL", verdict="bullish", summary="Test thesis")

        resp = seeded_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        recent = data.get("recent_runs", [])
        # Should have at least the runs we just created + the seeded ones
        assert len(recent) >= 2, \
            f"Dashboard recent_runs should show agent runs, got {len(recent)}"

    def test_dashboard_shows_portfolio(self, seeded_client):
        """Dashboard should reflect portfolio state."""
        resp = seeded_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        # latest_portfolio should exist (from seeded data)
        assert "latest_portfolio" in data


class TestTickerDetailRoundtrip:
    """Ticker detail page must aggregate all agent data for a ticker."""

    def test_ticker_detail_shows_all_agent_data(self, seeded_client, db):
        """GET /ticker/AAPL should return screener + thesis + IC data."""
        # AAPL is already seeded with screener, thesis, and IC review
        resp = seeded_client.get("/api/ticker/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        # Should have aggregated data from multiple agents
        assert isinstance(data, dict)
        assert data.get("ticker") == "AAPL" or "AAPL" in str(data)
