"""Tests for IC Review D1 (metric schema signal validation) and D2 (library similarity context)."""

import pytest

from backend.agents.ic_review import ICReviewAgent


@pytest.fixture
def agent():
    return ICReviewAgent(config={"ai_review": False})


@pytest.fixture
def quality():
    return {
        "roic": 18.0,
        "gross_margin": 55.0,
        "roe": 22.0,
        "fcf_yield": 0.04,
        "debt_equity": 0.8,
    }


@pytest.fixture
def constitution():
    return {
        "ic_hurdles": {"base_return_pct": 20, "bear_return_pct": 15},
        "must_have_signals": [],
        "anti_signals": [],
    }


# ---------------------------------------------------------------------------
# D1: Scorecard resolves aliases via metric_schema
# ---------------------------------------------------------------------------


def test_scorecard_resolves_aliases(agent, quality, constitution):
    """Signal 'Return on Invested Capital > 15%' should resolve to canonical 'roic'."""
    constitution["must_have_signals"] = ["Return on Invested Capital > 15%"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    assert scorecard["available"] is True
    met = scorecard["signals_met"]
    assert len(met) == 1
    assert met[0]["metric"] == "roic"
    assert met[0]["actual"] == 18.0
    assert met[0]["met"] is True
    assert scorecard["signals_missed"] == []


def test_scorecard_standard_signal(agent, quality, constitution):
    """Signal 'ROIC > 15%' should still work (canonical name is itself an alias)."""
    constitution["must_have_signals"] = ["ROIC > 15%"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    met = scorecard["signals_met"]
    assert len(met) == 1
    assert met[0]["metric"] == "roic"
    assert met[0]["actual"] == 18.0
    assert met[0]["met"] is True


def test_scorecard_signal_missed(agent, quality, constitution):
    """Signal 'ROIC > 25%' should be missed when actual is 18%."""
    constitution["must_have_signals"] = ["ROIC > 25%"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    assert len(scorecard["signals_met"]) == 0
    assert len(scorecard["signals_missed"]) == 1
    assert scorecard["signals_missed"][0]["metric"] == "roic"
    assert scorecard["signals_missed"][0]["met"] is False


def test_scorecard_unknown_signal(agent, quality, constitution):
    """Signal 'magic_metric > 5' should be marked 'unchecked' (no canonical match)."""
    constitution["must_have_signals"] = ["magic_metric > 5"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    met = scorecard["signals_met"]
    assert len(met) == 1
    assert met[0]["actual"] == "N/A"
    assert met[0]["met"] == "unchecked"


def test_scorecard_gross_margin_alias(agent, quality, constitution):
    """Signal 'Gross Margin >= 50%' resolves via display name alias."""
    constitution["must_have_signals"] = ["Gross Margin >= 50%"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    met = scorecard["signals_met"]
    assert len(met) == 1
    assert met[0]["metric"] == "gross_margin"
    assert met[0]["actual"] == 55.0
    assert met[0]["met"] is True


def test_anti_signal_resolved(agent, quality, constitution):
    """Anti-signal 'Debt to Equity > 2' should resolve to 'debt_equity' and not trigger."""
    constitution["anti_signals"] = ["Debt to Equity > 2"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    # D/E is 0.8 which is below 2 — should NOT trigger
    assert scorecard["anti_signals_triggered"] == []


def test_anti_signal_triggered(agent, quality, constitution):
    """Anti-signal triggers when actual exceeds threshold."""
    quality["debt_equity"] = 3.5
    constitution["anti_signals"] = ["Debt to Equity > 2"]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    triggered = scorecard["anti_signals_triggered"]
    assert len(triggered) == 1
    assert triggered[0]["metric"] == "debt_equity"
    assert triggered[0]["actual"] == 3.5


def test_scorecard_multiple_signals(agent, quality, constitution):
    """Multiple signals from different alias forms all resolve correctly."""
    constitution["must_have_signals"] = [
        "ROIC > 15%",
        "Gross Margin >= 50%",
        "Return on Invested Capital > 10%",
    ]
    thesis = {"quality": quality}

    scorecard = agent._build_constitution_scorecard(thesis, constitution)

    # All three should be met (roic=18 > 15, gm=55 >= 50, roic=18 > 10)
    assert len(scorecard["signals_met"]) == 3
    assert len(scorecard["signals_missed"]) == 0


def test_no_constitution_returns_unavailable(agent, quality):
    """No constitution → scorecard unavailable."""
    thesis = {"quality": quality}
    scorecard = agent._build_constitution_scorecard(thesis, None)
    assert scorecard["available"] is False


# ---------------------------------------------------------------------------
# D1: Helper methods
# ---------------------------------------------------------------------------


def test_extract_metric_standard():
    """Extract metric from 'ROIC > 15%'."""
    assert ICReviewAgent._extract_metric_from_signal("ROIC > 15%") == "ROIC"


def test_extract_metric_display_name():
    """Extract metric from 'Return on Invested Capital > 15%'."""
    result = ICReviewAgent._extract_metric_from_signal("Return on Invested Capital > 15%")
    assert result == "Return on Invested Capital"


def test_extract_metric_positive():
    """Extract metric from 'FCF positive'."""
    assert ICReviewAgent._extract_metric_from_signal("FCF positive") == "FCF"


def test_extract_metric_gte():
    """Extract metric from 'Gross Margin >= 50%'."""
    assert ICReviewAgent._extract_metric_from_signal("Gross Margin >= 50%") == "Gross Margin"


def test_extract_metric_debt():
    """Extract metric from 'Debt to Equity > 2'."""
    assert ICReviewAgent._extract_metric_from_signal("Debt to Equity > 2") == "Debt to Equity"


# ---------------------------------------------------------------------------
# D2: Library similarity context in IC review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ic_similar_research_in_output():
    """When library returns similar entries, they appear in result_data."""

    class FakeLibrary:
        async def find_similar(self, **kwargs):
            return [
                {"ticker": "MSFT", "verdict": "PASS", "expected_return": 22.5, "entry_type": "ic_verdict"},
                {"ticker": "ORCL", "verdict": "NO_PASS", "expected_return": 12.0, "entry_type": "ic_verdict"},
            ]

    agent = ICReviewAgent(config={"ai_review": False}, library=FakeLibrary())

    context = {
        "ticker": "GOOG",
        "thesis": {
            "ticker": "GOOG",
            "company_name": "Alphabet",
            "sector": "Technology",
            "price": 150.0,
            "fair_value": 200.0,
            "discount_pct": 25.0,
            "expected_return": 25.0,
            "quality": {"gross_margin": 55.0, "roic": 20.0, "roe": 25.0, "debt_equity": 0.1},
            "valuation": {"growth_rate": 12.0},
            "return_sources": {"discount": 10.0, "growth": 8.0, "margin": 5.0, "dividends": 2.0},
        },
    }

    result = await agent.run(context)

    assert result.ok
    similar = result.data.get("similar_research", [])
    assert len(similar) == 2
    assert similar[0]["ticker"] == "MSFT"
    assert similar[1]["ticker"] == "ORCL"


@pytest.mark.asyncio
async def test_ic_no_library_no_crash():
    """library=None should not crash the agent."""
    agent = ICReviewAgent(config={"ai_review": False}, library=None)

    context = {
        "ticker": "GOOG",
        "thesis": {
            "ticker": "GOOG",
            "company_name": "Alphabet",
            "sector": "Technology",
            "price": 150.0,
            "fair_value": 200.0,
            "discount_pct": 25.0,
            "expected_return": 25.0,
            "quality": {"gross_margin": 55.0, "roic": 20.0, "roe": 25.0, "debt_equity": 0.1},
            "valuation": {"growth_rate": 12.0},
            "return_sources": {"discount": 10.0, "growth": 8.0, "margin": 5.0, "dividends": 2.0},
        },
    }

    result = await agent.run(context)

    assert result.ok
    assert result.data.get("similar_research") == []


@pytest.mark.asyncio
async def test_ic_library_error_no_crash():
    """Library that raises should not crash the agent."""

    class BrokenLibrary:
        async def find_similar(self, **kwargs):
            raise RuntimeError("DB connection failed")

    agent = ICReviewAgent(config={"ai_review": False}, library=BrokenLibrary())

    context = {
        "ticker": "GOOG",
        "thesis": {
            "ticker": "GOOG",
            "company_name": "Alphabet",
            "sector": "Technology",
            "price": 150.0,
            "fair_value": 200.0,
            "discount_pct": 25.0,
            "expected_return": 25.0,
            "quality": {"gross_margin": 55.0, "roic": 20.0, "roe": 25.0, "debt_equity": 0.1},
            "valuation": {"growth_rate": 12.0},
            "return_sources": {"discount": 10.0, "growth": 8.0, "margin": 5.0, "dividends": 2.0},
        },
    }

    result = await agent.run(context)

    assert result.ok
    assert result.data.get("similar_research") == []
