"""SEC bulk-ingestion tests (ADR-0059): fully offline.

Synthetic companyfacts JSON and form-index text stand in for the bulk
products; every network helper is monkeypatched; the guarded seams in
sync.py are replaced with capturing fakes so the prices/ownership modules
never run for real.
"""

from __future__ import annotations

import asyncio
import copy
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from backend.core import opconfig
from backend.services.ingest import sec_bulk, sec_index
from backend.services.ingest import sync as ingest_sync
from backend.services.market_data import MarketDataService
from backend.workflows import screener, thesis_health


def _run(coro):
    return asyncio.run(coro)


def _today():
    return datetime.now(timezone.utc).date()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    d = tmp_path / "cache"
    d.mkdir()
    monkeypatch.setattr(opconfig, "cache_dir", lambda: d)
    return d


# --- synthetic companyfacts ----------------------------------------------------------

def _entry(end, val, form, fy, fp, filed, accn, start=None):
    e = {"end": end, "val": val, "form": form, "fy": fy, "fp": fp,
         "filed": filed, "accn": accn}
    if start:
        e["start"] = start
    return e


SYN_FACTS = {
    "cik": 1234567,
    "entityName": "Synthetic Inc",
    "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            _entry("2023-12-31", 900.0, "10-K", 2023, "FY", "2024-02-20",
                   "0001234567-24-000010", start="2023-01-01"),
            _entry("2024-12-31", 1000.0, "10-K", 2024, "FY", "2025-02-20",
                   "0001234567-25-000010", start="2024-01-01"),
            _entry("2025-12-31", 1200.0, "10-K", 2025, "FY", "2026-02-20",
                   "0001234567-26-000010", start="2025-01-01"),
            _entry("2025-06-30", 280.0, "10-Q", 2025, "Q2", "2025-08-01",
                   "0001234567-25-000020", start="2025-04-01"),
            # YTD span inside a 10-Q must NOT land as a quarterly value.
            _entry("2025-06-30", 560.0, "10-Q", 2025, "Q2", "2025-08-01",
                   "0001234567-25-000020", start="2025-01-01"),
            _entry("2025-09-30", 300.0, "10-Q", 2025, "Q3", "2025-11-01",
                   "0001234567-25-000030", start="2025-07-01"),
            _entry("2026-03-31", 330.0, "10-Q", 2026, "Q1", "2026-05-01",
                   "0001234567-26-000020", start="2026-01-01"),
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            _entry("2023-12-31", 90.0, "10-K", 2023, "FY", "2024-02-20",
                   "0001234567-24-000010", start="2023-01-01"),
            _entry("2024-12-31", 100.0, "10-K", 2024, "FY", "2025-02-20",
                   "0001234567-25-000010", start="2024-01-01"),
            _entry("2025-12-31", 120.0, "10-K", 2025, "FY", "2026-02-20",
                   "0001234567-26-000010", start="2025-01-01"),
            _entry("2026-03-31", 33.0, "10-Q", 2026, "Q1", "2026-05-01",
                   "0001234567-26-000020", start="2026-01-01"),
        ]}},
    }},
}

# A later bulk refresh delivers a restatement: same period end, later filed.
SYN_FACTS_RESTATED = copy.deepcopy(SYN_FACTS)
SYN_FACTS_RESTATED["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(
    _entry("2025-12-31", 150.0, "10-K/A", 2025, "FY", "2026-04-10",
           "0001234567-26-000015", start="2025-01-01"))


