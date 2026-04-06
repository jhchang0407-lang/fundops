"""Tests for B3 — Outcome checker completion.

Verifies the three gaps are filled:
1. Benchmark return (SPY) is fetched and alpha calculated
2. Thesis integrity scores current vs original fundamentals
3. Goal alignment checks return path vs strategy
"""

import json
import pytest
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.connectors import ConnectorResult

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Create a mock ScreenerV2DB with common stubs."""
    db = MagicMock()
    db.record_outcome_snapshot = MagicMock()
    db.get_active_constitution = MagicMock(return_value=None)
    db.get_due_checks = MagicMock(return_value=[])
    return db


def _make_yfinance():
    """Create a mock yfinance connector."""
    yf = MagicMock()
    yf.get_quotes = AsyncMock()
    return yf


def _make_sec(ratios_data=None, financials_data=None):
    """Create a mock SEC connector returning specified data."""
    sec = MagicMock()

    if ratios_data is not None:
        sec.get_ratios = AsyncMock(return_value=ConnectorResult(
            connector="sec_edgar", capability="key_metrics", data=ratios_data,
        ))
    else:
        sec.get_ratios = AsyncMock(return_value=ConnectorResult(
            connector="sec_edgar", capability="key_metrics", error="No data",
        ))

    if financials_data is not None:
        sec.get_financials = AsyncMock(return_value=ConnectorResult(
            connector="sec_edgar", capability="financials", data=financials_data,
        ))
    else:
        sec.get_financials = AsyncMock(return_value=ConnectorResult(
            connector="sec_edgar", capability="financials", error="No data",
        ))

    return sec


def _make_spy_dataframe(dates_prices: dict):
    """Build a pandas DataFrame mimicking yfinance.download() output.

    dates_prices: {"2025-01-15": 500.0, "2025-04-15": 520.0, ...}
    """
    import pandas as pd
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in dates_prices.keys()])
    df = pd.DataFrame({"Close": list(dates_prices.values())}, index=index)
    return df


def _original_stock(
    ticker="TEST",
    price=100.0,
    gm=0.45,
    roic=0.15,
    growth=0.12,
    de=0.5,
    expected_return=25.0,
    fair_value=130.0,
):
    """Build an original_data dict as the screener would produce."""
    return {
        "ticker": ticker,
        "price": price,
        "grossProfitMargin": gm,
        "roic": roic,
        "revenueGrowth": growth,
        "debtEquity": de,
        "expected_return": expected_return,
        "fairValue": fair_value,
        "companyName": f"{ticker} Corp",
    }


# ---------------------------------------------------------------------------
# Gap 1: Benchmark return tests
# ---------------------------------------------------------------------------

class TestBenchmarkReturn:

    async def test_benchmark_return_calculated(self):
        """Mock yfinance with known SPY prices -> benchmark_return_pct computed."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        spy_df = _make_spy_dataframe({
            "2025-01-13": 490.0,
            "2025-01-14": 495.0,
            "2025-01-15": 500.0,
            "2025-04-14": 518.0,
            "2025-04-15": 520.0,
        })

        yf = _make_yfinance()
        agent = OutcomeCheckerAgent(db=_make_db(), yfinance=yf)

        with patch("yfinance.download", return_value=spy_df):
            result = await agent._fetch_benchmark_return(
                screened_at="2025-01-15T00:00:00+00:00",
                check_at="2025-04-15T00:00:00+00:00",
            )

        assert result is not None
        # SPY: 500 -> 520 = 4.0%
        assert abs(result - 4.0) < 0.1

    async def test_benchmark_return_spy_failure(self):
        """yfinance fails -> benchmark is None, no crash."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        yf = _make_yfinance()
        agent = OutcomeCheckerAgent(db=_make_db(), yfinance=yf)

        with patch("yfinance.download", side_effect=Exception("Network error")):
            result = await agent._fetch_benchmark_return(
                screened_at="2025-01-15T00:00:00+00:00",
                check_at="2025-04-15T00:00:00+00:00",
            )

        assert result is None

    async def test_benchmark_return_no_yfinance(self):
        """No yfinance connector -> benchmark is None."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db(), yfinance=None)
        result = await agent._fetch_benchmark_return(
            screened_at="2025-01-15", check_at="2025-04-15",
        )
        assert result is None

    async def test_benchmark_return_bad_dates(self):
        """Unparseable dates -> None, no crash."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        yf = _make_yfinance()
        agent = OutcomeCheckerAgent(db=_make_db(), yfinance=yf)

        result = await agent._fetch_benchmark_return(
            screened_at="not-a-date", check_at="also-not",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Gap 1 continued: Alpha calculation
# ---------------------------------------------------------------------------

class TestAlphaCalculated:

    async def test_alpha_calculated(self):
        """return_pct - benchmark_return = alpha."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        spy_df = _make_spy_dataframe({
            "2025-01-13": 490.0,
            "2025-01-15": 500.0,
            "2025-04-14": 518.0,
            "2025-04-15": 520.0,
        })

        yf = _make_yfinance()
        # Stock quote: current price 130 (was 100 -> +30%)
        yf.get_quotes.return_value = ConnectorResult(
            connector="yfinance", capability="quotes",
            data=[{"symbol": "TEST", "price": 130.0}],
        )

        db = _make_db()
        agent = OutcomeCheckerAgent(db=db, yfinance=yf)

        with patch("yfinance.download", return_value=spy_df):
            result = await agent._check_ticker(
                ticker="TEST",
                run_id="run-1",
                screened_at="2025-01-15T00:00:00+00:00",
                days_elapsed=90,
                original_data=_original_stock(price=100.0),
            )

        # Stock +30%, SPY +4% -> alpha = 26%
        assert result["return_pct"] == 30.0
        assert result["benchmark_return_pct"] is not None
        assert abs(result["benchmark_return_pct"] - 4.0) < 0.1
        assert result["alpha_pct"] is not None
        assert abs(result["alpha_pct"] - 26.0) < 0.2


