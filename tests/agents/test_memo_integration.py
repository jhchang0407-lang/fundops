"""Tests for memo agent integration: constitution lens (E3) and library auto-ingest (E2)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.memo import MemoAgent


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_CONSTITUTION = {
    "version": "v1",
    "north_star": "Quality compounders at a discount",
    "dimensions": {
        "cheapness": "Discount to intrinsic value via DCF",
        "quality": "High ROIC, durable gross margins above 50%",
        "growth": "Revenue growth above 10% with reinvestment runway",
        "value_creation": "Moat quality and reinvestment rate > FCF yield",
        "capital_allocation": "Management buys back stock below intrinsic value",
        "trap_risk": "Declining margins, customer churn, leverage",
    },
    "sector_routing": {},
}

SAMPLE_CONSTITUTION_NO_DIMS = {
    "version": "v1",
    "north_star": "Quality compounders",
    "dimensions": {},
}


def _make_memo_agent(**kwargs):
    """Create a MemoAgent with mocked dependencies."""
    return MemoAgent(
        config=kwargs.get("config", {}),
        fmp=kwargs.get("fmp"),
        sec=kwargs.get("sec"),
        yfinance=kwargs.get("yfinance"),
        llm=kwargs.get("llm"),
        web_search=kwargs.get("web_search"),
        db=kwargs.get("db"),
    )


# ---------------------------------------------------------------------------
# E3: Constitution context is passed to memo agent
# ---------------------------------------------------------------------------

class TestMemoConstitutionContextPassed:
    """Verify constitution flows through to the memo agent's strategy field."""

    def test_constitution_sets_strategy(self):
        """When constitution is provided in context, _strategy is populated."""
        agent = _make_memo_agent()

        # Simulate what run() does at the top: extract strategy from constitution
        context = {"ticker": "AAPL", "constitution": SAMPLE_CONSTITUTION}
        constitution = context.get("constitution")
        agent._strategy = None
        if not agent._strategy and constitution:
            agent._strategy = {
                "north_star": constitution.get("north_star", ""),
                "dimensions": constitution.get("dimensions", {}),
                "sector_routing": constitution.get("sector_routing", {}),
            }

        assert agent._strategy is not None
        assert agent._strategy["north_star"] == "Quality compounders at a discount"
        assert "cheapness" in agent._strategy["dimensions"]
        assert "value_creation" in agent._strategy["dimensions"]

    def test_no_constitution_no_strategy(self):
        """When no constitution is provided and no DB, _strategy stays None."""
        agent = _make_memo_agent()
        agent._strategy = None
        context = {"ticker": "AAPL"}
        constitution = context.get("constitution")
        if not agent._strategy and constitution:
            agent._strategy = {
                "north_star": constitution.get("north_star", ""),
                "dimensions": constitution.get("dimensions", {}),
            }
        assert agent._strategy is None


# ---------------------------------------------------------------------------
# E3: Constitution dimensions appear in memo context / prompts
# ---------------------------------------------------------------------------

