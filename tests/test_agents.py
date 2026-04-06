"""Tests for agent implementations."""

import pytest
from backend.agents.screener import ScreenerAgent
from backend.agents.thesis import ThesisAgent
from backend.agents.ic_review import ICReviewAgent
from backend.agents.library import LibraryAgent
from backend.agents.portfolio import PortfolioAgent
from backend.agents.allocator import AllocatorAgent


# --- Screener ---

def test_screener_scoring():
    agent = ScreenerAgent()
    stock = {
        "symbol": "PAYC", "companyName": "Paycom", "sector": "Technology",
        "price": 260, "pe": 22, "marketCap": 15_000_000_000,
        "grossProfitMargin": 0.83, "netProfitMargin": 0.20,
        "returnOnEquity": 0.34, "debtEquity": 0, "revenueGrowth": 0.12,
    }
    result = agent._score_stock(stock, [])
    assert result is not None
    assert result["symbol"] == "PAYC"
    assert result["expected_return"] > 0
    assert result["dislocation_score"] > 0
    assert result["compounder_score"] > 0
    assert result["top_lens"] in ("dislocation", "compounder")


def test_screener_scoring_filters_invalid():
    agent = ScreenerAgent()
    assert agent._score_stock({}, []) is None
    assert agent._score_stock({"symbol": "X", "price": 0}, []) is None


@pytest.mark.asyncio
async def test_screener_empty_universe():
    agent = ScreenerAgent()
    result = await agent.run({})
    assert result.status == "failed"
    assert "Failed to fetch" in result.errors[0]


# --- Thesis ---

def test_thesis_valuation():
    agent = ThesisAgent()
    data = {"price": 260, "pe": 22, "revenue_growth": 0.12}
    val = agent._calculate_valuation("PAYC", data)
    assert val["fair_value_base"] > 0
    assert val["method"] == "growth_adjusted_pe"


@pytest.mark.asyncio
async def test_thesis_no_ticker():
    agent = ThesisAgent()
    result = await agent.run({})
    assert result.status == "failed"
    assert "No ticker" in result.errors[0]


# --- IC Review ---

@pytest.mark.asyncio
async def test_ic_review_pass(mock_llm):
    agent = ICReviewAgent(config={"hurdle_base_pct": 20, "hurdle_bear_pct": 15}, llm=mock_llm)
    context = {
        "ticker": "PAYC",
        "company_name": "Paycom",
        "expected_return": 35.0,
        "discount_pct": 31.0,
        "return_sources": {"discount": 18, "growth": 12, "margin": 5, "dividends": 0},
        "quality": {"gross_margin": 83, "roic": 34, "roe": 34, "debt_equity": 0, "fcf_yield": 5},
        "valuation": {"growth_rate": 12},
        "variant_view": "Beti adoption underpriced",
    }
    result = await agent.run(context)
    assert result.status == "complete"
    assert result.data["verdict"] in ("PASS", "NO_PASS")
    assert result.data["base_return"] == 35.0
    assert result.data["bear_return"] > 0


@pytest.mark.asyncio
async def test_ic_review_nopass_low_bear():
    agent = ICReviewAgent(config={"hurdle_base_pct": 20, "hurdle_bear_pct": 15})
    context = {
        "ticker": "BBY",
        "expected_return": 28.0,
        "discount_pct": 31.0,
        "return_sources": {"discount": 14, "growth": 10, "margin": 4, "dividends": 0},
        "quality": {"gross_margin": 24},
        "valuation": {"growth_rate": 5},
    }
    result = await agent.run(context)
    # With 70% haircut on growth+margin, bear return should be low
    assert result.data["bear_return"] < result.data["base_return"]


# --- Library ---

@pytest.mark.asyncio
async def test_library_no_sources():
    agent = LibraryAgent(config={"memo_sources": []})
    result = await agent.run({})
    assert result.status == "complete"
    # Library always scans judgment events even with empty memo_sources
    assert "ingested" in result.data or "archived" in result.data
    assert "errors" in result.data


# --- Portfolio ---

@pytest.mark.asyncio
async def test_portfolio_no_positions():
    agent = PortfolioAgent()
    result = await agent.run({})
    assert result.status == "complete"
    assert result.data["message"] == "No positions to monitor"


@pytest.mark.asyncio
async def test_portfolio_with_positions():
    agent = PortfolioAgent()
    context = {
        "positions": [
            {"ticker": "PLTR", "shares": 1200, "cost_basis": 6.70, "type": "legacy"},
            {"ticker": "PAYC", "shares": 80, "cost_basis": 245, "type": "core"},
        ]
    }
    result = await agent.run(context)
    assert result.status == "complete"
    holdings = result.data["holdings"]
    assert len(holdings) == 2
    # Without quotes, price falls back to cost_basis
    assert all(h["market_value"] > 0 for h in holdings)


# --- Allocator ---

@pytest.mark.asyncio
async def test_allocator_no_holdings():
    agent = AllocatorAgent()
    result = await agent.run({})
    assert result.status == "complete"
    assert result.data["message"] == "No holdings to analyze"


@pytest.mark.asyncio
async def test_allocator_trim_concentration():
    agent = AllocatorAgent(config={"concentration_limit_pct": 20})
    context = {
        "holdings": [
            {"ticker": "PLTR", "shares": 1200, "weight": 25.7, "market_value": 144000, "pnl_pct": 1697, "type": "legacy"},
            {"ticker": "PAYC", "shares": 80, "weight": 3.3, "market_value": 20800, "pnl_pct": 6, "type": "core"},
        ],
        "alerts": [],
    }
    result = await agent.run(context)
    actions = result.data["actions_required"]
    assert any(a["action"] == "TRIM" and a["ticker"] == "PLTR" for a in actions)