# ---------------------------------------------------------------------------
# Gap 2: Thesis integrity tests
# ---------------------------------------------------------------------------

class TestThesisIntegrity:

    async def test_thesis_integrity_all_held(self):
        """Current data matches original -> score ~100."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        sec = _make_sec(ratios_data={
            "grossProfitMargin": 0.45,
            "roic": 0.15,
            "revenueGrowth": 0.12,
            "debtEquity": 0.5,
        })

        agent = OutcomeCheckerAgent(db=_make_db(), sec=sec)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data=_original_stock(),
            days_elapsed=90,
        )

        assert result["score"] is not None
        assert result["score"] == 100
        for check in result["checks"].values():
            assert check["status"] == "held"

    async def test_thesis_integrity_deteriorated(self):
        """Current data much worse -> score < 50."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        # GM dropped 40%, ROIC dropped 50%, growth turned negative, debt doubled
        sec = _make_sec(ratios_data={
            "grossProfitMargin": 0.27,    # was 0.45 -> -40%
            "roic": 0.075,                 # was 0.15 -> -50%
            "revenueGrowth": -0.05,        # was 0.12 -> negative
            "debtEquity": 1.2,             # was 0.5 -> +140%
        })

        agent = OutcomeCheckerAgent(db=_make_db(), sec=sec)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data=_original_stock(),
            days_elapsed=180,
        )

        assert result["score"] is not None
        assert result["score"] < 50
        # Check that at least some metrics show "deteriorated"
        deteriorated_count = sum(
            1 for c in result["checks"].values() if c["status"] == "deteriorated"
        )
        assert deteriorated_count >= 2

    async def test_thesis_integrity_moderate_decline(self):
        """15% decline in metrics -> partial score (between 50 and 100)."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        sec = _make_sec(ratios_data={
            "grossProfitMargin": 0.39,    # was 0.45 -> -13.3% (moderate)
            "roic": 0.13,                  # was 0.15 -> -13.3% (moderate)
            "revenueGrowth": 0.10,         # was 0.12 -> -16.7% (moderate)
            "debtEquity": 0.58,            # was 0.5 -> +16% (moderate, higher is worse)
        })

        agent = OutcomeCheckerAgent(db=_make_db(), sec=sec)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data=_original_stock(),
            days_elapsed=180,
        )

        assert result["score"] is not None
        assert 40 <= result["score"] <= 60  # half credit for moderate declines

    async def test_thesis_integrity_no_sec(self):
        """SEC connector unavailable -> score None, no crash."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db(), sec=None)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data=_original_stock(),
            days_elapsed=90,
        )

        # Without SEC data, all metrics get partial credit (50%)
        assert result["score"] is not None
        assert result["score"] == 50  # 50% of 100 since all get half credit
        for check in result["checks"].values():
            assert check["status"] == "no_current_data"

    async def test_thesis_integrity_sec_failure(self):
        """SEC connector raises exception -> graceful fallback."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        sec = MagicMock()
        sec.get_ratios = AsyncMock(side_effect=Exception("SEC down"))
        sec.get_financials = AsyncMock(side_effect=Exception("SEC down"))

        agent = OutcomeCheckerAgent(db=_make_db(), sec=sec)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data=_original_stock(),
            days_elapsed=90,
        )

        # Should not crash — returns score with partial credit
        assert result["score"] is not None

    async def test_thesis_integrity_no_original_data(self):
        """No original metrics -> score None, empty checks."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db(), sec=None)

        result = await agent._check_thesis_integrity(
            ticker="TEST",
            original_data={"ticker": "TEST", "price": 100.0},
            days_elapsed=90,
        )

        assert result["score"] is None
        assert result["total_weight"] == 0
        assert result["checks"] == {}


