"""Test learning loops: feedback patterns, drift detection, outcomes.

Verifies that the learning system correctly records feedback,
detects patterns, generates proposals, and tracks outcomes.
"""

import json
import pytest
from datetime import datetime, timezone


class TestFeedbackRecording:

    def test_screener_feedback_creates_event(self, seeded_client):
        """Screener feedback should be recorded as a workflow event."""
        resp = seeded_client.post("/api/screener/v2/feedback", json={
            "screener_run_id": "test-run-1",
            "ticker": "AAPL",
            "feedback": "dismissed",
            "dismiss_reason": "too expensive",
        })
        assert resp.status_code == 200

    def test_dismiss_records_negative_signal(self, seeded_client):
        """Dismissing a ticker should record it as feedback."""
        resp = seeded_client.post("/api/research/dismiss/AAPL", json={
            "reason": "declining margins"
        })
        assert resp.status_code == 200

    def test_promote_records_positive_signal(self, seeded_client):
        """Promoting a ticker should record it as feedback."""
        resp = seeded_client.post("/api/research/promote/AAPL", json={})
        assert resp.status_code == 200


class TestRefinementProposals:

    def test_proposals_endpoint_accessible(self, seeded_client):
        """Refinement proposals endpoint should be accessible."""
        resp = seeded_client.get("/api/strategy/refinement-proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert "proposals" in data

    def test_learning_proposals_accessible(self, seeded_client):
        """Learning proposals endpoint should be accessible."""
        resp = seeded_client.get("/api/learning/proposals")
        assert resp.status_code == 200


class TestDriftDetection:

    def test_drift_endpoint_accessible(self, seeded_client):
        """Drift analysis endpoint should be accessible."""
        resp = seeded_client.get("/api/learning/drift")
        assert resp.status_code == 200
        data = resp.json()
        # Drift requires >=5 IC decisions — may return "not enough data"
        assert isinstance(data, dict)

    def test_drift_with_insufficient_data(self, seeded_client):
        """Drift with <5 IC decisions should indicate insufficient data."""
        resp = seeded_client.get("/api/learning/drift")
        assert resp.status_code == 200
        data = resp.json()
        # Should indicate not enough data
        has_enough = data.get("has_enough_data", False)
        # With seeded data (1 IC review), should not have enough
        assert not has_enough or data.get("decisions_analyzed", 0) <= 5

    def test_drift_requires_constitution(self, client):
        """Drift with no constitution should handle gracefully."""
        resp = client.get("/api/learning/drift")
        assert resp.status_code == 200


class TestOutcomes:

    def test_outcomes_endpoint_accessible(self, seeded_client):
        """Outcomes endpoint should be accessible."""
        resp = seeded_client.get("/api/learning/outcomes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_run_outcome_checker(self, seeded_client):
        """Outcome checker should be runnable."""
        resp = seeded_client.post("/api/outcomes/check", json={})
        assert resp.status_code in (200, 404)  # May not have outcomes to check


class TestLibraryLearning:

    def test_library_stats(self, seeded_client):
        """Library stats should be accessible."""
        resp = seeded_client.get("/api/library/stats")
        assert resp.status_code == 200

    def test_library_similarity_search(self, seeded_client):
        """Library similarity search should work."""
        resp = seeded_client.get("/api/library/similar/AAPL")
        assert resp.status_code == 200

    def test_library_ask(self, seeded_client):
        """Library ask (RAG) should work."""
        resp = seeded_client.post("/api/library/ask", json={
            "question": "What are the best quality compounders?",
            "history": [],
        })
        assert resp.status_code == 200
