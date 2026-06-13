"""Market-context routes: upcoming events, watchlists/themes, macro strip.
All reads are local-only (stored events, cached macro series); ingestion
happens on the daily tick, never on page views."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import macro
from backend.services.ingest import events as events_service
from backend.stores import get_stores

router = APIRouter()


# --- events ---------------------------------------------------------------------

@router.get("/events/upcoming")
async def upcoming_events(days: int = 45):
    return {"events": events_service.upcoming_view(get_stores(), days_ahead=days)}


# --- macro ----------------------------------------------------------------------

@router.get("/macro")
async def macro_strip():
    return {"series": macro.macro_strip(get_stores())}


@router.get("/macro/{series}")
async def macro_series(series: str, limit: int = 260):
    limit = max(1, min(limit, 2000))
    series = series.upper()
    if series not in macro.MACRO_SERIES:
        raise HTTPException(status_code=404, detail=f"unknown macro series {series}")
    label, kind = macro.MACRO_SERIES[series]
    return {"series": series, "label": label, "kind": kind,
            "points": macro.macro_history(get_stores(), series, limit=limit)}


# --- watchlists & themes -----------------------------------------------------------

class WatchlistIn(BaseModel):
    name: str
    kind: str = "watchlist"   # watchlist | theme
    note: str | None = None
    tickers: list[str] = []


class TickerIn(BaseModel):
    ticker: str


def _snapshot_rows(stores, tickers: list[str]) -> list[dict]:
    """Snapshot metrics + health chips for watchlist rows. Pure local read."""
    from backend.workflows import thesis_health  # lazy: avoids import cycles

    prices = stores.portfolio.prices()
    held = {h["ticker"] for h in stores.portfolio.holdings()}
    rows = []
    for t in tickers:
        ent = stores.identity.resolve_ticker(t)
        latest = stores.financial.latest(ent["id"]) if ent else {}
        rows.append({
            "ticker": t,
            "name": (ent or {}).get("name"),
            "price": prices.get(t),
            "momentum_3m": latest.get("momentum_3m"),
            "pe": latest.get("pe"),
            "fcf_yield": latest.get("fcf_yield"),
            "market_cap": latest.get("market_cap"),
            "owned": t in held,
            "thesis_health": thesis_health.summary_for(stores, t),
        })
    return rows


@router.get("/watchlists")
async def list_watchlists(kind: str | None = None):
    stores = get_stores()
    out = []
    for wl in stores.context.list_watchlists(kind):
        out.append({**wl, "rows": _snapshot_rows(stores, wl["tickers"])})
    return {"watchlists": out}


def _reject_unknown_tickers(stores, tickers: list[str]) -> None:
    """Watchlists hold real, locally-known companies — silently storing junk
    tickers would render rows of dashes and pollute snapshot queries."""
    unknown = [str(t).upper() for t in tickers
               if not stores.identity.resolve_ticker(str(t).upper())]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown ticker(s): {', '.join(unknown)} — only tickers "
                   "with retained FundOps identity can be added")


@router.post("/watchlists")
async def create_watchlist(body: WatchlistIn):
    stores = get_stores()
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.kind not in ("watchlist", "theme"):
        raise HTTPException(status_code=400, detail="kind must be watchlist|theme")
    if stores.context.watchlist_by_name(body.name):
        raise HTTPException(status_code=409, detail="a list with that name exists")
    _reject_unknown_tickers(stores, body.tickers)
    wl = stores.context.create_watchlist(body.name, kind=body.kind, note=body.note)
    for t in body.tickers:
        stores.context.add_ticker(wl["id"], t)
    return stores.context.get_watchlist(wl["id"])


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(watchlist_id: str):
    stores = get_stores()
    if not stores.context.get_watchlist(watchlist_id):
        raise HTTPException(status_code=404, detail="unknown watchlist")
    stores.context.delete_watchlist(watchlist_id)
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/tickers")
async def add_watchlist_ticker(watchlist_id: str, body: TickerIn):
    stores = get_stores()
    if not stores.context.get_watchlist(watchlist_id):
        raise HTTPException(status_code=404, detail="unknown watchlist")
    if not body.ticker.strip():
        raise HTTPException(status_code=400, detail="ticker is required")
    _reject_unknown_tickers(stores, [body.ticker.strip()])
    stores.context.add_ticker(watchlist_id, body.ticker.strip())
    return stores.context.get_watchlist(watchlist_id)


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}")
async def remove_watchlist_ticker(watchlist_id: str, ticker: str):
    stores = get_stores()
    if not stores.context.get_watchlist(watchlist_id):
        raise HTTPException(status_code=404, detail="unknown watchlist")
    stores.context.remove_ticker(watchlist_id, ticker)
    return stores.context.get_watchlist(watchlist_id)
