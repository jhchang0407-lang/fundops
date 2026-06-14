"""Shared platform-test fixtures: one tmp workspace per test.

Kept minimal and idempotent so test_workflows.py and test_monitoring.py can
both use it. Workflow tests additionally get offline stub-mode AI (no API
key) and a deterministic fake MarketDataService — no network anywhere."""

from __future__ import annotations

import pytest

from backend.core import ai
from backend.core.workspace import Workspace, set_workspace
from backend.domain import wiring
from backend.domain.criteria import Criterion
from backend.services.market_data import MarketDataService
from backend.stores import Stores


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace(tmp_path / "ws.db")
    set_workspace(ws)
    yield ws
    set_workspace(None)
    ws.close()


@pytest.fixture
def stores(workspace):
    return Stores(workspace)


# --- workflow-test fixtures -------------------------------------------------------

UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]

# Deterministic metric fixtures. With the screen roic>=0.10 / gross_margin>=0.30:
# AAA/BBB/CCC/FFF pass, DDD fails both, EEE has no data (unevaluable).
# Thesis stub expected return = (fcf_yield + revenue_growth) * 100:
# AAA 18.0, BBB 13.0, CCC 3.0 (capped < 5.0), FFF 7.0 (< IC hurdle 8).
FAKE_METRICS = {
    "AAA": {"company_name": "Alpha Corp", "sector": "Technology", "price": 100.0,
            "roic": 0.25, "gross_margin": 0.55, "fcf_yield": 0.06,
            "revenue_growth": 0.12, "pe": 22.0, "eps": 6.0, "debt_equity": 0.5,
            "revenue": 5.0e10, "operating_margin": 0.30, "fcf_margin": 0.25},
    "BBB": {"company_name": "Beta Industries", "sector": "Industrials", "price": 50.0,
            "roic": 0.18, "gross_margin": 0.45, "fcf_yield": 0.05,
            "revenue_growth": 0.08, "pe": 18.0, "eps": 2.5, "debt_equity": 0.8,
            "revenue": 2.0e10, "operating_margin": 0.18, "fcf_margin": 0.15},
    "CCC": {"company_name": "Gamma Holdings", "sector": "Consumer", "price": 80.0,
            "roic": 0.12, "gross_margin": 0.35, "fcf_yield": 0.02,
            "revenue_growth": 0.01, "pe": 20.0, "eps": 4.0, "debt_equity": 1.2,
            "revenue": 1.0e10, "operating_margin": 0.10, "fcf_margin": 0.05},
    "DDD": {"company_name": "Delta Co", "sector": "Energy", "price": 30.0,
            "roic": 0.05, "gross_margin": 0.25, "fcf_yield": 0.07,
            "revenue_growth": 0.15, "pe": 8.0, "eps": 3.5, "debt_equity": 2.0,
            "revenue": 6.0e9},
    "FFF": {"company_name": "Zeta Group", "sector": "Healthcare", "price": 40.0,
            "roic": 0.11, "gross_margin": 0.32, "fcf_yield": 0.03,
            "revenue_growth": 0.04, "pe": 13.0, "eps": 3.0, "debt_equity": 0.6,
            "revenue": 8.0e9, "operating_margin": 0.12, "fcf_margin": 0.08},
}


@pytest.fixture(autouse=True)
def no_web(monkeypatch):
    """Tests never touch the live web. The developer's real config may have the
    web-search toggle ON, which would otherwise make every thesis/memo test
    attempt real searches (slow, flaky, networked). Web-behavior tests opt back
    in by monkeypatching web_research themselves."""
    from backend.core import web_research
    monkeypatch.setattr(web_research, "enabled", lambda: False)


@pytest.fixture
def offline_ai(monkeypatch, stores, tmp_path):
    """Stub-mode AI gateway bound to this test's stores (root conftest sets a
    dummy OPENAI_API_KEY; clear it so opconfig.api_key() returns None)."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Force the stub provider regardless of environment — a claude/codex CLI
    # on PATH must never turn unit tests into real (billed) agent calls.
    monkeypatch.setenv("FUNDOPS_AI_PROVIDER", "stub")
    monkeypatch.setenv("FUNDOPS_DB", str(tmp_path / "ws.db"))
    gateway = ai.AIGateway(stores)
    ai.set_ai(gateway)
    yield gateway
    ai.set_ai(None)


def _persist(stores, ticker: str, m: dict) -> dict:
    """Mirror what the real MarketDataService persists: entity identity,
    financial observations, price mark."""
    ent = stores.identity.ensure_entity(
        ticker, name=m["company_name"], sector=m["sector"],
    )
    numeric = {k: v for k, v in m.items() if isinstance(v, (int, float))}
    stores.financial.store_metrics_snapshot(
        ent["id"], numeric, "2026-03-31", "annual", {"source": "test-fixture"},
    )
    stores.portfolio.mark_price(ticker, m["price"])
    return {**m, "entity_id": ent["id"], "ticker": ticker}


@pytest.fixture
def fake_market(monkeypatch, stores, offline_ai):
    """Deterministic offline MarketDataService: fixed metrics for 5 tickers;
    EEE intentionally has no data."""

    async def fake_metrics_for(self, tickers, allow_fetch=True, concurrency=4):
        out = {}
        for t in (x.upper() for x in tickers):
            if t in FAKE_METRICS:
                out[t] = _persist(self.stores, t, FAKE_METRICS[t])
        return out

    async def fake_fetch_fundamentals(self, ticker):
        t = ticker.upper()
        if t not in FAKE_METRICS:
            return None
        return _persist(self.stores, t, FAKE_METRICS[t])

    monkeypatch.setattr(MarketDataService, "metrics_for", fake_metrics_for)
    monkeypatch.setattr(MarketDataService, "fetch_fundamentals", fake_fetch_fundamentals)
    return FAKE_METRICS


@pytest.fixture
def constitution(stores):
    """Small active constitution: 2 screen criteria, 2 rank criteria, 1 IC
    hurdle (expected_return >= 8); screener handoff trimmed to 3 so selection
    reflow is observable with a 6-ticker universe."""
    criteria = [
        Criterion("screen.roic_min", "screen", "quality floor", "test",
                  metric="roic", operator=">=", value=0.10),
        Criterion("screen.gross_margin_min", "screen", "margin floor", "test",
                  metric="gross_margin", operator=">=", value=0.30),
        Criterion("rank.fcf_yield", "rank", "cash-flow yield priority", "test",
                  metric="fcf_yield", operator=">", value=0.0, weight=0.6),
        Criterion("rank.revenue_growth", "rank", "growth priority", "test",
                  metric="revenue_growth", operator=">", value=0.0, weight=0.4),
        Criterion("ic.expected_return_min", "ic_hurdle", "minimum expected return",
                  "test", metric="expected_return", operator=">=", value=8.0),
    ]
    universe = {"name": "test-universe", "tickers": UNIVERSE, "source": "test"}
    projections = wiring.project_settings(
        criteria, north_star="Quality compounders at fair prices", universe=universe,
    )
    projections["screener"]["settings"]["handoff_count"] = 3
    return stores.constitution.activate_version(
        north_star="Quality compounders at fair prices",
        style_blend={"quality": 0.7, "value": 0.3},
        narrative=None,
        version_rationale="platform workflow test baseline",
        criteria=criteria,
        projections=projections,
        universe=universe,
    )
