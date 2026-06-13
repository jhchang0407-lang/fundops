"""Web research: gating, provider selection, context rendering, and the
augmentation wiring into thesis / memo / thematic research.

No network anywhere: provider fetchers are monkeypatched; the OFF state is
pinned to do nothing (the toggle must mean no requests at all).
"""

from __future__ import annotations

import pytest

from backend.core import opconfig, web_research


@pytest.fixture
def web_off(monkeypatch):
    monkeypatch.setattr(web_research, "enabled", lambda: False)


@pytest.fixture
def web_on_ddg(monkeypatch):
    """Toggle on, no keys → keyless DuckDuckGo backend with a fake fetcher."""
    monkeypatch.setattr(web_research, "enabled", lambda: True)
    monkeypatch.setattr(opconfig, "secret", lambda name, env=None: None)
    monkeypatch.setattr(
        web_research, "_search_ddg",
        lambda q, n: [{"title": f"Result for {q}", "url": "https://example.com/a",
                       "snippet": "snippet text"}][:n])


# --- gating + provider selection ----------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_toggle_means_no_search(web_off):
    out = await web_research.search("anything")
    assert out["provider"] is None and out["results"] == []
    assert "disabled" in out["note"]


def test_provider_selection_prefers_keys(monkeypatch):
    monkeypatch.setattr(web_research, "enabled", lambda: True)
    monkeypatch.setattr(opconfig, "secret",
                        lambda name, env=None: "k" if name == "brave" else None)
    assert web_research.active_provider() == "brave"
    monkeypatch.setattr(opconfig, "secret", lambda name, env=None: None)
    assert web_research.active_provider() == "ddg"


@pytest.mark.asyncio
async def test_search_failure_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(web_research, "enabled", lambda: True)
    monkeypatch.setattr(opconfig, "secret", lambda name, env=None: None)
    def boom(q, n):
        raise OSError("offline")
    monkeypatch.setattr(web_research, "_search_ddg", boom)
    out = await web_research.search("x")
    assert out["results"] == [] and "unavailable" in out["note"]


def test_context_block_uses_w_numbering():
    block, sources = web_research.context_block(
        [{"title": "T1", "url": "https://a", "snippet": "s1"},
         {"title": "T2", "url": "https://b", "snippet": ""}])
    assert block.splitlines()[0].startswith("[W1] T1")
    assert sources == ["[W1] T1 — https://a", "[W2] T2 — https://b"]


# --- wiring: thematic synthesis carries web sources when enabled --------------------

@pytest.mark.asyncio
async def test_thematic_report_includes_web_sources(
        stores, offline_ai, monkeypatch, web_on_ddg):
    from backend.services import fulltext_search
    from backend.workflows import research_runs
    from tests.platform.conftest import FAKE_METRICS, _persist

    for t, m in FAKE_METRICS.items():
        _persist(stores, t, m)

    async def hits(stores, query, forms=None):
        return {"ok": True, "hits": [{"ticker": "AAA", "company": "Alpha", "in_universe": True}]}
    monkeypatch.setattr(fulltext_search, "search_filings", hits)

    async def fake_row(stores, c):
        return {"cik": "1", "accession": "acc-AAA", "form": "10-K",
                "filed_at": "2026-02-01", "ticker": "AAA"}
    from backend.services.ingest import filing_text
    monkeypatch.setattr(research_runs, "_theme_filing_row", fake_row)
    monkeypatch.setattr(filing_text, "fetch_and_cache_sections",
                        lambda stores, f: _async_sections(f))

    out = await research_runs.run_thematic(stores, "widgets", limit=1)
    body = stores.artifacts.get(out["artifact_id"])["payload"]["body"]
    assert any(s.startswith("[W1]") for s in body["sources"])


async def _async_sections(filing):
    return {s: "body " * 50 for s in ("business", "risk_factors", "mdna")}


# --- wiring: the off state keeps thesis/memo prompts SEC-only -----------------------

@pytest.mark.asyncio
async def test_web_off_keeps_workflows_clean(stores, offline_ai, web_off, fake_market,
                                             monkeypatch):
    """With the toggle off, thesis generation must not include web context and
    must not error — the search call returns the disabled sentinel."""
    from backend.workflows import thesis
    stores.runs.set_workbench(thesis.INTAKE_KEY, {"items": [{"ticker": "AAA"}]})
    rid = await thesis.run_thesis(stores, trigger="user", tickers=["AAA"])
    run = stores.runs.get_run(rid)
    assert run["status"] == "completed"
    art = stores.artifacts.recent(kind="thesis", limit=1)
    payload = stores.artifacts.get(art[0]["id"])["payload"]
    assert "web_sources" not in payload["body"]


# --- wiring: memo carries web sources + the retained recency layer ------------------

@pytest.mark.asyncio
async def test_memo_augments_with_web_and_recency(stores, offline_ai, fake_market,
                                                  monkeypatch):
    from backend.core import web_research
    from backend.workflows import memo

    async def fake_search(query, max_results=5, ticker=None):
        return {"provider": "tavily", "note": None, "results": [
            {"title": f"News on {ticker or query}", "url": f"https://n.example/{ticker}",
             "snippet": "recent development"}]}
    monkeypatch.setattr(web_research, "search", fake_search)

    # Seed the retained recency layer: a recent 8-K and a known event.
    ent = stores.identity.ensure_entity("AAA")
    stores.bulk.add_filing(cik="1", ticker="AAA", entity_id=ent["id"], form="8-K",
                           filed_at="2026-06-01", accession="acc-8k-aaa",
                           title="Material event")
    stores.context.upsert_event("AAA", "earnings", "2026-07-15", "Earnings")

    rid = await memo.run_memo(stores, ticker="AAA", provenance="directed")
    assert stores.runs.get_run(rid)["status"] == "completed"
    art = stores.artifacts.recent(kind="investment_memo", limit=1)
    body = stores.artifacts.get(art[0]["id"])["payload"]["body"]
    # Web augmentation persisted with [Wn] sources (deduped across both queries).
    assert body["web_sources"] and body["web_sources"][0].startswith("[W1]")
    # The retained recency layer is in the artifact too.
    rc = body["recent_context"]
    assert {"form": "8-K", "filed": "2026-06-01"} in rc["recent_filings"]
    assert any(e["kind"] == "earnings" for e in rc["known_events"])


@pytest.mark.asyncio
async def test_memo_web_off_is_sec_only(stores, offline_ai, web_off, fake_market):
    from backend.workflows import memo
    rid = await memo.run_memo(stores, ticker="BBB", provenance="directed")
    assert stores.runs.get_run(rid)["status"] == "completed"
    art = stores.artifacts.recent(kind="investment_memo", limit=1)
    body = stores.artifacts.get(art[0]["id"])["payload"]["body"]
    assert "web_sources" not in body