def test_extract_company_facts(stores):
    ent = stores.identity.ensure_entity("SYNX", name="Synthetic Inc", cik="1234567")
    out = sec_bulk.extract_company_facts(stores, ent, SYN_FACTS)
    eid = ent["id"]
    # Reported facts retained with mapping + accession (10 distinct entries;
    # the YTD span is excluded by the duration guard).
    facts = stores.ws.query(
        "SELECT * FROM reported_financial_facts WHERE entity_id = ?", (eid,))
    assert len(facts) == out["facts"] == 10
    assert all(r["mapped_concept"] in ("revenue", "net_income") for r in facts)
    assert all(r["accession"] for r in facts)

    rev_annual = stores.financial.observations(eid, "revenue", period_type="annual")
    assert sorted(r["value"] for r in rev_annual) == [900.0, 1000.0, 1200.0]
    rev_q = stores.financial.observations(eid, "revenue", period_type="quarterly")
    assert {r["period_end"]: r["value"] for r in rev_q} == {
        "2025-06-30": 280.0, "2025-09-30": 300.0, "2026-03-31": 330.0}

    # Derived margins per matching period, with formula + input lineage.
    margins = {r["period_end"]: r for r in
               stores.financial.observations(eid, "net_margin", period_type="annual")}
    assert margins["2025-12-31"]["value"] == pytest.approx(120.0 / 1200.0)
    assert margins["2025-12-31"]["is_calculated"] == 1
    assert margins["2025-12-31"]["lineage"]["formula"] == "net_income / revenue"
    assert margins["2025-12-31"]["lineage"]["inputs"]["revenue"] == 1200.0

    # Latest projection: flows prefer the newest FULL period (FY2025), so the
    # newer Q1-2026 quarter never masquerades as headline revenue/net income.
    # Scale-invariant margins stay newest-of-any-period (Q1-2026 here).
    latest = stores.financial.latest(eid)
    assert latest["revenue"] == 1200.0
    assert latest["net_income"] == 120.0
    assert latest["net_margin"] == pytest.approx(0.1)

    # Re-extract is idempotent: no new facts, no pointless supersession.
    again = sec_bulk.extract_company_facts(stores, ent, SYN_FACTS)
    assert again == {"facts": 0, "observations": 0, "unmapped": 0}

    # A restatement in a later refresh: latest filed wins, the prior
    # observation is superseded, derived margins recalculate.
    restated = sec_bulk.extract_company_facts(stores, ent, SYN_FACTS_RESTATED)
    assert restated == {"facts": 1, "observations": 2, "unmapped": 0}  # net_income + net_margin
    ni_2025 = [r for r in stores.financial.observations(eid, "net_income", period_type="annual")
               if r["period_end"] == "2025-12-31"]
    assert [r["value"] for r in ni_2025] == [150.0]
    superseded = stores.ws.query_one(
        "SELECT COUNT(*) AS n FROM financial_observations WHERE entity_id = ? "
        "AND metric = 'net_income' AND period_end = '2025-12-31' "
        "AND superseded_by IS NOT NULL", (eid,))
    assert superseded["n"] == 1
    margins = {r["period_end"]: r["value"] for r in
               stores.financial.observations(eid, "net_margin", period_type="annual")}
    assert margins["2025-12-31"] == pytest.approx(150.0 / 1200.0)
    assert stores.financial.latest(eid)["revenue"] == 1200.0
    assert stores.financial.latest(eid)["net_income"] == 150.0  # restated FY wins


def test_sync_companyfacts_from_local_zip(stores, cache, monkeypatch):
    monkeypatch.setattr(sec_bulk, "_fetch_json", lambda url, timeout: {
        "0": {"cik_str": 1234567, "ticker": "SYNX", "title": "Synthetic Inc"}})
    with zipfile.ZipFile(cache / "companyfacts.zip", "w") as zf:
        zf.writestr("CIK0001234567.json", json.dumps(SYN_FACTS))
    out = _run(sec_bulk.sync_companyfacts(stores, ["SYNX", "NOPE"]))
    assert out == {"companies": 1, "universe": 1}
    ent = stores.identity.resolve_ticker("SYNX")
    assert ent["cik"] == "1234567" and ent["name"] == "Synthetic Inc"
    assert stores.financial.latest(ent["id"])["revenue"] == 1200.0  # FY, not Q1
    # The CIK map was cached in the cache dir, not the workspace.
    assert (cache / "company_tickers.json").exists()


# --- daily form index -------------------------------------------------------------------

IDX_TEXT = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    June 10, 2026

