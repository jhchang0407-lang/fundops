"""Research Hub routes: sector/industry browser, deterministic dashboards,
theme dashboards, and (Phase 4) bounded research runs producing cited
artifacts."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from backend.services import research_hub
from backend.stores import get_stores

router = APIRouter()


@router.get("/research/sectors")
async def sectors_tree():
    return {"sectors": get_stores().identity.industry_tree()}


@router.get("/research/industry")
async def industry_dashboard(sector: str | None = None, industry: str | None = None):
    if not sector and not industry:
        raise HTTPException(status_code=400, detail="sector or industry is required")
    return research_hub.industry_dashboard(get_stores(), sector, industry)


@router.get("/research/theme/{watchlist_id}")
async def theme_dashboard(watchlist_id: str):
    out = research_hub.theme_dashboard(get_stores(), watchlist_id)
    if out is None:
        raise HTTPException(status_code=404, detail="unknown theme")
    return out


class ResearchRunIn(BaseModel):
    kind: str                     # industry_note | risk_landscape | peer_deep_dive
    sector: str | None = None
    industry: str | None = None
    watchlist_id: str | None = None
    tickers: list[str] = []
    label: str | None = None      # display label for ad-hoc ticker scopes


@router.post("/research/runs")
async def start_research_run(body: ResearchRunIn):
    """Bounded AI research run over a peer group (Phase 4 harness)."""
    from backend.workflows import research_runs

    stores = get_stores()
    try:
        tickers, group_total = research_runs.resolve_scope(
            stores, body.sector, body.industry, body.watchlist_id, body.tickers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if body.kind not in research_runs.RUN_KINDS:
        raise HTTPException(status_code=400,
                            detail=f"kind must be one of {sorted(research_runs.RUN_KINDS)}")
    label = body.label or body.industry or body.sector or "custom"
    if body.watchlist_id and not (body.label or body.industry or body.sector):
        wl = stores.context.get_watchlist(body.watchlist_id)
        label = wl["name"] if wl else "custom"
    result = await research_runs.run(stores, body.kind, tickers,
                                     group_label=label, group_total=group_total)
    return result


@router.post("/research/thematic")
async def thematic_research(body: dict = Body(...)):
    """Thematic deep research (SEC-only, bounded): discover a company set for a
    free-text theme, deep-read each one's 10-K Business/Risk/MD&A, synthesize a
    cited market report."""
    from backend.workflows import research_runs

    query = str(body.get("query") or body.get("q") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    limit = body.get("limit")
    limit = min(int(limit), research_runs.THEME_COMPANY_CAP) if isinstance(limit, int) and limit > 0 \
        else research_runs.THEME_COMPANY_CAP
    return await research_runs.run_thematic(get_stores(), query, limit=limit)


@router.get("/research/fulltext")
async def fulltext_search(q: str, forms: str | None = None):
    """Thematic EDGAR full-text search: who mentions X. Live, not retained."""
    from backend.services.fulltext_search import search_filings

    form_list = [f.strip() for f in forms.split(",") if f.strip()] if forms else None
    try:
        return await search_filings(get_stores(), q, form_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/research/notes")
async def research_notes(limit: int = 20):
    """Recent research-note artifacts (industry notes, filing notes)."""
    limit = max(1, min(limit, 200))
    stores = get_stores()
    notes = []
    for kind in ("industry_note", "filing_note"):
        for meta in stores.artifacts.recent(kind=kind, limit=limit):
            art = stores.artifacts.get(meta["id"]) or {}
            body = (art.get("payload") or {}).get("body") or {}
            notes.append({"id": meta["id"], "kind": meta["kind"],
                          "ticker": meta.get("ticker"),
                          "created_at": meta["created_at"],
                          "title": body.get("title") or meta.get("ticker") or kind})
    notes.sort(key=lambda n: n["created_at"], reverse=True)
    return {"notes": notes[:limit]}
