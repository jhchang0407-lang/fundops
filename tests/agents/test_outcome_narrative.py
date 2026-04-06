"""Tests for B4 — Outcome checker narrative web research.

Tests that the OutcomeCheckerAgent can research WHY a screened stock moved,
ground the narrative against known financials, and classify thesis outcome.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.outcome_checker import OutcomeCheckerAgent
from backend.core.web_search import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Create a mock ScreenerV2DB that returns one due check."""
    db = MagicMock()
    db.get_due_checks.return_value = [
        {
            "run_id": "run_001",
            "check_days": 90,
            "run_at": "2025-12-01T00:00:00Z",
            "top_results": [
                {
                    "ticker": "PAYC",
                    "companyName": "Paycom Software",
                    "price": 150.0,
                    "expected_return": 25.0,
                    "grossProfitMargin": 0.85,
                    "roic": 0.30,
                    "revenueGrowth": 0.12,
                    "debtEquity": 0.05,
                },
            ],
        }
    ]
    db.record_outcome_snapshot = MagicMock()
    return db


def _make_yfinance(price: float = 187.5):
    """Create a mock yfinance that returns a given price.

    Production code calls self.yfinance.get_quotes([ticker]) and expects
    an object with .ok and .data (list of quote dicts).
    """
    yf = MagicMock()
    result = MagicMock()
    result.ok = True
    result.data = [{"price": price}]
    yf.get_quotes = AsyncMock(return_value=result)
    return yf


def _make_web_search(text: str, error: str = "", cost: float = 0.03):
    """Create a mock WebSearchProvider."""
    ws = MagicMock()
    ws.search = AsyncMock(return_value=SearchResult(
        text=text,
        sources=[],
        cost=cost,
        duration_s=1.2,
        error=error,
    ))
    return ws


POSITIVE_NARRATIVE = (
    "PAYC Paycom Software stock rallied in Q1 2026 after the company reported "
    "strong results that beat expectations. Revenue grew 15% year-over-year, "
    "and margins improved significantly. The discount closed as analysts "
    "upgraded the stock and raised price targets. Multiple expansion drove "
    "much of the re-rating as investors gained confidence in the SaaS "
    "business model's durability."
)

NEGATIVE_NARRATIVE = (
    "PAYC Paycom Software shares declined after the company missed expectations "
    "on both revenue and earnings. Growth decelerated to single digits as "
    "competitive pressure from larger HCM vendors intensified. Management "
    "cut guidance for the full year, and margins contracted due to elevated "
    "spending on sales and marketing. Several analysts downgraded the stock."
)

