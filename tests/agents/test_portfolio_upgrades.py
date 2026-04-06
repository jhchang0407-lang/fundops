"""Tests for Portfolio F1 (SEC thesis health checks) and F2 (exit → learning feedback)."""

import asyncio
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from backend.agents.portfolio import PortfolioAgent, _parse_assumption


# ---------------------------------------------------------------------------
# Helpers / Mocks
# ---------------------------------------------------------------------------

@dataclass
class FakeConnectorResult:
    """Mimics ConnectorResult for SEC connector mocks."""
    connector: str = "sec_edgar"
    capability: str = "key_metrics"
    data: dict | list = field(default_factory=dict)
    error: str | None = None
    duration_s: float = 0.01

    @property
    def ok(self) -> bool:
        return self.error is None


class FakeSEC:
    """Minimal SEC connector mock that returns canned ratios."""

    def __init__(self, ratios: list[dict] | None = None, error: str | None = None):
        self._ratios = ratios
        self._error = error

    async def get_ratios(self, ticker: str) -> FakeConnectorResult:
        if self._error:
            return FakeConnectorResult(error=self._error)
        return FakeConnectorResult(data=self._ratios or [])


class FakeQuoteSource:
    """Minimal quote source mock."""

    def __init__(self, prices: dict[str, float]):
        self._prices = prices

    async def get_quotes(self, tickers: list[str]) -> FakeConnectorResult:
        data = [{"symbol": t, "price": self._prices.get(t, 100)} for t in tickers]
        return FakeConnectorResult(data=data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sec_ratios_healthy():
    """SEC ratios where all metrics are above typical thresholds."""
    return [{
        "date": "2025-12-31",
        "grossProfitMargin": 0.65,
        "operatingProfitMargin": 0.30,
        "revenueGrowth": 0.20,
        "returnOnInvestedCapital": 0.18,
        "returnOnEquity": 0.25,
        "debtToEquity": 0.5,
        "currentRatio": 2.0,
    }]


@pytest.fixture
def sec_ratios_breached():
    """SEC ratios where gross margin and revenue growth are below thresholds."""
    return [{
        "date": "2025-12-31",
        "grossProfitMargin": 0.45,   # Below 60% threshold
        "operatingProfitMargin": 0.10,
        "revenueGrowth": 0.08,       # Below 15% threshold
        "returnOnInvestedCapital": 0.12,
        "returnOnEquity": 0.15,
        "debtToEquity": 0.5,
        "currentRatio": 2.0,
    }]


@pytest.fixture
def positions_with_assumptions():
    """Portfolio positions with key_assumptions from IC verdict."""
    return [
        {
            "ticker": "ACME",
            "shares": 100,
            "cost_basis": 50.0,
            "key_assumptions": [
                "Revenue growth sustains above 15%",
                "Gross margin holds above 60%",
            ],
        },
    ]


@pytest.fixture
def positions_with_exit():
    """Portfolio positions including an exited position."""
    return [
        {
            "ticker": "ACME",
            "shares": 100,
            "cost_basis": 50.0,
            "key_assumptions": ["Gross margin holds above 60%"],
        },
        {
            "ticker": "GONE",
            "shares": 0,
            "cost_basis": 40.0,
            "status": "exited",
            "exit_price": 52.0,
            "entry_date": "2025-01-15",
            "exit_date": "2025-12-20",
            "key_assumptions": ["Revenue growth sustains above 10%"],
        },
    ]


# ---------------------------------------------------------------------------
# _parse_assumption unit tests
# ---------------------------------------------------------------------------

class TestParseAssumption:
    def test_revenue_growth_above(self):
        metric, threshold, direction = _parse_assumption("Revenue growth sustains above 15%")
        assert metric == "revenueGrowth"
        assert threshold == pytest.approx(0.15)
        assert direction == "above"

    def test_gross_margin_above(self):
        metric, threshold, direction = _parse_assumption("Gross margin holds above 60%")
        assert metric == "grossProfitMargin"
        assert threshold == pytest.approx(0.60)
        assert direction == "above"

    def test_debt_to_equity_below(self):
        metric, threshold, direction = _parse_assumption("Debt to equity stays below 1.5")
        assert metric == "debtToEquity"
        assert threshold == pytest.approx(1.5)
        assert direction == "below"

    def test_unparseable_assumption(self):
        metric, threshold, direction = _parse_assumption("Multiple re-rates toward fair value")
        assert metric is None
        assert threshold is None

    def test_roic_above(self):
        metric, threshold, direction = _parse_assumption("ROIC exceeds 12%")
        assert metric == "returnOnInvestedCapital"
        assert threshold == pytest.approx(0.12)
        assert direction == "above"


# ---------------------------------------------------------------------------
# F1: SEC thesis health checks
# ---------------------------------------------------------------------------

class TestThesisHealthIntact:
    """F1: When current SEC data meets thresholds, all assumptions are 'intact'."""

    def test_thesis_health_intact(self, sec_ratios_healthy, positions_with_assumptions):
        sec = FakeSEC(ratios=sec_ratios_healthy)
        agent = PortfolioAgent(sec=sec)

        result = asyncio.run(
            agent._check_thesis_health(
                ticker="ACME",
                key_assumptions=positions_with_assumptions[0]["key_assumptions"],
            )
        )

        assert len(result) == 2
        assert all(r["status"] == "intact" for r in result)
        # Verify actual values are populated
        assert result[0]["current_value"] == pytest.approx(0.20)  # revenueGrowth
        assert result[1]["current_value"] == pytest.approx(0.65)  # grossProfitMargin


class TestThesisHealthBreach:
    """F1: When current SEC data is below threshold, status is 'breach' and alert is generated."""

    def test_thesis_health_breach(self, sec_ratios_breached, positions_with_assumptions):
        sec = FakeSEC(ratios=sec_ratios_breached)
        agent = PortfolioAgent(sec=sec)

        result = asyncio.run(
            agent._check_thesis_health(
                ticker="ACME",
                key_assumptions=positions_with_assumptions[0]["key_assumptions"],
            )
        )

        assert len(result) == 2
        assert all(r["status"] == "breach" for r in result)
        assert result[0]["metric"] == "revenueGrowth"
        assert result[0]["current_value"] == pytest.approx(0.08)
        assert result[1]["metric"] == "grossProfitMargin"
        assert result[1]["current_value"] == pytest.approx(0.45)

    def test_breach_generates_critical_alert(self, sec_ratios_breached):
        """Full run() should produce a thesis_breach alert with severity 'critical'."""
        sec = FakeSEC(ratios=sec_ratios_breached)
        quotes = FakeQuoteSource({"ACME": 55.0})
        agent = PortfolioAgent(sec=sec, yfinance=quotes)

        context = {
            "positions": [{
                "ticker": "ACME",
                "shares": 100,
                "cost_basis": 50.0,
                "key_assumptions": ["Gross margin holds above 60%"],
            }],
        }

        result = asyncio.run(agent.run(context))

        assert result.ok
        alerts = result.data.get("alerts", [])
        thesis_alerts = [a for a in alerts if a["type"] == "thesis_breach"]
        assert len(thesis_alerts) == 1
        assert thesis_alerts[0]["severity"] == "critical"
        assert thesis_alerts[0]["ticker"] == "ACME"
        assert "Gross margin" in thesis_alerts[0]["message"]

        # Verify thesis_health is attached to holding
        holdings = result.data.get("holdings", [])
        acme = [h for h in holdings if h["ticker"] == "ACME"][0]
        assert "thesis_health" in acme
        assert acme["thesis_health"][0]["status"] == "breach"


class TestThesisHealthNoSEC:
    """F1: SEC connector unavailable — thesis health skipped, no crash."""

    def test_thesis_health_no_sec(self, positions_with_assumptions):
        agent = PortfolioAgent(sec=None)

        result = asyncio.run(
            agent._check_thesis_health(
                ticker="ACME",
                key_assumptions=positions_with_assumptions[0]["key_assumptions"],
            )
        )

        assert result == []

    def test_run_no_sec_no_crash(self):
        """Full run() without SEC connector should work fine."""
        quotes = FakeQuoteSource({"ACME": 55.0})
        agent = PortfolioAgent(sec=None, yfinance=quotes)

        context = {
            "positions": [{
                "ticker": "ACME",
                "shares": 100,
                "cost_basis": 50.0,
                "key_assumptions": ["Revenue growth sustains above 15%"],
            }],
        }

        result = asyncio.run(agent.run(context))

        assert result.ok
        # No thesis_breach alerts since SEC is unavailable
        alerts = result.data.get("alerts", [])
        thesis_alerts = [a for a in alerts if a["type"] == "thesis_breach"]
        assert len(thesis_alerts) == 0


class TestThesisHealthNoAssumptions:
    """F1: No key_assumptions in position — thesis health skipped."""

    def test_no_assumptions_skips(self, sec_ratios_healthy):
        sec = FakeSEC(ratios=sec_ratios_healthy)
        agent = PortfolioAgent(sec=sec)

        result = asyncio.run(
            agent._check_thesis_health(ticker="ACME", key_assumptions=[])
        )

        assert result == []

    def test_run_no_assumptions_no_health(self, sec_ratios_healthy):
        """Full run() with position lacking key_assumptions should skip thesis health."""
        sec = FakeSEC(ratios=sec_ratios_healthy)
        quotes = FakeQuoteSource({"ACME": 55.0})
        agent = PortfolioAgent(sec=sec, yfinance=quotes)

        context = {
            "positions": [{
                "ticker": "ACME",
                "shares": 100,
                "cost_basis": 50.0,
                # No key_assumptions
            }],
        }

        result = asyncio.run(agent.run(context))

        assert result.ok
        holdings = result.data.get("holdings", [])
        acme = [h for h in holdings if h["ticker"] == "ACME"][0]
        assert "thesis_health" not in acme


# ---------------------------------------------------------------------------
# F2: Exit → Learning feedback
# ---------------------------------------------------------------------------

class TestExitJudgmentEvent:
    """F2: Position exit records a judgment event."""

    def test_exit_judgment_event_recorded(self, sec_ratios_healthy):
        db = MagicMock()
        db.record_judgment_event = MagicMock(return_value=42)
        sec = FakeSEC(ratios=sec_ratios_healthy)
        quotes = FakeQuoteSource({"ACME": 55.0, "GONE": 52.0})
        agent = PortfolioAgent(db=db, sec=sec, yfinance=quotes)

        context = {
            "positions": [
                {
                    "ticker": "ACME",
                    "shares": 100,
                    "cost_basis": 50.0,
                    "key_assumptions": ["Revenue growth sustains above 15%"],
                },
                {
                    "ticker": "GONE",
                    "shares": 0,
                    "cost_basis": 40.0,
                    "status": "exited",
                    "exit_price": 52.0,
                    "entry_date": "2025-01-15",
                    "exit_date": "2025-12-20",
                    "key_assumptions": ["Revenue growth sustains above 10%"],
                },
            ],
        }

        asyncio.run(agent.run(context))

        # Verify judgment event was recorded for GONE
        db.record_judgment_event.assert_called_once()
        call_kwargs = db.record_judgment_event.call_args
        assert call_kwargs[1]["event_type"] == "position_exited"
        assert call_kwargs[1]["ticker"] == "GONE"
        assert call_kwargs[1]["agent"] == "portfolio"
        data = call_kwargs[1]["data"]
        assert data["entry_price"] == 40.0
        assert data["exit_price"] == 52.0
        assert data["return_pct"] == pytest.approx(30.0)
        assert data["hold_duration_days"] == 339  # Jan 15 to Dec 20
        assert data["thesis_integrity_at_exit"] in ("intact", "at_risk", "breached", "unknown")

    def test_exit_return_calculation(self):
        """Verify return_pct is calculated correctly."""
        db = MagicMock()
        db.record_judgment_event = MagicMock(return_value=1)
        agent = PortfolioAgent(db=db)

        agent._record_exit(
            ticker="TEST",
            entry_price=100.0,
            exit_price=130.0,
            entry_date="2025-01-01",
            exit_date="2025-07-01",
            thesis_health=[{"status": "intact"}],
        )

        call_kwargs = db.record_judgment_event.call_args
        data = call_kwargs[1]["data"]
        assert data["return_pct"] == pytest.approx(30.0)
        assert data["thesis_integrity_at_exit"] == "intact"

    def test_exit_with_breach_thesis(self):
        """Exit with breached thesis should record thesis_integrity as 'breached'."""
        db = MagicMock()
        db.record_judgment_event = MagicMock(return_value=1)
        agent = PortfolioAgent(db=db)

        agent._record_exit(
            ticker="BAD",
            entry_price=100.0,
            exit_price=70.0,
            entry_date="2025-01-01",
            exit_date="2025-06-01",
            thesis_health=[
                {"status": "intact"},
                {"status": "breach"},
            ],
        )

        data = db.record_judgment_event.call_args[1]["data"]
        assert data["return_pct"] == pytest.approx(-30.0)
        assert data["thesis_integrity_at_exit"] == "breached"


class TestExitNoDBNoCrash:
    """F2: No db → exit recording skipped gracefully."""

    def test_exit_no_db_no_crash(self):
        agent = PortfolioAgent(db=None)

        # Should not raise
        agent._record_exit(
            ticker="TEST",
            entry_price=100.0,
            exit_price=130.0,
            entry_date="2025-01-01",
            exit_date="2025-07-01",
        )

    def test_exit_db_error_no_crash(self):
        """DB error during exit recording should be caught."""
        db = MagicMock()
        db.record_judgment_event = MagicMock(side_effect=Exception("DB write failed"))
        agent = PortfolioAgent(db=db)

        # Should not raise despite DB error
        agent._record_exit(
            ticker="TEST",
            entry_price=100.0,
            exit_price=130.0,
            entry_date="2025-01-01",
            exit_date="2025-07-01",
        )
