"""#22: sector-aware metric profiles in the Research Hub.

The flat industrial template (gross_margin/roic) reads as ~4% / blank for bank
filers — the largest sector. A sector-aware profile reads financials on
roe / operating_margin (which ARE populated) and labels gross_margin/roic as
not-applicable. revenue_growth (0 stored rows, no rescue) is dropped for all.
"""

from __future__ import annotations

from backend.services import research_hub as rh


def _seed_bank(stores, ticker, roe, net_margin, op_margin):
    ent = stores.identity.ensure_entity(
        ticker, name=f"{ticker} Bancorp", sector="Banks & Financial Services",
        industry="Banks")
    # roe/net_margin/operating_margin populated; gross_margin/roic absent.
    stores.financial.store_metrics_snapshot(
        ent["id"],
        {"roe": roe, "net_margin": net_margin, "operating_margin": op_margin,
         "revenue": 5.0e9},
        "2025-12-31", "annual")
    stores.portfolio.mark_price(ticker, 50.0)
    return ent


def test_profile_for_keys_on_stored_sector_strings():
    assert rh.profile_for([{"sector": "Banks & Financial Services"}]) is rh.FINANCIAL_PROFILE
    assert rh.profile_for([{"sector": "Insurance"}]) is rh.FINANCIAL_PROFILE
    assert rh.profile_for([{"sector": "REITs"}]) is rh.FINANCIAL_PROFILE
    assert rh.profile_for([{"sector": "Software & IT Services"}]) is rh.DEFAULT_PROFILE
    assert rh.profile_for([{"sector": None}]) is rh.DEFAULT_PROFILE
    assert rh.profile_for([]) is rh.DEFAULT_PROFILE
    # revenue_growth is dropped everywhere.
    assert "revenue_growth" not in rh.DEFAULT_PROFILE["aggregates"]
    assert "revenue_growth" not in rh.FINANCIAL_PROFILE["constituents"]


def test_bank_group_dashboard_uses_financial_profile(stores):
    _seed_bank(stores, "BNKA", 0.12, 0.28, 0.34)
    _seed_bank(stores, "BNKB", 0.10, 0.22, 0.30)
    entities = stores.identity.entities_in_group(sector="Banks & Financial Services")
    dash = rh.group_dashboard(stores, entities, "Banks")

    # roe is surfaced; the industrial gross_margin/roic are NOT (and never as coverage:0).
    assert "roe" in dash["aggregates"]
    assert "gross_margin" not in dash["aggregates"]
    assert "roic" not in dash["aggregates"]
    assert dash["aggregates"]["roe"]["median"] == 0.11

    assert "roe" in dash["constituent_metrics"]
    assert "gross_margin" not in dash["constituent_metrics"]
    assert dash["trend_metric"] == "operating_margin"
    assert dash["trend_label"] == "operating margin"
    assert set(dash["na_metrics"]) == {"gross_margin", "roic"}
    assert dash["aggregate_metrics"] == list(dash["aggregates"].keys())


def test_bank_peers_use_financial_metrics(stores):
    _seed_bank(stores, "BNKA", 0.12, 0.28, 0.34)
    _seed_bank(stores, "BNKB", 0.10, 0.22, 0.30)
    peers = rh.peers_for(stores, "BNKA")
    assert peers and peers[0]["is_subject"]
    assert "roe" in peers[0]
    assert "gross_margin" not in peers[0]