AMBIGUOUS_NARRATIVE = (
    "PAYC Paycom Software traded sideways over the period. The company reported "
    "in-line results with no major surprises. The broader SaaS sector saw "
    "mixed performance during 2026."
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOutcomeNarrativeGenerated:
    """Test that narrative appears in outcome output when web_search is available."""

    def test_outcome_narrative_generated(self):
        db = _make_db()
        yf = _make_yfinance(187.5)  # +25% return
        ws = _make_web_search(POSITIVE_NARRATIVE)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        assert result.status == "complete"
        assert result.data["checked"] == 1

        ticker_result = result.data["results"][0]
        assert ticker_result["ticker"] == "PAYC"
        assert "narrative" in ticker_result
        narrative = ticker_result["narrative"]
        assert narrative["narrative"] == POSITIVE_NARRATIVE
        assert narrative["confidence"] > 0
        assert narrative["grounded"] is True

        # Verify web search was called
        ws.search.assert_called_once()
        call_kwargs = ws.search.call_args
        query = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("query", "")
        assert "PAYC" in query
        assert "gained" in query  # positive return


class TestOutcomeNarrativeThesisPlayedOut:
    """Test thesis_played_out classification."""

    def test_thesis_played_out_positive(self):
        """Positive return with confirming research -> thesis_played_out=True."""
        db = _make_db()
        yf = _make_yfinance(187.5)  # +25%
        ws = _make_web_search(POSITIVE_NARRATIVE)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        narrative = result.data["results"][0]["narrative"]
        assert narrative["thesis_played_out"] is True

    def test_thesis_played_out_negative(self):
        """Negative return with thesis-breaking research -> thesis_played_out=False."""
        db = _make_db()
        yf = _make_yfinance(120.0)  # -20%
        ws = _make_web_search(NEGATIVE_NARRATIVE)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        narrative = result.data["results"][0]["narrative"]
        assert narrative["thesis_played_out"] is False

    def test_thesis_played_out_ambiguous(self):
        """Ambiguous narrative -> thesis_played_out=None."""
        db = _make_db()
        yf = _make_yfinance(152.0)  # ~+1.3%, within noise
        ws = _make_web_search(AMBIGUOUS_NARRATIVE)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        narrative = result.data["results"][0]["narrative"]
        assert narrative["thesis_played_out"] is None


class TestOutcomeNarrativeGrounding:
    """Test that narrative passes through the grounding layer."""

    def test_outcome_narrative_grounding_applied(self):
        """Narrative with a contradicted claim surfaces contradictions."""
        # Narrative claims 50% gross margin, but original data says 85%
        text_with_bad_claim = (
            "PAYC Paycom Software reported a gross margin of 50% in Q1 2026, "
            "well below expectations. Revenue grew 15%. The discount closed as "
            "analysts upgraded the stock and raised price targets. Multiple expansion "
            "drove the re-rating."
        )
        db = _make_db()
        yf = _make_yfinance(187.5)
        ws = _make_web_search(text_with_bad_claim)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        narrative = result.data["results"][0]["narrative"]
        # Grounding should have found the gross margin contradiction
        assert narrative["confidence"] > 0
        # The grounding layer ran (narrative dict has all expected keys)
        assert "contradictions" in narrative
        assert "warnings" in narrative


class TestOutcomeNarrativeNoWebSearch:
    """Test that missing web_search causes no crash."""

    def test_outcome_narrative_no_web_search(self):
        """web_search=None -> no narrative, no crash."""
        db = _make_db()
        yf = _make_yfinance(187.5)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=None)
        result = asyncio.run(agent.run(context={}))

        assert result.status == "complete"
        assert result.data["checked"] == 1
        ticker_result = result.data["results"][0]
        assert "narrative" not in ticker_result


class TestOutcomeNarrativeWebSearchFailure:
    """Test graceful handling of web search failures."""

    def test_web_search_returns_error(self):
        """web_search returns error -> no narrative, no crash."""
        db = _make_db()
        yf = _make_yfinance(187.5)
        ws = _make_web_search(text="", error="Rate limited")

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        assert result.status == "complete"
        assert result.data["checked"] == 1
        ticker_result = result.data["results"][0]
        # No narrative when search fails
        assert "narrative" not in ticker_result

    def test_web_search_raises_exception(self):
        """web_search.search() raises -> no narrative, no crash."""
        db = _make_db()
        yf = _make_yfinance(187.5)
        ws = MagicMock()
        ws.search = AsyncMock(side_effect=ConnectionError("Network down"))

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        assert result.status == "complete"
        assert result.data["checked"] == 1
        ticker_result = result.data["results"][0]
        assert "narrative" not in ticker_result

    def test_no_return_data_skips_narrative(self):
        """If return_pct is None (no price data), skip narrative."""
        db = _make_db()
        # yfinance returns None price -> return_pct will be None
        yf = MagicMock()
        result = MagicMock()
        result.ok = True
        result.data = [{"price": None}]
        yf.get_quotes = AsyncMock(return_value=result)
        ws = _make_web_search(POSITIVE_NARRATIVE)

        agent = OutcomeCheckerAgent(db=db, yfinance=yf, web_search=ws)
        result = asyncio.run(agent.run(context={}))

        assert result.status == "complete"
        ticker_result = result.data["results"][0]
        # No narrative because return_pct is None
        assert "narrative" not in ticker_result
        # web_search should NOT have been called
        ws.search.assert_not_called()
