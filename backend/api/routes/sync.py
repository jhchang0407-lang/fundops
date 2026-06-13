"""Bulk data sync routes (api-contract "Bulk data additions", ADR-0059).

GET /sync is a cheap local read (sync_state + COUNTs + cache size); the POST
endpoints launch bootstrap / daily tick as background tasks so the request
returns immediately while progress lands in sync_state.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException

from backend.core import opconfig
from backend.data.universes import PRESETS, load_preset
from backend.services.ingest import sync as ingest_sync
from backend.stores import get_stores

router = APIRouter()

_tasks: set[asyncio.Task] = set()  # keep background tasks alive until done


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.get("/sync")
async def sync_status():
    stores = get_stores()
    snap = stores.bulk.state_snapshot()
    uni = opconfig.load()["data"]["universe_default"]
    preset = PRESETS.get(uni)
    try:
        universe_count = len(load_preset(uni))
    except (ValueError, OSError):
        universe_count = 0

    def _count(table: str) -> int:
        row = stores.ws.query_one(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608 — fixed names
        return row["n"] if row else 0

    coverage = stores.bulk.price_coverage()
    cache = opconfig.cache_dir()
    cache_bytes = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file())
    try:
        progress = json.loads(snap.get("bootstrap_progress") or "null")
    except ValueError:
        progress = None
    return {
        "bootstrap": {
            "done": snap.get("bootstrap_done") == "1",
            "running": snap.get("bootstrap_running") == "1",
            "stage": snap.get("bootstrap_stage"),
            "progress": progress,
            "error": snap.get("bootstrap_error") or None,
        },
        "last_daily_tick": snap.get("last_daily_tick"),
        "last_bulk_refresh": snap.get("last_bulk_refresh"),
        "universe": {"name": preset["label"] if preset else uni,
                     "count": universe_count},
        "counts": {
            "facts": _count("reported_financial_facts"),
            "prices_tickers": coverage.get("tickers") or 0,
            "prices_rows": coverage.get("rows_") or 0,
            "filings": _count("filings"),
            "ownership": _count("ownership_records"),
        },
        "cache_size_mb": round(cache_bytes / (1024 * 1024), 1),
    }


@router.post("/sync/bootstrap")
async def start_bootstrap():
    stores = get_stores()
    if stores.bulk.get_state("bootstrap_running") == "1":
        raise HTTPException(status_code=409, detail="bootstrap already running")
    _spawn(ingest_sync.bootstrap(stores))
    return {"started": True}


@router.post("/sync/daily")
async def run_daily_sync():
    _spawn(ingest_sync.daily_tick(get_stores()))
    return {"started": True}
