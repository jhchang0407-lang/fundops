"""Workflow routes (docs/api-contract.md — Workflows, /api/runs,
/api/research/directed).

Routes are thin: parse → call workflow fns → return dicts. Long runs are
kicked as asyncio background tasks (handles kept in a module-level dict);
*/current endpoints read workbench state and never spend AI.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable

from fastapi import APIRouter, Body, HTTPException

from backend.services.market_data import MarketDataService
from backend.stores import get_stores
from backend.workflows import ic_review, memo, pipeline, screener, thesis

router = APIRouter()

_tasks: dict[str, asyncio.Task] = {}


def _kick(run_id: str, coro: Awaitable) -> str:
    task = asyncio.create_task(coro)
    _tasks[run_id] = task
    task.add_done_callback(lambda _t: _tasks.pop(run_id, None))
    return run_id


_FUNNEL_KINDS = ("pipeline", "screener", "thesis", "ic_review", "memo")


def _already_running(stores, kind: str) -> dict | None:
    """Return an in-flight run of this kind so the route reuses it instead of
    stacking a duplicate (double-clicks, or a second pipeline over a live one)."""
    existing = stores.runs.active_run_id(kind)
    if existing:
        return {"run_id": existing, "already_running": True}
    return None


def _selection_args(body: dict) -> tuple[str, str]:
    ticker = str(body.get("ticker") or "").upper().strip()
    action = str(body.get("action") or "").strip()
    if not ticker:
        raise HTTPException(400, "ticker is required")
    return ticker, action


# --- Screener ----------------------------------------------------------------------

@router.post("/workflows/screener/run")
async def screener_run() -> dict:
    stores = get_stores()
    if busy := _already_running(stores, "screener"):
        return busy
    rid = screener.prepare_run(stores, trigger="user")
    _kick(rid, screener.execute_run(stores, rid))
    return {"run_id": rid}


@router.get("/workflows/screener/current")
async def screener_current() -> dict:
    return screener.screener_current(get_stores())


@router.post("/workflows/screener/selection")
async def screener_selection(body: dict = Body(...)) -> dict:
    ticker, action = _selection_args(body)
    try:
        return screener.screener_select(get_stores(), ticker, action)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# --- Thesis ------------------------------------------------------------------------

@router.post("/workflows/thesis/run")
async def thesis_run() -> dict:
    stores = get_stores()
    if busy := _already_running(stores, "thesis"):
        return busy
    rid = thesis.prepare_run(stores, trigger="user")
    _kick(rid, thesis.execute_run(stores, rid))
    return {"run_id": rid}


@router.get("/workflows/thesis/current")
async def thesis_current() -> dict:
    return thesis.thesis_current(get_stores())


@router.post("/workflows/thesis/selection")
async def thesis_selection(body: dict = Body(...)) -> dict:
    ticker, action = _selection_args(body)
    try:
        return thesis.thesis_select(get_stores(), ticker, action)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# --- IC Review ----------------------------------------------------------------------

@router.post("/workflows/ic/run")
async def ic_run() -> dict:
    stores = get_stores()
    if busy := _already_running(stores, "ic_review"):
        return busy
    rid = ic_review.prepare_run(stores, trigger="user")
    _kick(rid, ic_review.execute_run(stores, rid))
    return {"run_id": rid}


@router.get("/workflows/ic/current")
async def ic_current() -> dict:
    return ic_review.ic_current(get_stores())


@router.post("/workflows/ic/override")
async def ic_override(body: dict = Body(...)) -> dict:
    ticker, action = _selection_args(body)
    try:
        return ic_review.ic_override(get_stores(), ticker, action)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# --- Memo --------------------------------------------------------------------------

@router.post("/workflows/memo/run")
async def memo_run(body: dict | None = Body(None)) -> dict:
    ticker = ((body or {}).get("ticker") or None)
    stores = get_stores()
    if busy := _already_running(stores, "memo"):
        return busy
    rid = memo.prepare_run(stores, trigger="user")
    _kick(rid, memo.execute_run(stores, rid, ticker=ticker))
    return {"run_id": rid}


@router.get("/workflows/memo/current")
async def memo_current() -> dict:
    return memo.memo_current(get_stores())


# --- Pipeline ----------------------------------------------------------------------

@router.post("/workflows/pipeline/run")
async def pipeline_run() -> dict:
    stores = get_stores()
    # The pipeline drives its own screener/thesis/ic/memo runs, so refuse to
    # start while ANY funnel work is in flight — that's what stacked the
    # duplicate runs before.
    for kind in _FUNNEL_KINDS:
        if existing := stores.runs.active_run_id(kind):
            return {"run_id": existing, "already_running": True, "blocked_by": kind}
    rid = pipeline.prepare_run(stores, trigger="user")
    _kick(rid, pipeline.execute_run(stores, rid))
    return {"run_id": rid}


# --- Runs --------------------------------------------------------------------------

@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    stores = get_stores()
    run = stores.runs.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    return {"run": run, "steps": stores.runs.steps_for(run_id)}


@router.get("/runs")
async def list_runs(limit: int = 30) -> list[dict]:
    limit = max(1, min(limit, 500))
    return get_stores().runs.recent_runs(limit=limit)


# --- Directed research ----------------------------------------------------------------

@router.post("/research/directed")
async def directed_research(body: dict = Body(...)) -> dict:
    """Start research at Thesis or Memo for a validated ticker with
    user-directed provenance (bypasses the screener funnel)."""
    ticker = str(body.get("ticker") or "").upper().strip()
    capability = body.get("capability")
    if not ticker:
        raise HTTPException(400, "ticker is required")
    if capability not in ("thesis", "memo"):
        raise HTTPException(400, "capability must be 'thesis' or 'memo'")
    stores = get_stores()
    data = await MarketDataService(stores).fetch_fundamentals(ticker)
    if not data:
        raise HTTPException(404, f"unknown ticker {ticker}: no fundamentals available")
    if capability == "thesis":
        intake = stores.runs.get_workbench(thesis.INTAKE_KEY) or {"items": []}
        items = intake.get("items") or []
        if ticker not in {str(i.get("ticker")).upper() for i in items}:
            items.append({"ticker": ticker, "provenance": "directed"})
        intake["items"] = items
        intake["tickers"] = [i["ticker"] for i in items]
        stores.runs.set_workbench(thesis.INTAKE_KEY, intake)
        rid = thesis.prepare_run(stores, trigger="directed")
        _kick(rid, thesis.execute_run(stores, rid, tickers=[ticker]))
    else:
        rid = memo.prepare_run(stores, trigger="directed")
        _kick(rid, memo.execute_run(stores, rid, ticker=ticker, provenance="directed"))
    return {"run_id": rid}
