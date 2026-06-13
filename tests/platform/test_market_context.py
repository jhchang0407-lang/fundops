"""Phase 2-4 backend surface: events, watchlists, macro, peers, Research Hub
aggregates, portfolio analytics, the learning->Constitution loop, offline
research runs, and CSV exports. All offline/deterministic."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.services.portfolio_service import PortfolioService

from tests.platform.conftest import FAKE_METRICS, _persist


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def seeded(stores):
    return {t: _persist(stores, t, m) for t, m in FAKE_METRICS.items()}


def _seed_bars(stores, ticker: str, days: int = 400, base: float = 100.0,
               gain: float = 0.001, volume: float = 1e6):
    today = datetime.now(timezone.utc).date()
    rows, price = [], base
    for d in range(days, 0, -1):
        rows.append({"ticker": ticker, "date": (today - timedelta(days=d)).isoformat(),
                     "close": round(price, 4), "volume": volume})
        price *= 1 + gain
    stores.bulk.upsert_prices(rows)


# --- watchlists -------------------------------------------------------------------

def test_watchlist_crud_and_rows(client, stores, seeded):
    r = client.post("/api/watchlists", json={"name": "Defense tech",
                                             "tickers": ["AAA", "BBB"]})
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    assert r.json()["tickers"] == ["AAA", "BBB"]
    # duplicate name rejected
    assert client.post("/api/watchlists", json={"name": "defense TECH"}).status_code == 409
    out = client.get("/api/watchlists").json()["watchlists"][0]
    row = next(x for x in out["rows"] if x["ticker"] == "AAA")
    assert row["price"] == 100.0
    client.delete(f"/api/watchlists/{wid}/tickers/BBB")
    assert stores.context.get_watchlist(wid)["tickers"] == ["AAA"]
    client.delete(f"/api/watchlists/{wid}")
    assert stores.context.get_watchlist(wid) is None


# --- macro --------------------------------------------------------------------------

def test_macro_strip_with_cached_series(client, stores):
    today = datetime.now(timezone.utc).date()
    stores.context.upsert_macro("DGS10", [{"date": today.isoformat(), "value": 4.21}])
    cpi = [{"date": (today - timedelta(days=370)).isoformat(), "value": 300.0},
           {"date": today.isoformat(), "value": 309.0}]
    stores.context.upsert_macro("CPIAUCSL", cpi)
    strip = {s["series"]: s for s in client.get("/api/macro").json()["series"]}
    assert strip["DGS10"]["display"] == "4.21%"
    assert strip["CPIAUCSL"]["value"] == pytest.approx(3.0, abs=0.01)
    assert strip["DFF"]["display"] == "—"  # not cached yet, honest gap


# --- events ----------------------------------------------------------------------

def test_company_events_merges_sources(client, stores, seeded):
    stores.context.upsert_event("AAA", "earnings",
                                (datetime.now(timezone.utc).date()
                                 + timedelta(days=20)).isoformat(), label="Earnings")
    stores.bulk.add_filing(cik="0001", ticker="AAA", form="10-Q",
                           filed_at="2026-05-01", accession="acc-1")
    stores.bulk.add_ownership("AAA", kind="insider_transaction", as_of="2026-05-10",
                              owner_name="Jane Doe", owner_role="CEO",
                              shares=1000, value=100000, txn_type="buy")
    events = client.get("/api/company/AAA/events").json()["events"]
    kinds = {e["kind"] for e in events}
    assert {"earnings", "filing", "insider_cluster"} <= kinds


def test_upcoming_events_scoped_to_holdings_and_watchlists(client, stores, seeded):
    future = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    stores.context.upsert_event("AAA", "earnings", future, label="Earnings")
    stores.context.upsert_event("CCC", "earnings", future, label="Earnings")
    assert client.get("/api/events/upcoming").json()["events"] == []  # no scope yet
    PortfolioService(stores).add_lot("AAA", 5, 90.0, "2026-01-02")
    events = client.get("/api/events/upcoming").json()["events"]
    assert [e["ticker"] for e in events] == ["AAA"]  # CCC not held/watched


def test_company_events_empty_reason_in_and_out_of_scope(client, stores, seeded):
    # AAA held -> in scope; no events retained -> awaiting-sync reason.
    PortfolioService(stores).add_lot("AAA", 5, 90.0, "2026-01-02")
    held = client.get("/api/company/AAA/events").json()
    assert held["events"] == [] and "daily sync" in (held.get("empty_reason") or "")
    # ZZZ not held/watched -> out-of-scope (add-to-watchlist) reason.
    out = client.get("/api/company/ZZZ/events").json()
    assert out["events"] == [] and "watchlist" in (out.get("empty_reason") or "").lower()


def test_macro_sync_records_and_clears_last_sync_error(stores, monkeypatch):
    import asyncio

    from backend.services import macro

    def boom(series, start):
        raise RuntimeError("fred unreachable")

    monkeypatch.setattr(macro, "_fetch_csv", boom)
    asyncio.run(macro.sync_macro(stores))
    strip = {s["series"]: s for s in macro.macro_strip(stores)}
    assert strip["DGS10"]["value"] is None
    assert "fred unreachable" in (strip["DGS10"]["last_sync_error"] or "")

    today = datetime.now(timezone.utc).date().isoformat()
    monkeypatch.setattr(macro, "_fetch_csv",
                        lambda series, start: [{"date": today, "value": 4.2}])
    asyncio.run(macro.sync_macro(stores))
    strip2 = {s["series"]: s for s in macro.macro_strip(stores)}
    assert strip2["DGS10"]["last_sync_error"] is None
    assert strip2["DGS10"]["last_sync_at"] and strip2["DGS10"]["value"] == 4.2


# --- peers + research hub ----------------------------------------------------------

def test_peers_and_industry_dashboard(client, stores):
    for t, (sector, industry, cap) in {
        "AXA": ("Industrials", "Aerospace & Defense", 5e9),
        "BXB": ("Industrials", "Aerospace & Defense", 4e9),
        "CXC": ("Industrials", "Aerospace & Defense", 20e9),
        "DXD": ("Technology", "Software", 1e9),
    }.items():
        ent = stores.identity.ensure_entity(t, name=f"{t} Corp", sector=sector,
                                            industry=industry)
        stores.identity.ws.execute(
            "UPDATE investment_entities SET industry = ? WHERE id = ?",
            (industry, ent["id"]))
        stores.financial.store_metrics_snapshot(
            ent["id"], {"market_cap": cap, "roic": 0.10, "gross_margin": 0.40},
            "2026-03-31", "annual", {"source": "test"})
    peers = client.get("/api/company/AXA/peers").json()["peers"]
    assert peers[0]["ticker"] == "AXA" and peers[0]["is_subject"]
    assert {p["ticker"] for p in peers} == {"AXA", "BXB", "CXC"}  # same industry only
    assert peers[1]["ticker"] == "BXB"  # nearest by market cap

    tree = client.get("/api/research/sectors").json()["sectors"]
    industrials = next(s for s in tree if s["sector"] == "Industrials")
    assert industrials["count"] == 3
    dash = client.get("/api/research/industry",
                      params={"industry": "Aerospace & Defense"}).json()
    assert dash["size"] == 3
    assert dash["aggregates"]["roic"]["median"] == pytest.approx(0.10)
    assert len(dash["constituents"]) == 3


# --- portfolio analytics --------------------------------------------------------------

def test_portfolio_analytics_vs_benchmark(client, stores, seeded):
    _seed_bars(stores, "AAA", days=200, base=100.0, gain=0.002)
    _seed_bars(stores, "^GSPC", days=200, base=5000.0, gain=0.001)
    last_close = stores.bulk.latest_close("AAA")["close"]
    stores.portfolio.mark_price("AAA", last_close)
    purchase = (datetime.now(timezone.utc).date() - timedelta(days=150)).isoformat()
    PortfolioService(stores).add_lot("AAA", 10, 100.0, purchase)
    out = client.get("/api/portfolio/analytics", params={"range": "1y"}).json()
    perf = out["performance"]
    assert perf["benchmark_available"] is True
    assert perf["portfolio_return"] is not None and perf["portfolio_return"] > 0
    assert perf["benchmark_return"] is not None
    assert perf["excess_return"] == pytest.approx(
        perf["portfolio_return"] - perf["benchmark_return"], abs=1e-9)
    assert perf["portfolio_series"] and perf["benchmark_series"]
    contrib = out["contribution"]
    assert contrib[0]["ticker"] == "AAA" and contrib[0]["total_pnl"] > 0
    assert out["exposure"]["sectors"][0]["sector"] == "Technology"
    assert out["risk"]["max_drawdown"] is not None
    assert "volatility" in out["risk"]


def test_weekend_flow_is_not_performance(stores, seeded):
    """A buy dated on a non-trading day attaches to the next bar day as a
    flow — TWR must read 0%, not +100% (audit finding: dropped flows)."""
    from backend.services.portfolio_analytics import benchmark_compare, value_series

    today = datetime.now(timezone.utc).date()
    # Bars only on even days back; flat price.
    rows = [{"ticker": "AAA", "date": (today - timedelta(days=d)).isoformat(),
             "close": 100.0, "volume": 1e6} for d in range(60, 0, -2)]
    stores.bulk.upsert_prices(rows)
    stores.portfolio.mark_price("AAA", 100.0)
    svc = PortfolioService(stores)
    svc.add_lot("AAA", 10, 100.0, (today - timedelta(days=59)).isoformat())
    # Second buy dated on a NON-bar day (odd offset).
    svc.add_lot("AAA", 10, 100.0, (today - timedelta(days=29)).isoformat())
    series = value_series(stores, "1y")
    assert sum(p["flow"] for p in series) == pytest.approx(2000.0)  # both flows land
    perf = benchmark_compare(stores, "1y")
    assert perf["portfolio_return"] == pytest.approx(0.0, abs=1e-9)


def test_risk_ignores_deposits_and_withdrawals(stores, seeded):
    """Flat prices + a mid-window deposit and a partial sale: volatility 0,
    drawdown 0 (audit findings: flow jumps read as vol/crash)."""
    from backend.services.portfolio_analytics import risk

    today = datetime.now(timezone.utc).date()
    rows = [{"ticker": "AAA", "date": (today - timedelta(days=d)).isoformat(),
             "close": 100.0, "volume": 1e6} for d in range(90, 0, -1)]
    stores.bulk.upsert_prices(rows)
    stores.portfolio.mark_price("AAA", 100.0)
    svc = PortfolioService(stores)
    svc.add_lot("AAA", 10, 100.0, (today - timedelta(days=89)).isoformat())
    svc.add_lot("AAA", 10, 100.0, (today - timedelta(days=45)).isoformat())  # deposit
    svc.record_sale("AAA", 10, 100.0, (today - timedelta(days=20)).isoformat())  # withdrawal
    out = risk(stores, "1y")
    assert out["max_drawdown"] == pytest.approx(0.0, abs=1e-9)
    assert out.get("volatility", 0.0) == pytest.approx(0.0, abs=1e-9)


def test_contribution_denominator_uses_original_cost(client, stores, seeded):
    """A profitable sale must not inflate capital deployed: sold cost =
    proceeds - realized P&L, not proceeds."""
    from backend.services.portfolio_analytics import contribution

    svc = PortfolioService(stores)
    svc.add_lot("AAA", 10, 100.0, "2026-01-02")     # $1,000 deployed
    svc.record_sale("AAA", 10, 150.0, "2026-03-01")  # +$500 realized
    rows = contribution(stores)
    aaa = next(r for r in rows if r["ticker"] == "AAA")
    assert aaa["realized_pnl"] == pytest.approx(500.0)
    # 500 profit on 1,000 deployed = +50pp (NOT 500/1500 = 33pp).
    assert aaa["contribution_pp"] == pytest.approx(50.0, abs=0.1)


# --- learning -> Constitution loop ----------------------------------------------------

def test_accepted_recommendation_becomes_pending_proposal(client, stores, seeded,
                                                          constitution):
    rec_id = stores.learning.add_record(
        "recommendation",
        {"proposed_change": {"kind": "research_review", "metric": "fcf_yield",
                             "direction": "low",
                             "summary": "add a research-review check on fcf_yield"},
         "supporting_tickers": ["CCC", "FFF"], "windows": [6, 12],
         "teaching_note": "Low FCF yield picks repeatedly underperformed."},
        confidence_label="recommendation_ready",
    )
    client.post("/api/dashboard/refresh")
    items = client.get("/api/dashboard").json()["needs_decision"]
    item = next(i for i in items if i["source_type"] == "learning_recommendation")
    assert stores.constitution.pending_proposal() is None
    res = client.post(f"/api/dashboard/items/{item['id']}/respond",
                      json={"response": "accept"}).json()
    assert res.get("proposal_id")
    pending = stores.constitution.pending_proposal()
    assert pending is not None and pending["id"] == res["proposal_id"]
    rules = pending["payload"]["rules"]
    new_rule = next(r for r in rules if r["criterion_id"] == "research_review.fcf_yield_learning")
    assert new_rule["kind"] == "research_review"
    assert f"learning_recommendation:{rec_id}" == new_rule["rule_source"]
    # Existing constitution rules carried over, nothing auto-activated.
    assert len(rules) == len(constitution["criteria"]) + 1
    assert stores.constitution.active_version()["id"] == constitution["id"]


def test_dashboard_accept_activates_proposal(client, stores, seeded, constitution):
    """An approval record must never exist without its effect: accepting a
    strategy proposal from the Dashboard activates it like Chat approval."""
    stores.learning.add_record(
        "recommendation",
        {"proposed_change": {"kind": "research_review", "metric": "fcf_yield",
                             "direction": "low", "summary": "watch fcf_yield"},
         "supporting_tickers": ["CCC"], "windows": [6],
         "teaching_note": "note"},
        confidence_label="recommendation_ready",
    )
    client.post("/api/dashboard/refresh")
    items = client.get("/api/dashboard").json()["needs_decision"]
    rec_item = next(i for i in items if i["source_type"] == "learning_recommendation")
    res = client.post(f"/api/dashboard/items/{rec_item['id']}/respond",
                      json={"response": "accept"}).json()
    proposal_id = res["proposal_id"]
    client.post("/api/dashboard/refresh")
    items = client.get("/api/dashboard").json()["needs_decision"]
    prop_item = next(i for i in items if i["source_id"] == proposal_id)
    out = client.post(f"/api/dashboard/items/{prop_item['id']}/respond",
                      json={"response": "accept"}).json()
    assert out.get("version_id")
    active = stores.constitution.active_version()
    assert active["id"] == out["version_id"]
    assert active["version_number"] == constitution["version_number"] + 1
    assert any(c["criterion_id"] == "research_review.fcf_yield_learning"
               for c in active["criteria"])
    assert stores.constitution.pending_proposal() is None


# --- research runs (offline stub) ------------------------------------------------------

RISK_OLD = ("We depend on a small number of customers. " * 12 + "\n\n"
            + "Supply chain constraints may impact component availability. " * 8)
RISK_NEW = ("We depend on a small number of customers. " * 12 + "\n\n"
            + "Expanded export-control restrictions may limit international sales. " * 8)


def test_risk_diff_run_offline(client, stores, seeded):
    stores.context.upsert_filing_section("acc-old", "risk_factors", RISK_OLD,
                                         ticker="AAA", form="10-K", filed_at="2025-03-01")
    stores.context.upsert_filing_section("acc-new", "risk_factors", RISK_NEW,
                                         ticker="AAA", form="10-K", filed_at="2026-03-01")
    out = client.post("/api/company/AAA/research", json={"kind": "risk_diff"}).json()
    assert out["ok"] is True
    art = stores.artifacts.get(out["artifact_id"])
    assert art["kind"] == "filing_note"
    assert art["payload"]["body"]["diff_counts"]["added"] >= 1
    assert art["payload"]["body"]["diff_counts"]["removed"] >= 1
    assert len(art["payload"]["body"]["sources"]) == 2


def test_risk_diff_needs_two_filings(client, stores, seeded):
    out = client.post("/api/company/BBB/research", json={"kind": "risk_diff"})
    assert out.status_code == 409
    assert "two 10-K" in out.json()["detail"]


def test_industry_note_run_offline(client, stores, seeded):
    out = client.post("/api/research/runs",
                      json={"kind": "industry_note",
                            "tickers": ["AAA", "BBB"]}).json()
    assert out["ok"] is True
    art = stores.artifacts.get(out["artifact_id"])
    assert art["kind"] == "industry_note"
    assert art["payload"]["body"]["tickers"] == ["AAA", "BBB"]
    assert art["rendered_md"]
    notes = client.get("/api/research/notes").json()["notes"]
    assert any(n["id"] == out["artifact_id"] for n in notes)


def test_home_briefing_composes_from_records(client, stores, seeded, constitution):
    """Deterministic briefing: held-ticker filings, health states, learning
    readiness, events, macro — no model call, every item referenced."""
    PortfolioService(stores).add_lot("AAA", 5, 90.0, "2026-01-02")
    today = datetime.now(timezone.utc).date()
    stores.bulk.add_filing(cik="0001", ticker="AAA", form="10-Q",
                           filed_at=today.isoformat(), accession="brief-acc-1")
    stores.bulk.add_filing(cik="0002", ticker="CCC", form="10-Q",  # not held
                           filed_at=today.isoformat(), accession="brief-acc-2")
    stores.context.upsert_event("AAA", "earnings",
                                (today + timedelta(days=5)).isoformat(), label="Earnings")
    stores.learning.add_record(
        "recommendation", {"proposed_change": {"metric": "fcf_yield"}},
        confidence_label="recommendation_ready")
    out = client.get("/api/home/briefing").json()
    assert [f["ticker"] for f in out["filings"]] == ["AAA"]  # held only
    assert out["learning_ready"] == 1
    assert out["learning"]["ready"] == 1  # observable learning summary
    assert out["events"] and out["events"][0]["ticker"] == "AAA"
    assert out["watch_total"] == 1
    assert {s["series"] for s in out["macro"]} == {"DGS10", "DFF", "UNRATE", "CPIAUCSL"}
    assert out["pending_proposal"] is None


# --- CSV exports ---------------------------------------------------------------------

def test_csv_exports(client, stores, seeded):
    PortfolioService(stores).add_lot("AAA", 10, 90.0, "2026-01-15")
    r = client.get("/api/export/portfolio.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "AAA" in r.text and "ticker" in r.text
    r2 = client.get("/api/export/financials/AAA.csv")
    assert r2.status_code == 200
    assert "roic" in r2.text


def test_workspace_export_estimate_and_skips_rebuildable_bulk(client, stores, seeded):
    """Pre-download size estimate is exposed and the resyncable financial bulk
    is excluded from the workspace archive (ISSUE-004)."""
    est = client.get("/api/settings/export/estimate").json()
    assert "approx_bytes" in est and est["total_rows"] >= 0
    assert {"financial_observations", "reported_financial_facts",
            "price_history"} <= set(est["excluded_tables"])
    # The archive itself must not carry the excluded rebuildable tables.
    dump = client.get("/api/settings/export").json()
    assert "financial_observations" not in dump["tables"]
    assert "reported_financial_facts" not in dump["tables"]
    assert "portfolio_lots" in dump["tables"]  # user state retained
