"""Tests for E4 — Memo web research grounding integration.

Verifies that fetch_market_intelligence correctly wires up the web grounding
layer (A4) with pre-search fact anchoring and post-search validation.
"""

import asyncio
import types
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeSearchResult:
    """Minimal mock of a web search result."""
    text: str
    cost: float = 0.01
    error: str = ""


SAMPLE_FINANCIAL_DATA = {
    "revenue": 1_800_000_000,
    "revenue_growth": 0.12,
    "gross_margin": 0.72,
    "roic": 0.18,
    "debt_equity": 0.35,
    "fcf_yield": 0.05,
    "price": 145.0,
    "market_cap": 8_500_000_000,
}


def _make_web_search(texts: list[str] | None = None):
    """Build a mock web_search with an async .search() that returns FakeSearchResult.

    If texts is provided, each call returns the next text in order.
    """
    if texts is None:
        texts = [
            "Paycom (PAYC) saw revenue grow 12% in Q3 2025. Stock dropped due to macro fears.",
            "PAYC competes with ADP and Paychex. TAM ~$30B growing 8% CAGR.",
            "Analyst consensus: 10 buy, 5 hold. Price target $160-$200. PAYC buyback $500M in 2025.",
        ]

    call_count = 0

    async def _search(prompt: str, context: dict) -> FakeSearchResult:
        nonlocal call_count
        idx = min(call_count, len(texts) - 1)
        call_count += 1
        return FakeSearchResult(text=texts[idx])

    ws = MagicMock()
    ws.search = _search
    # Store prompts for inspection
    ws._prompts = []
    original_search = ws.search

    async def _tracking_search(prompt: str, context: dict) -> FakeSearchResult:
        ws._prompts.append(prompt)
        return await original_search(prompt, context)

    ws.search = _tracking_search
    return ws