Form Type   Company Name        CIK       Date Filed  File Name
---------------------------------------------------------------------------
10-Q        Synthetic Inc       1234567   20260610    edgar/data/1234567/0001234567-26-000042.txt
4           Synthetic Inc       1234567   20260610    edgar/data/1234567/0001234567-26-000043.txt
S-1         Other Co            9999999   20260610    edgar/data/9999999/0009999999-26-000001.txt
"""


def test_parse_form_index_keeps_known_forms():
    rows = sec_index.parse_form_index(IDX_TEXT)
    assert [r["form"] for r in rows] == ["10-Q", "4"]  # S-1 not in KEEP_FORMS
    assert rows[0] == {
        "form": "10-Q", "company": "Synthetic Inc", "cik": "1234567",
        "filed_at": "2026-06-10",
        "file_name": "edgar/data/1234567/0001234567-26-000042.txt",
        "accession": "0001234567-26-000042",
    }


def test_sync_daily_indexes_idempotent(stores, monkeypatch):
    stores.identity.ensure_entity("SYNX", name="Synthetic Inc", cik="1234567")
    monkeypatch.setattr(sec_index, "_fetch_index_text", lambda day: IDX_TEXT)
    since = (_today() - timedelta(days=7)).isoformat()
    out = _run(sec_index.sync_daily_indexes(stores, since))
    assert out["days_checked"] >= 4
    assert out["filings_added"] == 2  # unknown CIK filtered; dupes idempotent
    filings = stores.bulk.filings_for("SYNX")
    assert {f["form"] for f in filings} == {"10-Q", "4"}
    assert all(f["entity_id"] for f in filings)
    # Second run: same accessions, nothing added.
    out2 = _run(sec_index.sync_daily_indexes(stores, since))
    assert out2["filings_added"] == 0
    assert stores.bulk.get_state("last_index_date") == _today().isoformat()


# --- daily tick orchestration -------------------------------------------------------------

def test_daily_tick_topups_and_thesis_health(stores, monkeypatch):
    stores.identity.ensure_entity("SYNX", name="Synthetic Inc", cik="1234567")
    stores.bulk.set_state("price_depth_years", "5")  # already at depth → incremental path
    monkeypatch.setattr(sec_index, "_fetch_index_text", lambda day: IDX_TEXT)
    monkeypatch.setattr(ingest_sync, "universe_tickers", lambda: ["SYNX"])

    topped: list[str] = []

    async def fake_topup(s, ticker):
        topped.append(ticker)
        return {"facts": 1, "observations": 1}

    monkeypatch.setattr(sec_bulk, "topup_company", fake_topup)

    health_calls: list[tuple] = []
    monkeypatch.setattr(
        thesis_health, "refresh_for",
        lambda s, tickers, trigger="filing": health_calls.append((list(tickers), trigger)),
        raising=False)

    price_calls: list[tuple] = []

    async def fake_prices(s, tickers, **kwargs):
        price_calls.append((list(tickers), kwargs))
        return {"tickers": len(tickers), "rows": 0}

    monkeypatch.setattr(ingest_sync, "_load_price_sync", lambda: fake_prices)

    bench_calls: list[dict] = []

    async def fake_bench(s, **kwargs):
        bench_calls.append(kwargs)
        return {"tickers": 2, "rows": 0}

    monkeypatch.setattr(ingest_sync, "_load_benchmark_sync", lambda: fake_bench)
    monkeypatch.setattr(ingest_sync, "_load_events_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_macro_sync", lambda: None)

    summary = _run(ingest_sync.daily_tick(stores))
    assert summary["index"]["filings_added"] == 2
    assert summary["topped_up"] == ["SYNX"]  # one top-up despite repeated filings
    assert health_calls == [(["SYNX"], "filing")]
    assert price_calls == [(["SYNX"], {"incremental": True})]
    assert bench_calls == [{"incremental": True}]  # index series ride the tick
    # The 10-Q got processed; the form 4 is not fundamentals work.
    assert stores.bulk.unprocessed_filings(forms=["10-Q"]) == []
    assert stores.bulk.get_state("last_daily_tick")


def test_daily_tick_failed_topup_stays_unprocessed(stores, monkeypatch):
    stores.identity.ensure_entity("SYNX", name="Synthetic Inc", cik="1234567")
    monkeypatch.setattr(sec_index, "_fetch_index_text", lambda day: IDX_TEXT)
    monkeypatch.setattr(ingest_sync, "universe_tickers", lambda: ["SYNX"])
    monkeypatch.setattr(ingest_sync, "_load_price_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_benchmark_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_events_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_macro_sync", lambda: None)

    async def offline_topup(s, ticker):
        return None  # degraded: offline

    monkeypatch.setattr(sec_bulk, "topup_company", offline_topup)
    summary = _run(ingest_sync.daily_tick(stores))
    assert summary["topped_up"] == []
    assert len(stores.bulk.unprocessed_filings(forms=["10-Q"])) == 1  # retried next tick


# --- bootstrap stage progression ------------------------------------------------------------

def _bootstrap_fakes(monkeypatch, calls: dict):
    # Deterministic operational config regardless of the developer's machine.
    monkeypatch.setattr(
        opconfig, "load", lambda refresh=False: copy.deepcopy(opconfig.DEFAULTS))
    monkeypatch.setattr(ingest_sync, "load_preset", lambda name: ["SYNX", "ZZZZ"])

    async def fake_cik(s, tickers):
        calls["cik"] = list(tickers)
        s.identity.ensure_entity("SYNX", name="Synthetic Inc", cik="1234567")
        return {"SYNX": 1234567}

    async def fake_facts(s, tickers, progress_cb=None):
        calls["facts"] = list(tickers)
        if progress_cb:
            progress_cb(1, 1)
        return {"companies": 1, "universe": 1}

    async def fake_idx(s, since):
        calls["idx"] = str(since)
        return {"days_checked": 5, "filings_added": 0}

    async def fake_prices(s, tickers, **kwargs):
        calls.setdefault("prices", []).append((list(tickers), kwargs))
        return {"tickers": len(tickers), "rows": 9}

    async def fake_bench(s, **kwargs):
        calls.setdefault("benchmarks", []).append(kwargs)
        return {"tickers": 2, "rows": 9}

    monkeypatch.setattr(sec_bulk, "sync_cik_map", fake_cik)
    monkeypatch.setattr(sec_bulk, "sync_companyfacts", fake_facts)
    monkeypatch.setattr(sec_index, "sync_daily_indexes", fake_idx)
    monkeypatch.setattr(ingest_sync, "_load_price_sync", lambda: fake_prices)
    monkeypatch.setattr(ingest_sync, "_load_benchmark_sync", lambda: fake_bench)
    monkeypatch.setattr(ingest_sync, "_load_ownership_sync", lambda: None)


def test_bootstrap_stage_progression(stores, monkeypatch):
    calls: dict = {}
    _bootstrap_fakes(monkeypatch, calls)
    stages: list[str] = []
    real_set = stores.bulk.set_state

    def spy_set_state(key, value):
        if key == "bootstrap_stage":
            stages.append(value)
        real_set(key, value)

    monkeypatch.setattr(stores.bulk, "set_state", spy_set_state)

    out = _run(ingest_sync.bootstrap(stores))
    assert out["ok"] is True and out["errors"] == []
    assert stages == ["universe", "companyfacts", "prices", "ownership",
                      "indexes", "reconcile", "done"]
    assert calls["cik"] == calls["facts"] == ["SYNX", "ZZZZ"]
    # 5y universe bars (data.price_history_years) feed momentum/volatility.
    assert calls["prices"] == [(["SYNX", "ZZZZ"], {"years": 5})]
    snap = stores.bulk.state_snapshot()
    assert snap["bootstrap_done"] == "1"
    assert snap["bootstrap_running"] == "0"
    assert snap["last_bulk_refresh"] and snap["last_daily_tick"]
    assert json.loads(snap["bootstrap_progress"])["stage"] == "companyfacts"
    assert out["ownership"]["note"] == "ownership ingestion module not available"


def test_bootstrap_stage_failure_persists_completed_work(stores, monkeypatch):
    calls: dict = {}
    _bootstrap_fakes(monkeypatch, calls)

    async def boom(s, tickers, progress_cb=None):
        raise RuntimeError("zip corrupt")

    monkeypatch.setattr(sec_bulk, "sync_companyfacts", boom)
    out = _run(ingest_sync.bootstrap(stores))
    assert out["ok"] is False
    snap = stores.bulk.state_snapshot()
    assert snap.get("bootstrap_done") != "1"
    assert snap["bootstrap_stage"] == "failed"
    assert "companyfacts: zip corrupt" in snap["bootstrap_error"]
    assert snap["bootstrap_running"] == "0"
    # Earlier stage persisted, later stages still ran.
    assert calls["cik"] == ["SYNX", "ZZZZ"]
    assert calls["idx"]
    assert stores.identity.resolve_ticker("SYNX")["cik"] == "1234567"


# --- screener universe resolution -------------------------------------------------------------

def test_screener_resolves_default_universe_and_local_screening(
        stores, offline_ai, monkeypatch):
    captured: dict = {}

    def fake_preset(name):
        captured["preset"] = name
        return ["AAA", "BBB"]

    async def fake_metrics_for(self, tickers, allow_fetch=True, concurrency=4):
        captured["tickers"] = list(tickers)
        captured["allow_fetch"] = allow_fetch
        return {}

    monkeypatch.setattr(screener, "load_preset", fake_preset)
    monkeypatch.setattr(MarketDataService, "metrics_for", fake_metrics_for)

    # No constitution universe: data.universe_default resolves via load_preset.
    _run(screener.run_screener(stores))
    assert captured["preset"] == opconfig.load()["data"]["universe_default"]
    assert captured["tickers"] == ["AAA", "BBB"]
    assert captured["allow_fetch"] is True  # bootstrap not done yet: live fetch ok

    # After bootstrap, screening must never make live calls.
    stores.bulk.set_state("bootstrap_done", "1")
    _run(screener.run_screener(stores))
    assert captured["allow_fetch"] is False


def test_derive_computes_roic_and_gross_profit_fallback():
    """ROIC and a gross-profit fallback are derived so strategies that screen on
    them have coverage even when GrossProfit isn't tagged (regression: 0 ROIC
    coverage made every Russell 2000 screen pass 0 candidates)."""
    from backend.services.ingest.sec_bulk import _derive

    # ROIC = NOPAT / invested capital; invested = debt + equity.
    d = _derive({"operating_income": 200.0, "total_equity": 800.0, "total_debt": 200.0})
    assert abs(d["roic"] - (200 * (1 - 0.21) / 1000)) < 1e-9

    # Effective tax rate used when income-tax inputs exist.
    d2 = _derive({"operating_income": 200.0, "total_equity": 800.0,
                  "income_tax": 30.0, "pretax_income": 180.0})
    assert abs(d2["roic"] - (200 * (1 - 30 / 180) / 800)) < 1e-9

    # Gross profit derived from revenue - cost_of_revenue when not reported.
    d3 = _derive({"revenue": 1000.0, "cost_of_revenue": 550.0})
    assert d3["gross_profit"] == 450.0 and d3["gross_margin"] == 0.45

    # A directly reported gross profit is preferred over the fallback.
    d4 = _derive({"revenue": 1000.0, "gross_profit": 480.0, "cost_of_revenue": 550.0})
    assert d4["gross_margin"] == 0.48


def test_daily_tick_price_depth_catchup(stores, monkeypatch):
    """A workspace whose stored price depth is shallower than configured gets
    one full-window refetch (benchmarks included) instead of the incremental
    pass; the watermark then keeps later ticks incremental."""
    monkeypatch.setattr(sec_index, "_fetch_index_text", lambda day: None)
    monkeypatch.setattr(ingest_sync, "universe_tickers", lambda: ["SYNX"])
    monkeypatch.setattr(ingest_sync, "_load_events_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_macro_sync", lambda: None)
    monkeypatch.setattr(ingest_sync, "_load_ownership_sync", lambda: None)

    price_calls: list[tuple] = []

    async def fake_prices(s, tickers, **kwargs):
        price_calls.append((list(tickers), kwargs))
        return {"tickers": len(tickers), "rows": 5, "failed_chunks": 0}

    monkeypatch.setattr(ingest_sync, "_load_price_sync", lambda: fake_prices)

    bench_calls: list[dict] = []

    async def fake_bench(s, **kwargs):
        bench_calls.append(kwargs)
        return {"tickers": 2, "rows": 0, "failed_chunks": 0}

    monkeypatch.setattr(ingest_sync, "_load_benchmark_sync", lambda: fake_bench)

    # No watermark: tick runs the depth catch-up (full window, not incremental).
    summary = _run(ingest_sync.daily_tick(stores))
    assert price_calls == [(["SYNX"], {"years": 5.0})]
    assert bench_calls == [{}]  # full benchmark sync rode the catch-up
    assert summary["prices"]["depth_backfill"] == "0y -> 5y"
    assert stores.bulk.get_state("price_depth_years") == "5.0"

    # Watermark recorded: the next tick is incremental again.
    price_calls.clear(); bench_calls.clear()
    _run(ingest_sync.daily_tick(stores))
    assert price_calls == [(["SYNX"], {"incremental": True})]
    assert bench_calls == [{"incremental": True}]


def test_price_depth_catchup_retries_after_failed_chunks(stores, monkeypatch):
    """Failed chunks must not advance the depth watermark — the catch-up
    retries on the next tick instead of stranding part of the universe."""
    monkeypatch.setattr(ingest_sync, "universe_tickers", lambda: ["SYNX"])

    async def flaky_prices(s, tickers, **kwargs):
        return {"tickers": 0, "rows": 0, "failed_chunks": 2}

    monkeypatch.setattr(ingest_sync, "_load_price_sync", lambda: flaky_prices)
    monkeypatch.setattr(ingest_sync, "_load_benchmark_sync", lambda: None)

    out = _run(ingest_sync.ensure_price_depth(stores))
    assert out["note"].startswith("some chunks failed")
    assert stores.bulk.get_state("price_depth_years") is None
    # Still pending: a later call tries again.
    assert _run(ingest_sync.ensure_price_depth(stores)) is not None


def test_sector_backfill_classifies_and_bails_offline(stores, monkeypatch):
    """Sector backfill maps SIC → sector and sicDescription → industry for
    entities missing classification; unclassifiable filers become 'Unknown'
    (never refetched); an offline run bails after consecutive failures."""
    from backend.services.ingest import sectors

    stores.identity.ensure_entity("PHRM", name="Pharma Co", cik="111")
    stores.identity.ensure_entity("SOFT", name="Soft Co", cik="222")
    stores.identity.ensure_entity("BLNK", name="Blank Co", cik="333")
    stores.identity.ensure_entity("NOCK", name="No CIK Co")  # skipped: no cik

    subs = {
        "111": {"sic": "2834", "sicDescription": "PHARMACEUTICAL PREPARATIONS"},
        "222": {"sic": "7372", "sicDescription": "Services-Prepackaged Software"},
        "333": {},  # filer with no SIC → "Unknown", not NULL
    }
    monkeypatch.setattr(sectors, "_fetch_submissions", lambda cik: subs[str(cik)])
    monkeypatch.setattr(sectors, "PACING_S", 0)

    out = _run(sectors.backfill_sectors(stores))
    assert out == {"classified": 3, "failed": 0}
    assert stores.identity.resolve_ticker("PHRM")["sector"] == "Pharmaceuticals & Biotech"
    assert stores.identity.resolve_ticker("PHRM")["industry"] == "Pharmaceutical Preparations"
    assert stores.identity.resolve_ticker("PHRM")["sic"] == "2834"
    assert stores.identity.resolve_ticker("SOFT")["sector"] == "Software & IT Services"
    assert stores.identity.resolve_ticker("BLNK")["sector"] == "Unknown"
    assert stores.identity.resolve_ticker("BLNK")["sic"] is None
    assert stores.identity.resolve_ticker("NOCK")["sector"] is None

    # Everything classified → second pass is a no-op (no fetches).
    monkeypatch.setattr(sectors, "_fetch_submissions",
                        lambda cik: (_ for _ in ()).throw(AssertionError("refetched")))
    assert _run(sectors.backfill_sectors(stores)) == {"classified": 0, "failed": 0}

    # Offline: consecutive failures with no successes bail out early.
    for t, c in (("AAA1", "881"), ("AAA2", "882"), ("AAA3", "883"), ("AAA4", "884")):
        stores.identity.ensure_entity(t, cik=c)

    calls = []

    def down(cik):
        calls.append(cik)
        raise OSError("offline")

    monkeypatch.setattr(sectors, "_fetch_submissions", down)
    out = _run(sectors.backfill_sectors(stores))
    assert out["classified"] == 0 and out["failed"] == 3
    assert len(calls) == 3  # bailed before the 4th\n

def test_peers_widen_by_sic_tiers(stores):
    """A company whose exact industry has too few members widens to the
    3-digit / 2-digit SIC group before falling back to broad sector."""
    from backend.services.research_hub import peers_for

    stores.identity.ensure_entity("SODA", name="Soda Co", sector="Food, Beverage & Tobacco",
                                  industry="Beverages", sic="2086")
    # Same 3-digit group (208x beverages), different exact industry label.
    stores.identity.ensure_entity("BREW", name="Brew Co", sector="Food, Beverage & Tobacco",
                                  industry="Malt Beverages", sic="2082")
    stores.identity.ensure_entity("WINE", name="Wine Co", sector="Food, Beverage & Tobacco",
                                  industry="Wines & Distilled Beverages", sic="2084")
    stores.identity.ensure_entity("BAKE", name="Bake Co", sector="Food, Beverage & Tobacco",
                                  industry="Bakery Products", sic="2050")
    # Same broad sector division would also include this under the OLD scheme;
    # the SIC tiers must not reach it.
    stores.identity.ensure_entity("CHIP", name="Chip Co",
                                  sector="Electronics & Semiconductors",
                                  industry="Semiconductors", sic="3674")
    for t in ("SODA", "BREW", "WINE", "BAKE", "CHIP"):
        ent = stores.identity.resolve_ticker(t)
        stores.financial.add_observation(ent["id"], "gross_margin",
                                         "2025-12-31", "annual", 0.5)

    tickers = [p["ticker"] for p in peers_for(stores, "SODA")]
    assert tickers[0] == "SODA"          # subject first
    assert "BREW" in tickers and "WINE" in tickers  # 208x beverage group
    assert "CHIP" not in tickers         # never the semiconductor maker
