"""Company Page financial-statement assembly (ISSUE-014/015/016/017/018).

Pins: market technicals never render as statement periods; multiple period_ends
in one fiscal year/quarter collapse to a single column; mostly-blank stub
columns are suppressed; the API exposes catalog-driven income/balance/cashflow
sections plus a per-metric snapshot basis.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import statements
from backend.domain.derive import derive_price_metrics
from backend.domain.metric_catalog import is_market_metric, statement_section


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


def _ent(stores, ticker="ZZZ"):
    return stores.identity.ensure_entity(ticker, name="Zeta", sector="Technology")


# --- catalog classification ----------------------------------------------------

def test_derive_price_metrics_fills_price_dependent_gaps():
    """The one shared read-time derivation fills market_cap/pe/fcf_yield/
    earnings_yield from price + stored fundamentals (never stored, ADR-0017),
    so every read surface agrees instead of leaving them null."""
    latest = {"shares_outstanding": 1_000_000.0, "eps": 5.0,
              "free_cash_flow": 8_000_000.0, "net_income": 4_000_000.0}
    out = derive_price_metrics(latest, price=100.0)
    assert out["market_cap"] == 100_000_000.0       # price × shares
    assert out["pe"] == 20.0                          # price / eps
    assert out["fcf_yield"] == 0.08                   # fcf / market_cap
    assert out["earnings_yield"] == 0.04
    # No price -> price-dependent metrics stay absent (not invented).
    bare = derive_price_metrics({"shares_outstanding": 1.0, "eps": 5.0}, price=None)
    assert "market_cap" not in bare and "pe" not in bare
    # Negative EPS -> no P/E (a REIT's GAAP loss must not mint a P/E).
    reit = derive_price_metrics({"shares_outstanding": 1e6, "eps": -0.6}, price=5.0)
    assert "pe" not in reit and reit["market_cap"] == 5_000_000.0


def test_statement_section_classification():
    assert statement_section("revenue") == "income"
    assert statement_section("operating_margin") == "income"
    assert statement_section("total_assets") == "balance"
    assert statement_section("free_cash_flow") == "cashflow"
    # Market technicals are not statement facts (ADR-0043).
    for m in ("momentum_12m", "volatility_90d", "avg_dollar_volume_3m",
              "price", "market_cap"):
        assert statement_section(m) == "market"
        assert is_market_metric(m)
    # Pure derived ratios fall through to "ratio", out of the statements.
    assert statement_section("pe") == "ratio"
    assert statement_section("roic") == "ratio"


# --- period normalization (ISSUE-014) ------------------------------------------

def test_normalize_collapses_duplicate_fiscal_year():
    raw = [
        {"period_end": "2025-12-31", "metrics": {"revenue": 100.0}},
        {"period_end": "2025-09-30", "metrics": {"revenue": 90.0, "net_income": 9.0}},
        {"period_end": "2024-12-31", "metrics": {"revenue": 80.0}},
    ]
    cols = statements.normalize_periods(raw, "annual")
    assert [c["period_end"] for c in cols] == ["2025-12-31", "2024-12-31"]
    # Newest period_end in the group wins per metric; older only backfills.
    assert cols[0]["metrics"]["revenue"] == 100.0
    assert cols[0]["metrics"]["net_income"] == 9.0


def test_normalize_collapses_duplicate_fiscal_quarter():
    raw = [
        {"period_end": "2025-09-30", "metrics": {"revenue": 30.0}},
        {"period_end": "2025-09-15", "metrics": {"revenue": 29.0}},
        {"period_end": "2025-06-30", "metrics": {"revenue": 28.0}},
    ]
    cols = statements.normalize_periods(raw, "quarterly")
    assert [c["period_end"] for c in cols] == ["2025-09-30", "2025-06-30"]


# --- sectioning + thin suppression (ISSUE-016) ---------------------------------

def test_sectioned_relative_suppression_and_excludes_market():
    raw = [
        {"period_end": "2025-12-31", "metrics": {
            "revenue": 100.0, "net_income": 10.0, "operating_income": 20.0,
            "gross_profit": 40.0, "ebitda": 25.0,            # dense income column
            "total_assets": 500.0, "total_equity": 200.0,
            "operating_cash_flow": 30.0,                     # uniformly-sparse cash flow
            "momentum_12m": 0.4,                             # market: excluded
        }},
        {"period_end": "2024-12-31", "metrics": {
            "revenue": 90.0,                                 # income STUB vs the dense column
            "total_assets": 480.0, "total_equity": 190.0,
            "operating_cash_flow": 28.0,
        }},
    ]
    sections = statements.sectioned(raw, "annual")
    income_years = [c["period_end"][:4] for c in sections["income"]]
    # 2024 income carries 1 of 5 lines -> stub relative to the dense column -> dropped.
    assert income_years == ["2025"]
    # Cash flow is uniformly one real line across years -> kept, not hidden.
    assert [c["period_end"][:4] for c in sections["cashflow"]] == ["2025", "2024"]
    assert all("operating_cash_flow" in c["metrics"] for c in sections["cashflow"])
    # No market metric leaks into any section.
    all_metrics = {m for sec in sections.values() for col in sec for m in col["metrics"]}
    assert "momentum_12m" not in all_metrics


# --- store + endpoint integration (ISSUE-015/018) ------------------------------

def test_periods_excludes_market_metrics(stores):
    ent = _ent(stores)
    stores.financial.add_observation(ent["id"], "revenue", "2025-12-31", "quarterly", 100.0)
    stores.financial.add_observation(ent["id"], "momentum_12m", "2026-06-10", "quarterly", 0.4)
    periods = stores.financial.periods(ent["id"], "quarterly")
    flat = {m for p in periods for m in p["metrics"]}
    assert "revenue" in flat
    assert "momentum_12m" not in flat


def test_statement_columns_drops_orphans_keeps_ratios():
    """The flat CSV/chat builder collapses fiscal duplicates, drops orphan
    near-blank columns, but keeps derived ratios (roic, pe) alongside statement
    lines."""
    raw = [
        {"period_end": "2025-12-31", "metrics": {
            "revenue": 100.0, "net_income": 10.0, "operating_income": 20.0,
            "total_assets": 500.0, "total_equity": 200.0, "roic": 0.18, "pe": 22.0}},
        {"period_end": "2020-12-31", "metrics": {"total_debt": 50.0}},  # orphan stub
    ]
    cols = statements.statement_columns(raw, "annual")
    assert [c["period_end"] for c in cols] == ["2025-12-31"]  # orphan dropped
    assert "roic" in cols[0]["metrics"] and "pe" in cols[0]["metrics"]  # ratios kept
    # Canonical order: statement lines before uncatalogued ratios.
    keys = list(cols[0]["metrics"])
    assert keys.index("revenue") < keys.index("roic")


def test_company_financials_endpoint_shape(client, stores):
    ent = _ent(stores, "ZQQ")
    for pe, vals in (
        ("2025-12-31", {"revenue": 100.0, "net_income": 10.0, "operating_income": 20.0,
                        "total_assets": 500.0, "total_equity": 200.0,
                        "operating_cash_flow": 30.0, "free_cash_flow": 25.0}),
        ("2025-09-30", {"revenue": 70.0}),  # duplicate-year stub
    ):
        for metric, v in vals.items():
            stores.financial.add_observation(ent["id"], metric, pe, "annual", v)
    stores.financial.add_observation(ent["id"], "momentum_12m", "2026-06-10", "quarterly", 0.4)

    out = client.get("/api/company/ZQQ/financials").json()
    assert "snapshot_basis" in out
    assert out["coverage"]["sections"]["income"]["available"] is True
    annual = out["annual"]
    # Duplicate 2025 columns collapsed to one.
    assert [c["period_end"] for c in annual["periods"]] == ["2025-12-31"]
    assert "income" in annual and "balance" in annual and "cashflow" in annual
    income_metrics = {m for col in annual["income"] for m in col["metrics"]}
    assert "revenue" in income_metrics
    # Market metric never appears as a statement column anywhere.
    blob = str(out)
    assert "momentum_12m" not in blob
