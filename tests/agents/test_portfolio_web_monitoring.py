"""Tests for portfolio agent web research thesis monitoring (F3)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.portfolio import PortfolioAgent
from backend.core.web_search import SearchResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_position(
    ticker: str = "PAYC",
    shares: float = 100,
    cost_basis: float = 140.0,
    company_name: str = "Paycom Software",
    key_assumptions: list[str] | None = None,
    financial_data: dict | None = None,
    pos_type: str = "core",
) -> dict:
    """Build a position dict for test context."""
    return {
        "ticker": ticker,
        "shares": shares,
        "cost_basis": cost_basis,
        "company_name": company_name,
        "key_assumptions": key_assumptions or [],
        "financial_data": financial_data or {
            "revenue_growth": 0.12,
            "gross_margin": 0.85,
            "roic": 0.30,
            "price": 150.0,
            "market_cap": 9_000_000_000,
        },
        "type": pos_type,
    }


def _make_quote_source(prices: dict[str, float]):
    """Build a mock quote source that returns prices."""
    source = AsyncMock()
    result = MagicMock()
    result.ok = True
    result.data = [{"symbol": t, "price": p} for t, p in prices.items()]
    source.get_quotes = AsyncMock(return_value=result)
    return source


def _make_web_search(responses: dict[str, str] | None = None, error: str = ""):
    """Build a mock WebSearchProvider.

    Args:
        responses: Map of substring → response text. If the query contains
            the substring, that response is returned. If None, returns a
            default intact response.
        error: If set, all searches return this error.
    """
    ws = AsyncMock()

    async def _search(query: str, context=None):
        if error:
            return SearchResult(text="", error=error)
        if responses:
            for key, text in responses.items():
                if key.lower() in query.lower():
                    return SearchResult(text=text, cost=0.01)
        # Default response
        return SearchResult(
            text=(
                "Paycom Software (PAYC) continues to execute well in Q1 2026. "
                "Revenue growth remains on track at 12%. Gross margin confirmed at 85%. "
                "The company reaffirmed guidance and maintained its competitive position."
            ),
            cost=0.01,
        )

    ws.search = AsyncMock(side_effect=_search)
    return ws


# Breach text — signals that a thesis assumption has been challenged
BREACH_TEXT = (
    "Paycom Software (PAYC) reported disappointing Q1 2026 results. "
    "Revenue growth declined to 5%, well below the 12% consensus. "
    "Management warned of increased churn in the mid-market segment. "
    "The company's gross margin deteriorated from 85% to 78%. "
    "Multiple analysts downgraded the stock, citing challenged growth assumptions. "
    "CEO Chad Richison acknowledged that Beti adoption has fell short of targets."
)

# Intact text — thesis assumptions are holding
INTACT_TEXT = (
    "Paycom Software (PAYC) delivered strong Q1 2026 results. "
    "Revenue grew 14% year-over-year, consistent with prior guidance. "
    "Gross margin remained strong at 85%, reaffirmed by management. "
    "Beti adoption improved and the company maintained its competitive position. "
    "The thesis on track — growth confirmed, margin maintained, ROIC on target."
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPortfolioWebMonitoring:
    """Tests for _check_thesis_events and its integration into run()."""

    @pytest.mark.asyncio
    async def test_thesis_events_checked_weekly(self):
        """weekly=True + web_search available -> thesis events returned."""
        ws = _make_web_search()
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        assert "thesis_events" in result.data
        assert "PAYC" in result.data["thesis_events"]
        events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert len(events) == 1
        assert events[0]["assumption"] == "Revenue growth stays above 10%"
        assert events[0]["status"] in ("intact", "breach", "unconfirmed")
        # web_search.search should have been called
        ws.search.assert_called()

    @pytest.mark.asyncio
    async def test_thesis_events_run_without_weekly_flag(self):
        """weekly=False -> thesis events still run (weekly gate removed)."""
        ws = _make_web_search()
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": False})

        assert result.ok
        # Thesis events now run on every call (weekly gate removed)
        assert "thesis_events" in result.data
        ws.search.assert_called()

    @pytest.mark.asyncio
    async def test_thesis_events_run_default_context(self):
        """No weekly key in context -> thesis events still run."""
        ws = _make_web_search()
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions})

        assert result.ok
        # Thesis events run on every call
        assert "thesis_events" in result.data
        ws.search.assert_called()

    @pytest.mark.asyncio
    async def test_thesis_events_no_web_search(self):
        """web_search=None -> no thesis events, no crash."""
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=None)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        # Should not crash even with weekly=True and no web_search
        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        assert "thesis_events" not in result.data

    @pytest.mark.asyncio
    async def test_thesis_event_negative_signal_monitoring(self):
        """Web research with negative signal -> 'monitoring' status (single signal, no escalation).

        Web search alone NEVER sets 'breach'. First negative signal gets 'monitoring'.
        Only 2+ corroborated signals escalate to 'at_risk'.
        """
        ws = _make_web_search(responses={
            "revenue growth": BREACH_TEXT,
        })
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        # Single web signal -> monitoring, not breach/at_risk, so no alert
        events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert len(events) == 1
        assert events[0]["status"] == "monitoring"
        assert events[0]["signal_direction"] == "negative"
        # No thesis_event_at_risk alert for single signals
        at_risk_alerts = [
            a for a in result.data["alerts"]
            if a["type"] == "thesis_event_at_risk"
        ]
        assert len(at_risk_alerts) == 0

    @pytest.mark.asyncio
    async def test_thesis_event_intact_no_alert(self):
        """Web research confirms thesis -> no breach alert."""
        ws = _make_web_search(responses={
            "revenue growth": INTACT_TEXT,
        })
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        at_risk_alerts = [
            a for a in result.data["alerts"]
            if a["type"] == "thesis_event_at_risk"
        ]
        assert len(at_risk_alerts) == 0
        # Thesis events should still be recorded
        events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert events[0]["status"] == "intact"

    @pytest.mark.asyncio
    async def test_thesis_events_max_assumptions(self):
        """5 assumptions -> only first 3 checked (cost management cap)."""
        call_count = 0
        ws = AsyncMock()

        async def _search(query, context=None):
            nonlocal call_count
            call_count += 1
            return SearchResult(
                text=(
                    "Paycom Software (PAYC) results in Q1 2026 are consistent. "
                    "Growth confirmed and margin maintained. Thesis intact and supported."
                ),
                cost=0.01,
            )

        ws.search = AsyncMock(side_effect=_search)
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=[
                    "Revenue growth stays above 10%",
                    "Gross margin stays above 80%",
                    "Beti adoption continues",
                    "No major competitor disruption",
                    "ROIC stays above 25%",
                ],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        # Only 3 assumptions should have been checked
        events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert len(events) == 3
        assert call_count == 3
        # Verify it was the first 3
        assert events[0]["assumption"] == "Revenue growth stays above 10%"
        assert events[1]["assumption"] == "Gross margin stays above 80%"
        assert events[2]["assumption"] == "Beti adoption continues"

    @pytest.mark.asyncio
    async def test_thesis_events_search_failure(self):
        """Web search fails for one position -> other positions still checked."""
        call_count = 0
        ws = AsyncMock()

        async def _search(query, context=None):
            nonlocal call_count
            call_count += 1
            ticker = (context or {}).get("ticker", "")
            if ticker == "FAIL":
                raise ConnectionError("API timeout")
            return SearchResult(
                text=(
                    "Paycom Software (PAYC) Q1 2026 results confirmed growth. "
                    "Revenue maintained at 12% growth. Thesis intact and on track."
                ),
                cost=0.01,
            )

        ws.search = AsyncMock(side_effect=_search)
        quotes = _make_quote_source({"PAYC": 150.0, "FAIL": 50.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                ticker="FAIL",
                company_name="FailCorp",
                key_assumptions=["Should fail gracefully"],
            ),
            _make_position(
                ticker="PAYC",
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        # FAIL should have empty events (graceful failure)
        assert "FAIL" in result.data["thesis_events"]
        fail_events = result.data["thesis_events"]["FAIL"]["thesis_events"]
        assert len(fail_events) == 1
        assert fail_events[0]["status"] == "unconfirmed"
        assert "failed" in fail_events[0]["finding"].lower() or "Search failed" in fail_events[0]["finding"]
        # PAYC should still have been checked successfully
        assert "PAYC" in result.data["thesis_events"]
        payc_events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert len(payc_events) == 1
        assert payc_events[0]["status"] in ("intact", "unconfirmed")

    @pytest.mark.asyncio
    async def test_thesis_events_web_search_returns_error(self):
        """Web search returns error result -> unconfirmed status, no crash."""
        ws = _make_web_search(error="Rate limit exceeded")
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                key_assumptions=["Revenue growth stays above 10%"],
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        events = result.data["thesis_events"]["PAYC"]["thesis_events"]
        assert len(events) == 1
        assert events[0]["status"] == "unconfirmed"
        assert events[0]["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_no_thesis_events_without_key_assumptions(self):
        """Position with no key_assumptions -> skipped entirely."""
        ws = _make_web_search()
        quotes = _make_quote_source({"PAYC": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(key_assumptions=[]),  # No assumptions
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        # No thesis events since no assumptions to check
        assert "thesis_events" not in result.data
        ws.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_thesis_events_directly(self):
        """Direct unit test of _check_thesis_events method.

        With the three-tier system:
        - Negative web signal (single) -> 'monitoring' (not breach)
        - Positive web signal -> 'intact'
        - Web search alone NEVER sets 'breach'
        """
        call_idx = 0
        ws = AsyncMock()

        async def _search(query, context=None):
            nonlocal call_idx
            call_idx += 1
            # First call: negative text, second call: intact text
            if call_idx == 1:
                return SearchResult(text=BREACH_TEXT, cost=0.01)
            return SearchResult(text=INTACT_TEXT, cost=0.01)

        ws.search = AsyncMock(side_effect=_search)
        agent = PortfolioAgent(web_search=ws)

        result = await agent._check_thesis_events(
            ticker="PAYC",
            company_name="Paycom Software",
            key_assumptions=[
                "Revenue growth stays above 10%",
                "Gross margin stays above 80%",
            ],
            financial_data={
                "revenue_growth": 0.12,
                "gross_margin": 0.85,
                "price": 150.0,
            },
        )

        assert "thesis_events" in result
        assert "any_at_risk" in result
        assert len(result["thesis_events"]) == 2
        # First assumption: negative signal but single hit -> "monitoring" (not breach)
        assert result["thesis_events"][0]["status"] == "monitoring"
        assert result["thesis_events"][0]["signal_direction"] == "negative"
        # Second assumption should be intact (INTACT_TEXT)
        assert result["thesis_events"][1]["status"] == "intact"
        assert result["thesis_events"][1]["signal_direction"] == "positive"
        # No at_risk because no corroboration (single signal)
        assert result["any_at_risk"] is False

    @pytest.mark.asyncio
    async def test_multiple_positions_negative_signals(self):
        """Multiple positions, some with negative signals -> monitoring, not breach.

        With the three-tier system, single negative web signals produce
        'monitoring' status. No breach alerts from web alone.
        """
        ws = AsyncMock()

        async def _search(query, context=None):
            ticker = (context or {}).get("ticker", "")
            if ticker == "BAD":
                return SearchResult(text=BREACH_TEXT, cost=0.01)
            return SearchResult(text=INTACT_TEXT, cost=0.01)

        ws.search = AsyncMock(side_effect=_search)
        quotes = _make_quote_source({"BAD": 40.0, "GOOD": 150.0})
        agent = PortfolioAgent(fmp=quotes, web_search=ws)

        positions = [
            _make_position(
                ticker="BAD",
                company_name="BadCorp",
                key_assumptions=["Revenue growth stays above 10%"],
                financial_data={"revenue_growth": 0.12, "price": 40.0},
            ),
            _make_position(
                ticker="GOOD",
                company_name="GoodCorp",
                key_assumptions=["Margins stable"],
                financial_data={"gross_margin": 0.85, "price": 150.0},
            ),
        ]

        result = await agent.run({"positions": positions, "weekly": True})

        assert result.ok
        # BAD should have monitoring status (single negative signal, no corroboration)
        bad_events = result.data["thesis_events"]["BAD"]["thesis_events"]
        assert bad_events[0]["status"] == "monitoring"
        assert bad_events[0]["signal_direction"] == "negative"
        # GOOD should be intact
        good_events = result.data["thesis_events"]["GOOD"]["thesis_events"]
        assert good_events[0]["status"] == "intact"
        # No at_risk alerts since no corroboration
        at_risk_alerts = [
            a for a in result.data["alerts"]
            if a["type"] == "thesis_event_at_risk"
        ]
        assert len(at_risk_alerts) == 0