# ---------------------------------------------------------------------------
# Gap 3: Goal alignment tests
# ---------------------------------------------------------------------------

class TestGoalAlignment:

    async def test_goal_alignment_on_track(self):
        """Positive return matching expected -> 'aligned'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db())

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=22.0,
            original_data=_original_stock(expected_return=25.0),
            current_price=122.0,
            original_price=100.0,
            thesis_integrity={"score": 90, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["status"] == "aligned"

    async def test_goal_alignment_failed(self):
        """Negative return when positive expected -> 'failed'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db())

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=-15.0,
            original_data=_original_stock(expected_return=25.0),
            current_price=85.0,
            original_price=100.0,
            thesis_integrity={"score": 40, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["status"] == "failed"

    async def test_goal_alignment_no_return_data(self):
        """No return data -> assessed=False."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db())

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=None,
            original_data=_original_stock(),
            current_price=None,
            original_price=100.0,
            thesis_integrity={"score": None, "checks": {}, "total_weight": 0},
        )

        assert result["assessed"] is False
        assert result["status"] == "no_return_data"

    async def test_goal_alignment_value_strategy_discount_closed(self):
        """Value constitution + discount narrowed -> 'aligned'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        db = _make_db()
        db.get_active_constitution.return_value = {
            "id": "c1",
            "style_identity": "deep value, margin of safety",
            "north_star": "Find undervalued quality businesses",
        }

        agent = OutcomeCheckerAgent(db=db)

        # Price moved from 100 to 120, fair value is 130
        # Original discount: (130-100)/130 = 23%
        # Current discount: (130-120)/130 = 7.7% — narrowed
        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=20.0,
            original_data=_original_stock(price=100.0, fair_value=130.0, expected_return=25.0),
            current_price=120.0,
            original_price=100.0,
            thesis_integrity={"score": 85, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["status"] == "aligned"
        assert result["strategy_type"] == "value"
        assert result["discount_closed"] is True

    async def test_goal_alignment_value_no_fair_value(self):
        """Value constitution + no fair value data -> falls back to return vs expected."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        db = _make_db()
        db.get_active_constitution.return_value = {
            "id": "c1",
            "style_identity": "deep value, discount investing",
        }

        agent = OutcomeCheckerAgent(db=db)

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=5.0,
            original_data=_original_stock(price=100.0, fair_value=None, expected_return=25.0),
            current_price=105.0,
            original_price=100.0,
            thesis_integrity={"score": 70, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["strategy_type"] == "value"
        # Positive return with no fair value -> aligned (benefit of the doubt)
        assert result["status"] == "aligned"

    async def test_goal_alignment_compounder_strategy_aligned(self):
        """Compounder constitution + growth maintained -> 'aligned'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        db = _make_db()
        db.get_active_constitution.return_value = {
            "id": "c1",
            "style_identity": "quality compounder",
            "north_star": "Find quality compounders with durable growth",
        }

        agent = OutcomeCheckerAgent(db=db)

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=18.0,
            original_data=_original_stock(expected_return=20.0),
            current_price=118.0,
            original_price=100.0,
            thesis_integrity={"score": 85, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["status"] == "aligned"
        assert result["strategy_type"] == "compounder"
        assert result["thesis_integrity_score"] == 85

    async def test_goal_alignment_compounder_divergent(self):
        """Compounder constitution + growth deteriorated but positive return -> 'divergent'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        db = _make_db()
        db.get_active_constitution.return_value = {
            "id": "c1",
            "style_identity": "quality compounder",
        }

        agent = OutcomeCheckerAgent(db=db)

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=10.0,
            original_data=_original_stock(expected_return=25.0),
            current_price=110.0,
            original_price=100.0,
            thesis_integrity={"score": 40, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        assert result["status"] == "divergent"

    async def test_goal_alignment_general_underperforming(self):
        """No constitution + return well below expected -> 'divergent'."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        agent = OutcomeCheckerAgent(db=_make_db())

        result = await agent._check_goal_alignment(
            ticker="TEST",
            return_pct=5.0,
            original_data=_original_stock(expected_return=30.0),
            current_price=105.0,
            original_price=100.0,
            thesis_integrity={"score": 80, "checks": {}, "total_weight": 100},
        )

        assert result["assessed"] is True
        # 5% vs 30% expected -> well below 70% threshold (21%) -> divergent
        assert result["status"] == "divergent"


# ---------------------------------------------------------------------------
# Strategy classification tests
# ---------------------------------------------------------------------------

class TestStrategyClassification:

    def test_classify_value(self):
        from backend.agents.outcome_checker import _classify_strategy

        assert _classify_strategy({"style_identity": "deep value"}) == "value"
        assert _classify_strategy({"style_identity": "margin of safety"}) == "value"
        assert _classify_strategy({"north_star": "Find undervalued stocks"}) == "value"
        assert _classify_strategy({"style_identity": "sector dislocation"}) == "value"

    def test_classify_compounder(self):
        from backend.agents.outcome_checker import _classify_strategy

        assert _classify_strategy({"style_identity": "quality compounder"}) == "compounder"
        assert _classify_strategy({"north_star": "compound growth"}) == "compounder"

    def test_classify_general(self):
        from backend.agents.outcome_checker import _classify_strategy

        assert _classify_strategy(None) == "general"
        assert _classify_strategy({}) == "general"
        assert _classify_strategy({"style_identity": "something else"}) == "general"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelpers:

    def test_parse_datetime_iso(self):
        from backend.agents.outcome_checker import _parse_datetime

        dt = _parse_datetime("2025-01-15T12:00:00+00:00")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_datetime_date_only(self):
        from backend.agents.outcome_checker import _parse_datetime

        dt = _parse_datetime("2025-01-15")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_datetime_z_suffix(self):
        from backend.agents.outcome_checker import _parse_datetime

        dt = _parse_datetime("2025-01-15T00:00:00Z")
        assert dt is not None

    def test_parse_datetime_none(self):
        from backend.agents.outcome_checker import _parse_datetime

        assert _parse_datetime(None) is None
        assert _parse_datetime("") is None
        assert _parse_datetime("not-a-date") is None

    def test_extract_value(self):
        from backend.agents.outcome_checker import _extract_value

        data = {"a": 1.5, "b": "invalid", "c": 3.0}
        assert _extract_value(data, ["x", "a"]) == 1.5
        assert _extract_value(data, ["x", "y"]) is None
        assert _extract_value(data, ["b", "c"]) == 3.0  # skips invalid "b"
        assert _extract_value({}, ["a"]) is None


# ---------------------------------------------------------------------------
# Integration-style: full _check_ticker with all gaps wired
# ---------------------------------------------------------------------------

class TestCheckTickerIntegration:

    async def test_check_ticker_all_gaps_filled(self):
        """End-to-end: ticker check returns benchmark, integrity, and alignment."""
        from backend.agents.outcome_checker import OutcomeCheckerAgent

        spy_df = _make_spy_dataframe({
            "2025-01-13": 490.0,
            "2025-01-15": 500.0,
            "2025-04-14": 515.0,
            "2025-04-15": 520.0,
        })

        yf = _make_yfinance()
        yf.get_quotes.return_value = ConnectorResult(
            connector="yfinance", capability="quotes",
            data=[{"symbol": "TEST", "price": 120.0}],
        )

        sec = _make_sec(ratios_data={
            "grossProfitMargin": 0.44,
            "roic": 0.14,
            "revenueGrowth": 0.11,
            "debtEquity": 0.52,
        })

        db = _make_db()
        db.get_active_constitution.return_value = {
            "id": "c1",
            "style_identity": "quality-at-a-discount value",
        }

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, sec=sec)

        with patch("yfinance.download", return_value=spy_df):
            result = await agent._check_ticker(
                ticker="TEST",
                run_id="run-1",
                screened_at="2025-01-15T00:00:00+00:00",
                days_elapsed=90,
                original_data=_original_stock(price=100.0),
            )

        # Gap 1: benchmark filled
        assert result["benchmark_return_pct"] is not None
        assert result["alpha_pct"] is not None

        # Gap 2: thesis integrity scored
        assert result["thesis_integrity"]["score"] is not None
        assert result["thesis_integrity"]["score"] > 0

        # Gap 3: goal alignment assessed
        assert result["goal_alignment"]["assessed"] is True
        assert result["goal_alignment"]["status"] in ("aligned", "divergent", "failed")

        # DB was called
        db.record_outcome_snapshot.assert_called_once()
        call_kwargs = db.record_outcome_snapshot.call_args
        # Verify benchmark and alpha were passed
        assert call_kwargs.kwargs.get("benchmark_return_pct") is not None or \
               (len(call_kwargs.args) > 8 and call_kwargs.args[8] is not None)
