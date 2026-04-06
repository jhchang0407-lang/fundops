"""Tests for B2 — screener feedback wiring.

Verifies that Loop 1 pattern detection is triggered after screener runs
and that failures are non-blocking.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.resolved = {"db_path": ":memory:", "agents": {"screener": {"config": {}}}}
    return config


def _make_job(job_id="screener-test1", agent="screener", status="complete"):
    """Create a minimal Job-like object."""
    job = MagicMock()
    job.id = job_id
    job.agent = agent
    job.status = status
    return job


class TestScreenerFeedbackDetection:
    """Test that detect_patterns is called after screener completes."""

    async def test_screener_feedback_detection_called(self, mock_config):
        """detect_patterns should be called when the screener on_complete fires."""
        from backend.api.routes.agents import _screener_feedback_callback

        callback = _screener_feedback_callback(mock_config)
        job = _make_job()

        mock_patterns = [
            {"type": "dismiss_cluster", "tag": "too_cyclical", "count": 4,
             "tickers": ["X", "CLF", "AA", "NUE"], "details": "test", "evidence": []},
        ]

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.feedback_loop.detect_patterns", new_callable=AsyncMock) as mock_detect:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            mock_detect.return_value = mock_patterns

            await callback(job)

            mock_detect.assert_called_once_with(mock_db_instance)
            mock_db_instance.close.assert_called_once()

    async def test_screener_feedback_failure_non_blocking(self, mock_config):
        """If detect_patterns raises, the callback should not propagate the exception."""
        from backend.api.routes.agents import _screener_feedback_callback

        callback = _screener_feedback_callback(mock_config)
        job = _make_job()

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.feedback_loop.detect_patterns", new_callable=AsyncMock) as mock_detect:
            MockDB.return_value = MagicMock()
            mock_detect.side_effect = RuntimeError("DB connection lost")

            # Should NOT raise — failure is caught and logged
            await callback(job)

    async def test_screener_feedback_no_patterns(self, mock_config):
        """When no patterns are found, callback completes silently."""
        from backend.api.routes.agents import _screener_feedback_callback

        callback = _screener_feedback_callback(mock_config)
        job = _make_job()

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.feedback_loop.detect_patterns", new_callable=AsyncMock) as mock_detect:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            mock_detect.return_value = []

            await callback(job)

            mock_detect.assert_called_once()
            mock_db_instance.close.assert_called_once()

    async def test_screener_feedback_db_init_failure_non_blocking(self, mock_config):
        """If ScreenerV2DB fails to initialize, callback should not propagate."""
        from backend.api.routes.agents import _screener_feedback_callback

        callback = _screener_feedback_callback(mock_config)
        job = _make_job()

        with patch("backend.core.db_v2.ScreenerV2DB", side_effect=Exception("no db")):
            # Should NOT raise
            await callback(job)


class TestICDriftTrigger:
    """Test that Loop 2 behavioral drift analysis is triggered after IC review."""

    async def test_ic_drift_trigger_called(self, mock_config):
        """analyze_drift should be called when >=3 IC decisions exist."""
        from backend.api.routes.agents import _ic_drift_callback

        callback = _ic_drift_callback(mock_config)
        job = _make_job(job_id="ic-test1", agent="ic_review")

        mock_drift = {
            "has_enough_data": True,
            "decisions_analyzed": 5,
            "signal_drift": [{"signal": "ROIC > 15%", "violations": 2, "total_approvals": 5, "violation_rate": 40.0}],
            "anti_signal_violations": [],
            "style_drift": [],
            "override_patterns": [],
            "approval_profile": {},
            "summary": "Signal drift: 'ROIC > 15%' violated in 40% of approvals",
        }
        mock_constitution = {"style_identity": "quality compounder", "must_have_signals": ["ROIC > 15%"]}

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.behavioral.analyze_drift", new_callable=AsyncMock) as mock_analyze:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            # 3 passes + 1 fail = 4 decisions (>=3 threshold)
            mock_db_instance.get_events_by_type.side_effect = lambda event_type, limit=50: (
                [{"event_type": "ic_passed", "ticker": "AAPL"}, {"event_type": "ic_passed", "ticker": "MSFT"}, {"event_type": "ic_passed", "ticker": "GOOG"}]
                if event_type == "ic_passed"
                else [{"event_type": "ic_failed", "ticker": "META"}]
            )
            mock_db_instance.get_active_constitution.return_value = mock_constitution
            mock_analyze.return_value = mock_drift

            await callback(job)

            mock_analyze.assert_called_once_with(mock_db_instance, mock_constitution)
            mock_db_instance.record_judgment_event.assert_called_once()
            call_kwargs = mock_db_instance.record_judgment_event.call_args
            assert call_kwargs.kwargs["event_type"] == "drift_detected"
            assert call_kwargs.kwargs["agent"] == "behavioral"
            mock_db_instance.close.assert_called_once()

    async def test_ic_drift_trigger_insufficient_decisions(self, mock_config):
        """analyze_drift should NOT be called when <3 IC decisions exist."""
        from backend.api.routes.agents import _ic_drift_callback

        callback = _ic_drift_callback(mock_config)
        job = _make_job(job_id="ic-test2", agent="ic_review")

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.behavioral.analyze_drift", new_callable=AsyncMock) as mock_analyze:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            # Only 2 decisions total — below threshold
            mock_db_instance.get_events_by_type.side_effect = lambda event_type, limit=50: (
                [{"event_type": "ic_passed", "ticker": "AAPL"}]
                if event_type == "ic_passed"
                else [{"event_type": "ic_failed", "ticker": "META"}]
            )

            await callback(job)

            mock_analyze.assert_not_called()
            mock_db_instance.close.assert_called_once()

    async def test_ic_drift_trigger_no_constitution(self, mock_config):
        """analyze_drift should NOT be called when no active constitution exists."""
        from backend.api.routes.agents import _ic_drift_callback

        callback = _ic_drift_callback(mock_config)
        job = _make_job(job_id="ic-test3", agent="ic_review")

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.behavioral.analyze_drift", new_callable=AsyncMock) as mock_analyze:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_events_by_type.side_effect = lambda event_type, limit=50: (
                [{"event_type": "ic_passed", "ticker": "AAPL"}, {"event_type": "ic_passed", "ticker": "MSFT"}, {"event_type": "ic_passed", "ticker": "GOOG"}]
                if event_type == "ic_passed"
                else []
            )
            mock_db_instance.get_active_constitution.return_value = None

            await callback(job)

            mock_analyze.assert_not_called()
            mock_db_instance.close.assert_called_once()

    async def test_ic_drift_trigger_failure_non_blocking(self, mock_config):
        """If analyze_drift raises, the callback should not propagate the exception."""
        from backend.api.routes.agents import _ic_drift_callback

        callback = _ic_drift_callback(mock_config)
        job = _make_job(job_id="ic-test4", agent="ic_review")

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.behavioral.analyze_drift", new_callable=AsyncMock) as mock_analyze:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_events_by_type.side_effect = lambda event_type, limit=50: (
                [{"event_type": "ic_passed", "ticker": "AAPL"}, {"event_type": "ic_passed", "ticker": "MSFT"}, {"event_type": "ic_passed", "ticker": "GOOG"}]
                if event_type == "ic_passed"
                else []
            )
            mock_db_instance.get_active_constitution.return_value = {"style_identity": "test"}
            mock_analyze.side_effect = RuntimeError("LLM timeout")

            # Should NOT raise — failure is caught and logged
            await callback(job)

    async def test_ic_drift_trigger_no_drift_no_event(self, mock_config):
        """When no drift is detected, no judgment event should be recorded."""
        from backend.api.routes.agents import _ic_drift_callback

        callback = _ic_drift_callback(mock_config)
        job = _make_job(job_id="ic-test5", agent="ic_review")

        no_drift = {
            "has_enough_data": True,
            "decisions_analyzed": 5,
            "signal_drift": [],
            "anti_signal_violations": [],
            "style_drift": [],
            "override_patterns": [],
            "approval_profile": {},
            "summary": "No significant drift detected.",
        }

        with patch("backend.core.db_v2.ScreenerV2DB") as MockDB, \
             patch("backend.learning.behavioral.analyze_drift", new_callable=AsyncMock) as mock_analyze:
            mock_db_instance = MagicMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_events_by_type.side_effect = lambda event_type, limit=50: (
                [{"event_type": "ic_passed", "ticker": "AAPL"}, {"event_type": "ic_passed", "ticker": "MSFT"}, {"event_type": "ic_passed", "ticker": "GOOG"}]
                if event_type == "ic_passed"
                else []
            )
            mock_db_instance.get_active_constitution.return_value = {"style_identity": "test"}
            mock_analyze.return_value = no_drift

            await callback(job)

            mock_analyze.assert_called_once()
            mock_db_instance.record_judgment_event.assert_not_called()
            mock_db_instance.close.assert_called_once()
