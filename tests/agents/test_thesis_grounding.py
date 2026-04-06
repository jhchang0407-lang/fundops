"""Tests for thesis agent web research grounding integration (C4)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field

from backend.agents.thesis import ThesisAgent
from backend.core.web_search import SearchResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_DATA = {
    "ticker": "PAYC",
    "company_name": "Paycom Software",
    "sector": "Technology",
    "industry": "Software - Application",
    "price": 150.0,
    "market_cap": 9_000_000_000,
    "revenue_growth": 0.12,
    "gross_margin": 0.85,
    "roic": 0.30,
    "roe": 0.25,
    "debt_equity": 0.1,
    "fcf_yield": 0.04,
    "dividend_yield": 0.007,
    "operating_margin": 0.25,
    "net_margin": 0.20,
    "pe": 25.0,
}

# Text that is clearly about PAYC with recent dates and correct numbers
GOOD_WHY_CHEAP_TEXT = (
    "Paycom Software (PAYC) has seen its stock decline 20% from 52-week highs "
    "as of Q1 2026 due to concerns about slowing revenue growth in the HCM space. "
    "Revenue grew 12% year-over-year in Q4 2025, down from 25% growth in prior years. "
    "Gross margin remains strong at 85%. The company trades at 25x earnings, "
    "a discount to peers like ADP and Paychex. CEO Chad Richison has been buying shares."
)

GOOD_BULL_CASE_TEXT = (
    "The bull case for Paycom Software (PAYC) centers on its Beti product, "
    "which automates payroll processing. In March 2026, management raised guidance "
    "for FY2026. ROIC of 30% is best-in-class for the HCM industry. "
    "Revenue growth of 12% with gross margin of 85% suggests durable competitive advantages. "
    "The company has minimal debt (D/E of 0.1) and generates strong free cash flow."
)

# Text about a WRONG company to trigger low confidence
WRONG_COMPANY_TEXT = (
    "Amazon (AMZN) reported strong Q4 2025 earnings with AWS revenue growing 35%. "
    "The company's market cap exceeded $2 trillion. Amazon (AMZN) continues to "
    "dominate e-commerce with 38% market share. CEO Andy Jassy outlined plans for "
    "Amazon (AMZN) to expand its AI infrastructure in January 2026."
)


def _make_search_result(text: str, cost: float = 0.01) -> SearchResult:
    return SearchResult(text=text, cost=cost, duration_s=0.5)


def _make_agent(search_results: list[SearchResult] | None = None) -> ThesisAgent:
    """Create a ThesisAgent with mocked web_search returning given results in order."""
    web_search = AsyncMock()
    if search_results is not None:
        web_search.search = AsyncMock(side_effect=search_results)
    else:
        web_search.search = AsyncMock(return_value=_make_search_result(""))
    agent = ThesisAgent(
        config={"web_search": True},
        web_search=web_search,
    )
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_thesis_web_research_includes_grounding():
    """After web research, output must contain why_cheap_grounding and bull_case_grounding dicts."""
    agent = _make_agent([
        _make_search_result(GOOD_WHY_CHEAP_TEXT),
        _make_search_result(GOOD_BULL_CASE_TEXT),
    ])

    results = await agent._run_web_research("PAYC", SAMPLE_DATA)

    # Grounding dicts must exist
    assert "why_cheap_grounding" in results, "Missing why_cheap_grounding"
    assert "bull_case_grounding" in results, "Missing bull_case_grounding"

    # Check structure of grounding dicts
    for key in ("why_cheap_grounding", "bull_case_grounding"):
        g = results[key]
        assert "confidence" in g
        assert "recency_score" in g
        assert "contradictions" in g
        assert "warnings" in g
        assert "entity_confidence" in g
        assert "claims_confirmed" in g
        assert "claims_contradicted" in g
        assert isinstance(g["confidence"], float)
        assert isinstance(g["claims_confirmed"], int)
        assert isinstance(g["claims_contradicted"], int)

    # Good text about PAYC should have reasonable confidence
    assert results["why_cheap_grounding"]["confidence"] >= 0.4
    assert results["bull_case_grounding"]["confidence"] >= 0.4

    # Raw text still present
    assert results["why_cheap"] == GOOD_WHY_CHEAP_TEXT
    assert results["bull_case"] == GOOD_BULL_CASE_TEXT


@pytest.mark.asyncio
async def test_thesis_fact_anchor_injected():
    """Search queries must contain fact anchor text (revenue, margin data from SEC/FMP)."""
    agent = _make_agent([
        _make_search_result(GOOD_WHY_CHEAP_TEXT),
        _make_search_result(GOOD_BULL_CASE_TEXT),
    ])

    await agent._run_web_research("PAYC", SAMPLE_DATA)

    # web_search.search should have been called at least twice (why_cheap + bull_case)
    assert agent.web_search.search.call_count >= 2

    # First call = why_cheap query
    why_cheap_call = agent.web_search.search.call_args_list[0]
    query = why_cheap_call.kwargs.get("query") or why_cheap_call.args[0]

    # Fact anchor should include verified financials from SAMPLE_DATA
    assert "VERIFIED FINANCIALS" in query, "Fact anchor not injected into why_cheap query"
    assert "Paycom Software" in query
    assert "PAYC" in query
    # Check that at least one financial metric appears
    assert "Gross margin" in query or "Revenue growth" in query or "ROIC" in query

    # Second call = bull_case query
    bull_call = agent.web_search.search.call_args_list[1]
    bull_query = bull_call.kwargs.get("query") or bull_call.args[0]
    assert "VERIFIED FINANCIALS" in bull_query, "Fact anchor not injected into bull_case query"


@pytest.mark.asyncio
async def test_thesis_grounding_low_confidence_retry():
    """When initial search returns wrong-company text, a retry should be attempted."""
    # First call (why_cheap) returns wrong company text -> low confidence -> retry
    # Retry returns good text -> higher confidence
    # Third call (bull_case) returns good text
    # Fourth call would be bull retry but shouldn't happen (good confidence)
    agent = _make_agent([
        _make_search_result(WRONG_COMPANY_TEXT),       # why_cheap initial (low confidence)
        _make_search_result(GOOD_WHY_CHEAP_TEXT),      # why_cheap retry (better)
        _make_search_result(GOOD_BULL_CASE_TEXT),      # bull_case initial (good)
    ])

    results = await agent._run_web_research("PAYC", SAMPLE_DATA)

    # Should have called search 3 times: why_cheap + retry + bull_case
    assert agent.web_search.search.call_count == 3, (
        f"Expected 3 search calls (initial + retry + bull), got {agent.web_search.search.call_count}"
    )

    # The retry query (2nd call) should be the tighter query with industry/sector
    retry_call = agent.web_search.search.call_args_list[1]
    retry_query = retry_call.kwargs.get("query") or retry_call.args[0]
    assert "Software - Application" in retry_query or "Technology" in retry_query, (
        "Retry query should include industry/sector for specificity"
    )

    # After retry, why_cheap should contain the good text (not the wrong company text)
    assert results["why_cheap"] == GOOD_WHY_CHEAP_TEXT

    # Grounding should reflect the better retry confidence
    assert results["why_cheap_grounding"]["confidence"] >= 0.4


@pytest.mark.asyncio
async def test_thesis_grounding_no_block():
    """Even with confidence < 0.4 on both attempts, thesis still returns web_research (not empty)."""
    # Both initial and retry return wrong company text
    agent = _make_agent([
        _make_search_result(WRONG_COMPANY_TEXT),       # why_cheap initial
        _make_search_result(WRONG_COMPANY_TEXT),       # why_cheap retry (still wrong)
        _make_search_result(WRONG_COMPANY_TEXT),       # bull_case initial
        _make_search_result(WRONG_COMPANY_TEXT),       # bull_case retry (still wrong)
    ])

    results = await agent._run_web_research("PAYC", SAMPLE_DATA)

    # Results must still have text — grounding is advisory, not blocking
    assert "why_cheap" in results
    assert len(results["why_cheap"]) > 0, "why_cheap should not be empty even with low confidence"
    assert "bull_case" in results
    assert len(results["bull_case"]) > 0

    # Low confidence warnings should be present
    assert "why_cheap_warning" in results
    assert "LOW CONFIDENCE" in results["why_cheap_warning"]
    assert "bull_case_warning" in results
    assert "LOW CONFIDENCE" in results["bull_case_warning"]

    # Grounding metadata should still be present
    assert "why_cheap_grounding" in results
    assert "bull_case_grounding" in results
    assert results["why_cheap_grounding"]["confidence"] < 0.4
    assert results["bull_case_grounding"]["confidence"] < 0.4


@pytest.mark.asyncio
async def test_thesis_no_web_search_skips_grounding():
    """When web_search is None, grounding fields should be absent (no crash)."""
    agent = ThesisAgent(
        config={"web_search": True},
        web_search=None,  # No web search provider
    )

    # The run() method checks `self.web_search` before calling _run_web_research.
    # Simulate by calling run() with a minimal context — it should skip web research entirely.
    # We need to mock _fetch_data and _calculate_valuation since we have no connectors.
    agent._fetch_data = AsyncMock(return_value=SAMPLE_DATA)

    result = await agent.run({"ticker": "PAYC"})

    # Should succeed (thesis can be generated without web research)
    assert result.status == "complete"

    # web_research should be empty dict — no grounding fields
    web_research = result.data.get("web_research", {})
    assert "why_cheap_grounding" not in web_research
    assert "bull_case_grounding" not in web_research
    # No crash — that's the main assertion


# ---------------------------------------------------------------------------
# C2 — Library similarity context in Thesis
# ---------------------------------------------------------------------------

SAMPLE_SIMILAR_ENTRIES = [
    {
        "ticker": "ADP",
        "verdict": "PASS",
        "expected_return": 22.5,
        "entry_type": "ic_verdict",
        "conviction": 3,
        "sector": "Technology",
        "gross_margin": 48.0,
        "roic": 28.0,
    },
    {
        "ticker": "PAYX",
        "verdict": "FAIL",
        "expected_return": 12.0,
        "entry_type": "thesis",
        "conviction": 1,
        "sector": "Technology",
        "gross_margin": 62.0,
        "roic": 40.0,
    },
]


@pytest.mark.asyncio
async def test_thesis_similar_research_included():
    """When library is provided, thesis output includes similar_research list."""
    mock_library = AsyncMock()
    mock_library.find_similar = AsyncMock(return_value=SAMPLE_SIMILAR_ENTRIES)

    agent = ThesisAgent(
        config={"web_search": False},
        library=mock_library,
    )
    agent._fetch_data = AsyncMock(return_value=SAMPLE_DATA)

    result = await agent.run({"ticker": "PAYC"})

    assert result.status == "complete"
    similar = result.data.get("similar_research")
    assert similar is not None, "similar_research missing from thesis output"
    assert len(similar) == 2

    # Check structure of each entry
    assert similar[0]["ticker"] == "ADP"
    assert similar[0]["verdict"] == "PASS"
    assert similar[0]["expected_return"] == 22.5
    assert similar[0]["entry_type"] == "ic_verdict"
    assert similar[0]["conviction"] == 3

    assert similar[1]["ticker"] == "PAYX"
    assert similar[1]["verdict"] == "FAIL"

    # Library.find_similar should have been called with correct args
    mock_library.find_similar.assert_awaited_once_with(
        ticker="PAYC",
        sector="Technology",
        gross_margin=0.85,
        roic=0.30,
        top_k=5,
    )


@pytest.mark.asyncio
async def test_thesis_no_library_no_crash():
    """When library=None, thesis still works and similar_research is empty list."""
    agent = ThesisAgent(
        config={"web_search": False},
        library=None,
    )
    agent._fetch_data = AsyncMock(return_value=SAMPLE_DATA)

    result = await agent.run({"ticker": "PAYC"})

    assert result.status == "complete"
    similar = result.data.get("similar_research")
    assert similar is not None, "similar_research key should exist even without library"
    assert similar == [], "similar_research should be empty list when no library"
