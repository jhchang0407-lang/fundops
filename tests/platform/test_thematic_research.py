"""Thematic deep research (SEC-only, bounded): theme → discover companies via
EDGAR full-text → deep-read each one's 10-K sections → synthesize a cited report.

Offline + deterministic: discovery and filing reads are monkeypatched, AI is the
stub gateway, so the harness's composition (discovery, section reads, source
renumbering, artifact shape, coverage) is what's under test — not model output.
"""

from __future__ import annotations

import pytest

from backend.services import fulltext_search
from backend.services.ingest import filing_text
from backend.workflows import research_runs

from tests.platform.conftest import FAKE_METRICS, _persist


@pytest.fixture
def seeded(stores):
    return {t: _persist(stores, t, m) for t, m in FAKE_METRICS.items()}


@pytest.fixture
def fake_discovery(monkeypatch):
    async def fake_search(stores, query, forms=None):
        return {"query": query, "ok": True, "hits": [
            {"ticker": "AAA", "company": "Alpha Corp", "in_universe": True, "known": True},
            {"ticker": "BBB", "company": "Beta Industries", "in_universe": True, "known": True},
            {"ticker": "AAA", "company": "Alpha Corp", "in_universe": True},  # dup, dropped
            # Off-universe but has a CIK → kept (thematic looks beyond the universe).
            {"ticker": "UMAC", "company": "Unusual Machines", "cik": "1956955"},
            {"ticker": "ZZZZ", "company": "Unknown Co"},  # no identity AND no cik → dropped
            {"ticker": None, "company": "No Ticker Inc"},  # nothing to key on → dropped
        ]}
    monkeypatch.setattr(fulltext_search, "search_filings", fake_search)


@pytest.fixture
def fake_filings(monkeypatch):
    """One filing row + one document fetch per company, all sections present."""
    async def fake_row(stores, c):
        return {"cik": c.get("cik") or "111", "accession": f"acc-{c['ticker']}",
                "form": "10-K", "filed_at": "2026-02-01", "ticker": c["ticker"]}
    async def fake_fetch(stores, filing):
        t = filing["ticker"]
        return {s: f"{t} {s} body — discusses the market at length. " * 8
                for s in ("business", "risk_factors", "mdna")}
    monkeypatch.setattr(research_runs, "_theme_filing_row", fake_row)
    monkeypatch.setattr(filing_text, "fetch_and_cache_sections", fake_fetch)


@pytest.mark.asyncio
async def test_thematic_run_discovers_reads_and_synthesizes(
        stores, offline_ai, seeded, fake_discovery, fake_filings):
    out = await research_runs.run_thematic(stores, "drone market", limit=10)
    assert out["ok"] is True
    # Local companies sort first; the off-universe CIK-bearing one is KEPT.
    assert out["tickers"] == ["AAA", "BBB", "UMAC"]
    assert out["scope"]["deep_read"] == 3
    assert out["scope"]["discovered"] == 3

    art = stores.artifacts.get(out["artifact_id"])
    assert art["kind"] == "industry_note"
    body = art["payload"]["body"]
    assert body["kind"] == "thematic_report"
    assert body["theme"] == "drone market"
    # 3 companies × 3 sections (business/risk/mdna), renumbered into one sequence.
    assert len(body["sources"]) == 9
    assert body["sources"][0].startswith("[1]") and body["sources"][-1].startswith("[9]")
    assert "SEC filings only" in (art["rendered_md"] or "")


@pytest.mark.asyncio
async def test_thematic_respects_company_cap(
        stores, offline_ai, seeded, fake_filings, monkeypatch):
    async def many(stores, query, forms=None):
        return {"ok": True, "hits": [{"ticker": t, "company": t, "in_universe": True}
                                     for t in ("AAA", "BBB", "CCC", "DDD", "FFF")]}
    monkeypatch.setattr(fulltext_search, "search_filings", many)
    out = await research_runs.run_thematic(stores, "anything", limit=2)
    assert out["scope"]["selected"] == 2          # capped
    assert out["scope"]["discovered"] == 5        # but coverage records the full set
    assert len(out["tickers"]) == 2


@pytest.mark.asyncio
async def test_thematic_no_resolvable_companies_is_graceful(
        stores, offline_ai, monkeypatch):
    async def empty(stores, query, forms=None):
        return {"ok": True, "hits": [{"ticker": "ZZZZ", "company": "Unknown"}]}
    monkeypatch.setattr(fulltext_search, "search_filings", empty)
    out = await research_runs.run_thematic(stores, "obscure theme")
    assert out["ok"] is False
    assert "no companies" in out["note"].lower()
    # Even a no-company run is recorded + finalized (no orphan 'running' run).
    run = stores.runs.latest_run("thematic")
    assert run and run["status"] == "completed"
    assert stores.runs.get_workbench("thematic")["note"]


# --- async lifecycle + progress -----------------------------------------------------

def test_prepare_thematic_opens_a_guardable_run(stores):
    rid = research_runs.prepare_thematic(stores, "drones")
    # The concurrency guard (route) keys off active_run_id; the workbench drives the UI.
    assert stores.runs.active_run_id("thematic") == rid
    wb = stores.runs.get_workbench("thematic")
    assert wb["status"] == "running" and wb["theme"] == "drones" and wb["run_id"] == rid
    assert wb["stage"] == "discover"


@pytest.mark.asyncio
async def test_thematic_records_steps_and_workbench(
        stores, offline_ai, seeded, fake_discovery, fake_filings):
    out = await research_runs.run_thematic(stores, "drone market", limit=10)
    assert out["ok"] is True
    run = stores.runs.latest_run("thematic")
    assert run and run["status"] == "completed"
    assert run["stats"]["artifact_id"] == out["artifact_id"]
    assert run["stats"]["deep_read"] == 3
    # Every stage is recorded as a step, in order — this is what the Runs page +
    # progress bar read.
    assert [s["name"] for s in stores.runs.steps_for(run["id"])] == [
        "discover", "read_filings", "web_research", "synthesize", "save"]
    wb = stores.runs.get_workbench("thematic")
    assert wb["status"] == "completed" and wb["stage"] == "done"
    assert wb["artifact_id"] == out["artifact_id"] and wb["selected"] == 3


@pytest.mark.asyncio
async def test_theme_web_merges_dedupes_and_caps(monkeypatch):
    calls: list[str] = []

    async def fake_search(query, max_results=5, ticker=None):
        calls.append(query)
        return {"provider": "x", "note": "", "results": [
            {"title": f"u{len(calls)}", "url": f"http://u/{len(calls)}", "snippet": "s"},
            {"title": "shared", "url": "http://shared", "snippet": "s"},  # repeats across angles
        ]}

    monkeypatch.setattr(research_runs.web_research, "search", fake_search)
    block, sources = await research_runs._theme_web("drone market")
    assert len(calls) == research_runs.THEME_WEB_QUERIES          # one per angle, concurrent
    assert len(sources) == research_runs.THEME_WEB_QUERIES + 1    # 5 unique + 1 shared (deduped)
    assert block and block.count("shared") == 1                  # shared URL appears once