def _run(coro):
    """Helper to run an async function in tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMarketIntelIncludesGrounding:
    """test_market_intel_includes_grounding: With financial_data, output has grounding dict."""

    def test_grounding_present_with_financial_data(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        assert "grounding" in result, "Expected 'grounding' key when financial_data provided"
        grounding = result["grounding"]

        # All 3 queries should have grounding entries
        for key in ("opportunity_risk", "competitive_products", "capital_analyst"):
            assert key in grounding, f"Missing grounding entry for {key}"
            entry = grounding[key]
            assert "confidence" in entry
            assert "recency_score" in entry
            assert "contradictions" in entry
            assert "warnings" in entry
            assert isinstance(entry["confidence"], (int, float))
            assert 0.0 <= entry["confidence"] <= 1.0

    def test_grounding_confidence_is_numeric(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        for key in ("opportunity_risk", "competitive_products", "capital_analyst"):
            conf = result["grounding"][key]["confidence"]
            assert isinstance(conf, (int, float))


class TestMarketIntelGroundingSummary:
    """test_market_intel_grounding_summary: Verify grounding_summary structure."""

    def test_summary_fields(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        assert "grounding_summary" in result
        summary = result["grounding_summary"]

        assert "avg_confidence" in summary
        assert "min_confidence" in summary
        assert "stale_warning" in summary
        assert "total_contradictions" in summary

        assert isinstance(summary["avg_confidence"], (int, float))
        assert isinstance(summary["min_confidence"], (int, float))
        assert isinstance(summary["stale_warning"], bool)
        assert isinstance(summary["total_contradictions"], int)

    def test_summary_min_lte_avg(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        summary = result["grounding_summary"]
        assert summary["min_confidence"] <= summary["avg_confidence"]


class TestMarketIntelNoFinancialData:
    """test_market_intel_no_financial_data: Without financial_data, no grounding, no crash."""

    def test_no_grounding_without_data(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            # financial_data not provided
        ))

        # Core fields still present
        assert result["_available"] is True
        assert result["opportunity_risk"] != ""

        # Grounding fields absent
        assert "grounding" not in result
        assert "grounding_summary" not in result

    def test_backward_compat_output_shape(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
        ))

        # Original fields all present
        for key in ("opportunity_risk", "competitive_products", "capital_analyst",
                     "errors", "elapsed", "cost", "_available"):
            assert key in result, f"Missing expected key: {key}"


class TestMarketIntelStaleWarning:
    """test_market_intel_stale_warning: Stale dates trigger stale_warning = True."""

    def test_stale_dates_trigger_warning(self):
        from backend.memo.market_research import fetch_market_intelligence

        # All texts reference only old dates (2019/2020) to produce stale recency
        stale_texts = [
            "Paycom (PAYC) had revenue growth of 12% back in Q2 2019. Macro headwinds in FY2020.",
            "PAYC competed with ADP in 2019. The TAM was estimated at $20B in January 2020.",
            "Analysts rated PAYC a buy in March 2019. Buybacks totaled $200M in FY2019.",
        ]
        ws = _make_web_search(texts=stale_texts)

        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        assert "grounding_summary" in result
        assert result["grounding_summary"]["stale_warning"] is True

    def test_recent_dates_no_stale_warning(self):
        from backend.memo.market_research import fetch_market_intelligence

        recent_texts = [
            "Paycom (PAYC) reported Q4 2025 results showing 12% revenue growth in January 2026.",
            "PAYC competes with ADP in Q1 2026. TAM ~$30B as of March 2026.",
            "Analysts upgraded PAYC in February 2026. Price target $180.",
        ]
        ws = _make_web_search(texts=recent_texts)

        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        assert "grounding_summary" in result
        assert result["grounding_summary"]["stale_warning"] is False


class TestMarketIntelFactAnchorInPrompts:
    """test_market_intel_fact_anchor_in_prompts: Fact anchor text injected into queries."""

    def test_anchor_in_all_three_prompts(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        # The mock web_search tracks prompts via ws._prompts
        assert len(ws._prompts) == 3, f"Expected 3 search calls, got {len(ws._prompts)}"

        for i, prompt in enumerate(ws._prompts):
            assert "VERIFIED FINANCIALS" in prompt, (
                f"Prompt {i} missing fact anchor. Starts with: {prompt[:100]}"
            )
            assert "Paycom Software (PAYC)" in prompt, (
                f"Prompt {i} missing company identifier in anchor"
            )

    def test_no_anchor_without_financial_data(self):
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()
        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            # No financial_data
        ))

        assert len(ws._prompts) == 3
        for i, prompt in enumerate(ws._prompts):
            assert "VERIFIED FINANCIALS" not in prompt, (
                f"Prompt {i} should NOT have fact anchor without financial_data"
            )


class TestGroundingExceptionHandling:
    """Grounding errors are caught gracefully without breaking the pipeline."""

    def test_grounding_import_error_handled(self):
        """If web_grounding module fails to import during post-search, output still works."""
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search()

        # Patch ground_web_research to raise an exception
        with patch(
            "backend.memo.market_research.ground_web_research",
            side_effect=RuntimeError("grounding module broken"),
            create=True,
        ):
            # Should not raise — grounding failure is logged and skipped
            result = _run(fetch_market_intelligence(
                ticker="PAYC",
                company_name="Paycom Software",
                sector="Technology",
                web_search=ws,
                financial_data=SAMPLE_FINANCIAL_DATA,
            ))

        # Core fields still present
        assert result["_available"] is True
        assert result["opportunity_risk"] != ""

    def test_empty_text_grounding(self):
        """If a search returns empty text, grounding entry shows 0 confidence."""
        from backend.memo.market_research import fetch_market_intelligence

        ws = _make_web_search(texts=[
            "Paycom (PAYC) grew 12% in Q3 2025.",
            "",  # empty result
            "Analyst consensus on PAYC: 10 buy in March 2026.",
        ])

        result = _run(fetch_market_intelligence(
            ticker="PAYC",
            company_name="Paycom Software",
            sector="Technology",
            web_search=ws,
            financial_data=SAMPLE_FINANCIAL_DATA,
        ))

        assert "grounding" in result
        # The empty query should have 0 confidence
        cp_grounding = result["grounding"]["competitive_products"]
        assert cp_grounding["confidence"] == 0.0
        assert "No text to ground" in cp_grounding["warnings"]
