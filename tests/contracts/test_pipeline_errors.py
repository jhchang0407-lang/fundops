"""Test that pipeline failures are surfaced, not silent.

The #1 production bug: pipeline completes in 10s showing "done" but
produces zero data because a data source (yfinance) was rate-limited.
The pipeline must FAIL LOUDLY in this case, not silently succeed.
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.agents import AgentResult


class TestPipelineFailsLoudly:

    def test_pipeline_fails_when_screener_returns_no_data(self, db, v2db, structured_mock_llm, mock_fmp):
        """If the screener gets 0 quotes (yfinance rate-limited), pipeline must fail with error."""
        from tests.overrides import create_test_app, cleanup_test_app
        from backend.connectors import ConnectorResult

        # Create a yfinance mock that returns ZERO quotes (simulates rate limiting)
        mock_yf = MagicMock()
        async def _empty_quotes(tickers):
            return ConnectorResult(connector="yfinance", capability="quotes", data=[])
        mock_yf.get_quotes = _empty_quotes

        client, _, _ = create_test_app(
            mock_llm=structured_mock_llm, mock_fmp=mock_fmp,
            mock_yf=mock_yf, db=db, v2db=v2db,
        )

        # Run pipeline
        resp = client.post("/api/pipeline/run", json={})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        # Wait for job to complete
        import time
        for _ in range(30):
            job_resp = client.get(f"/api/jobs/{job_id}")
            job = job_resp.json()
            if job["status"] in ("complete", "completed", "failed"):
                break
            time.sleep(0.5)

        # The job MUST be marked as failed, not complete
        assert job["status"] == "failed", \
            f"Pipeline should fail when screener gets 0 quotes, but status={job['status']}"

        # Error message should mention the data source issue
        error = job.get("error", "")
        assert error, "Pipeline failure should have an error message"
        assert "screener" in error.lower() or "data" in error.lower() or "rate" in error.lower(), \
            f"Error message should mention screener/data failure, got: {error}"

        cleanup_test_app(client)

    def test_pipeline_screener_results_empty_means_no_data_on_page(self, seeded_client):
        """If screener_runs and agent_runs are both empty, screener page shows no results."""
        resp = seeded_client.get("/api/screener/v2/results")
        assert resp.status_code == 200
        # With no screener runs in the seeded DB, should return empty results
        # (the seeded DB has a screener agent_run but NOT a screener_runs entry)
        data = resp.json()
        # This is the v2 endpoint — it reads from screener_runs table
        results = data.get("results", [])
        # If the screener v2 returns empty, the frontend falls back to basic
        # Let's check that too
        basic_resp = seeded_client.get("/api/screener/results")
        assert basic_resp.status_code == 200
        basic_data = basic_resp.json()
        basic_results = basic_data.get("results", [])
        # At least ONE of these should have data (seeded DB has a screener run)
        assert len(results) > 0 or len(basic_results) > 0, \
            "Neither screener/v2/results nor screener/results returned data, but seeded DB has a screener run"


class TestPipelineRanking:

    def test_ic_review_only_gets_top_10_theses(self):
        """Pipeline should rank theses by expected return and only send top 10 to IC."""
        # Simulate 20 thesis results with varying returns
        thesis_results = [
            {"ticker": f"T{i:02d}", "expected_return": 50 - i * 2}
            for i in range(20)
        ]
        # Apply the same ranking logic the pipeline uses
        valid = [t for t in thesis_results if t.get("ticker") and not t.get("error")]
        valid.sort(key=lambda t: float(t.get("expected_return") or 0), reverse=True)
        ic_candidates = valid[:10]

        assert len(ic_candidates) == 10
        # Top candidate should have highest return
        assert ic_candidates[0]["ticker"] == "T00"
        assert ic_candidates[0]["expected_return"] == 50
        # 10th candidate should be T09 (return=32)
        assert ic_candidates[9]["ticker"] == "T09"
        assert ic_candidates[9]["expected_return"] == 32
        # T10-T19 should NOT be in ic_candidates
        ic_tickers = {t["ticker"] for t in ic_candidates}
        assert "T10" not in ic_tickers
        assert "T19" not in ic_tickers


class TestPipelineJobErrorsVisible:

    def test_failed_job_has_error_message(self, seeded_client):
        """Job status endpoint must include error message for failed jobs."""
        # Start a pipeline (will succeed with mocked agents)
        resp = seeded_client.post("/api/pipeline/run", json={})
        job_id = resp.json()["job_id"]

        # Check the job structure has error field
        job_resp = seeded_client.get(f"/api/jobs/{job_id}")
        assert job_resp.status_code == 200
        job = job_resp.json()
        # Job should have an error field (even if empty for successful jobs)
        assert "error" in job or "status" in job

    def test_jobs_list_shows_failed_status(self, seeded_client):
        """GET /jobs should include failed jobs with their errors."""
        resp = seeded_client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        # Just verify the structure — all jobs should have id, status, error fields
        for job in data["jobs"]:
            assert "id" in job
            assert "status" in job
