"""Thesis-health monitoring + coverage action routes (api-contract).

Refreshes are user-initiated or scheduled — never page-load side effects."""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.portfolio_service import PortfolioService, process_coverage_queue
from backend.stores import get_stores
from backend.workflows import thesis_health

router = APIRouter()


@router.get("/monitoring/due")
async def monitoring_due():
    tickers = thesis_health.due_tickers(get_stores())
    return {"due": len(tickers), "tickers": tickers}


@router.post("/monitoring/refresh")
async def monitoring_refresh():
    """Manual Thesis Health Refresh — metadata-gated full recalculation."""
    return {"refreshed": thesis_health.refresh_all(get_stores(), trigger="manual")}


@router.post("/monitoring/coverage/check")
async def coverage_check():
    """Queue coverage memos for holdings lacking Fresh Portfolio Thesis
    Coverage, then process the coverage queue."""
    stores = get_stores()
    queued = await PortfolioService(stores).ensure_coverage()
    await process_coverage_queue(stores)
    return {"queued": queued}