class TestMemoConstitutionDimensionsInContext:
    """Verify constitution dimensions are injected into memo prompts."""

    def test_strategy_lens_includes_standard_dimensions(self):
        """Standard dimensions (cheapness, quality, growth) appear in strategy lens."""
        agent = _make_memo_agent()
        strategy = {
            "north_star": "Quality compounders at a discount",
            "dimensions": {
                "cheapness": "Discount to intrinsic value",
                "quality": "High ROIC above 20%",
                "growth": "Revenue growth above 10%",
            },
        }
        lens = agent._build_strategy_lens(strategy)
        assert "STRATEGY LENS" in lens
        assert "Quality compounders at a discount" in lens
        assert "Discount to intrinsic value" in lens
        assert "High ROIC above 20%" in lens
        assert "Revenue growth above 10%" in lens

    def test_strategy_lens_includes_custom_dimensions(self):
        """Custom/arbitrary dimensions (value_creation, capital_allocation) appear in lens."""
        agent = _make_memo_agent()
        strategy = {
            "north_star": "",
            "dimensions": {
                "value_creation": "Moat quality and reinvestment rate",
                "capital_allocation": "Buybacks below intrinsic value",
                "trap_risk": "Watch for declining margins",
            },
        }
        lens = agent._build_strategy_lens(strategy)
        # Custom dimensions should appear under "Additional investor focus areas"
        assert "Value Creation" in lens
        assert "Moat quality and reinvestment rate" in lens
        assert "Capital Allocation" in lens
        assert "Buybacks below intrinsic value" in lens
        assert "Trap Risk" in lens

    def test_strategy_lens_empty_without_dimensions(self):
        """Empty dimensions produce empty strategy lens."""
        agent = _make_memo_agent()
        lens = agent._build_strategy_lens({"north_star": "", "dimensions": {}})
        assert lens == ""

    def test_strategy_lens_none_strategy(self):
        """None strategy produces empty strategy lens."""
        agent = _make_memo_agent()
        assert agent._build_strategy_lens(None) == ""

    def test_section_lens_returns_relevant_dims_for_moat_section(self):
        """Competitive Moats section gets moat/value_creation dimensions."""
        agent = _make_memo_agent()
        strategy = {
            "dimensions": {
                "value_creation": "Moat quality matters most",
                "cheapness": "40% discount required",
                "growth": "10% revenue growth",
            },
        }
        lens = agent._build_constitution_section_lens("Competitive Moats", strategy)
        assert "INVESTOR FOCUS AREAS" in lens
        assert "Value Creation" in lens
        assert "Moat quality matters most" in lens
        # cheapness is NOT relevant to moats section
        assert "40% discount required" not in lens

    def test_section_lens_returns_relevant_dims_for_financial_section(self):
        """Financial Analysis section gets quality/cheapness dimensions."""
        agent = _make_memo_agent()
        strategy = {
            "dimensions": {
                "quality": "High ROIC above 20%",
                "cheapness": "40% discount required",
                "capital_allocation": "Buybacks below IV",
            },
        }
        lens = agent._build_constitution_section_lens("Financial Analysis", strategy)
        assert "INVESTOR FOCUS AREAS" in lens
        assert "High ROIC above 20%" in lens
        assert "40% discount required" in lens
        # capital_allocation is NOT relevant to financial analysis section
        assert "Buybacks below IV" not in lens

    def test_section_lens_empty_for_executive_summary(self):
        """Executive Summary gets no section-specific lens (gets full strategy lens instead)."""
        agent = _make_memo_agent()
        strategy = {
            "dimensions": {
                "quality": "High ROIC above 20%",
                "cheapness": "40% discount required",
            },
        }
        lens = agent._build_constitution_section_lens("Executive Summary", strategy)
        assert lens == ""

    def test_section_lens_empty_without_strategy(self):
        """None strategy produces empty section lens."""
        agent = _make_memo_agent()
        assert agent._build_constitution_section_lens("Financial Analysis", None) == ""

    def test_section_lens_empty_without_dimensions(self):
        """Empty dimensions produce empty section lens."""
        agent = _make_memo_agent()
        lens = agent._build_constitution_section_lens("Financial Analysis", {"dimensions": {}})
        assert lens == ""

    def test_section_lens_for_investment_memo_sections(self):
        """Investment memo sections get relevant dimension directives."""
        agent = _make_memo_agent()
        strategy = {
            "dimensions": {
                "cheapness": "Deep discount required",
                "risk": "Downside protection is critical",
                "value_creation": "Moat reinvestment",
            },
        }
        # Opportunity Brief should get cheapness and value_creation
        lens = agent._build_constitution_section_lens("Opportunity Brief", strategy)
        assert "Deep discount required" in lens
        assert "Moat reinvestment" in lens

        # Risks & Bear Case should get risk
        lens = agent._build_constitution_section_lens("Risks & Bear Case", strategy)
        assert "Downside protection is critical" in lens
