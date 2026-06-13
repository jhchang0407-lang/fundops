"""Background scheduler (ADR-0048, ADR-0059): one loop, every 30 minutes.

Each pass drains the durable work queue (coverage memos, queued bootstrap or
daily-tick requests) and, once bootstrap is done, runs the daily data-sync
tick at most once per UTC day when schedules.data_sync is "daily". A
module-level lock guards reentrancy; the task starts in the API lifespan
and is cancelled on shutdown. Nothing here is triggered by page views.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

from backend.core import opconfig
from backend.services.ingest import sec_bulk
from backend.services.ingest import sync as ingest_sync
from backend.services.market_data import FACT_TOPUP_KIND

log = logging.getLogger("fundops.scheduler")

INTERVAL_S = 1800
FACT_TOPUPS_PER_TICK = 25
SECTORS_PER_TICK = 150
_tick_lock = asyncio.Lock()


def reconcile_interrupted_work(stores) -> dict:
    """Boot-time recovery for work a previous process never finished. A hard
    kill leaves the durable bootstrap_running flag set (blocking every future
    bootstrap), work-queue items stuck 'running' (never reclaimed), and
    holdings' coverage_state mid-flight (never re-enqueued). Nothing else
    clears these, so every process entry point runs this once."""
    out: dict = {"work": stores.ops.reconcile_orphans()}
    if stores.bulk.get_state("bootstrap_running") == "1":
        stores.bulk.set_state("bootstrap_running", "0")
        out["bootstrap_flag_cleared"] = True
    stuck = [h["ticker"] for h in stores.portfolio.holdings()
             if h.get("coverage_state") == "running"]
    if stuck:
        pending = {
            ((w.get("payload") or {}).get("ticker") or "").upper()
            for w in stores.ops.queue_state(limit=500)
            if w["status"] in ("queued", "running")
        }
        for ticker in stuck:
            state = "queued" if ticker.upper() in pending else "none"
            stores.portfolio.set_coverage_state(ticker, state)
        out["coverage_reset"] = stuck
    return out


async def _run_work(stores, item: dict, fn) -> None:
    try:
        await fn()
        stores.ops.complete_work(item["id"])
    except asyncio.CancelledError:  # shutdown mid-run: give the attempt back
        stores.ops.fail_work(item["id"], "interrupted by shutdown")
        raise
    except Exception as exc:  # fail_work owns retry-vs-terminal (ADR-0048)
        log.warning("work %s (%s) failed: %s", item["id"], item["kind"], exc)
        stores.ops.fail_work(item["id"], str(exc))


async def _drain_coverage(stores) -> None:
    """Coverage-memo work drains through its own processor, which claims
    queue items itself (portfolio_service owns that lifecycle)."""
    try:
        from backend.services.portfolio_service import process_coverage_queue
    except ImportError:
        return
    await process_coverage_queue(stores)


async def tick(stores) -> dict | None:
    """One scheduler pass; reentrancy-guarded so overlapping passes never run."""
    if _tick_lock.locked():
        return None
    async with _tick_lock:
        out: dict = {"work": 0}
        while item := stores.ops.claim_next(kind="bootstrap"):
            await _run_work(stores, item, lambda: ingest_sync.bootstrap(stores))
            out["work"] += 1
        while item := stores.ops.claim_next(kind="daily_tick"):
            await _run_work(stores, item, lambda: ingest_sync.daily_tick(stores))
            out["work"] += 1
        # Targeted fundamentals top-ups queued by the screener for tickers
        # the bulk file didn't cover. Bounded per pass (SEC pacing); the
        # remainder drains on later ticks.
        topups = 0
        while topups < FACT_TOPUPS_PER_TICK and (
                item := stores.ops.claim_next(kind=FACT_TOPUP_KIND)):
            ticker = ((item.get("payload") or {}).get("ticker") or "").upper()
            if not ticker:
                stores.ops.fail_work(item["id"], "fact_topup item missing ticker")
                continue
            await _run_work(stores, item,
                            lambda t=ticker: sec_bulk.topup_company(stores, t))
            out["work"] += 1
            topups += 1
            await asyncio.sleep(ingest_sync.TOPUP_DELAY_S)
        # Sector/industry identity backfill (peers + Markets tree): a bounded
        # batch per pass until the universe is classified, then a no-op read.
        try:
            from backend.services.ingest.sectors import backfill_sectors
            classified = await backfill_sectors(stores, limit=SECTORS_PER_TICK)
            if classified["classified"] or classified["failed"]:
                out["sectors"] = classified
        except Exception as exc:
            log.warning("sector backfill failed: %s", exc)
        await _drain_coverage(stores)

        cfg = opconfig.load()
        if (cfg["schedules"].get("data_sync") == "daily"
                and stores.bulk.get_state("bootstrap_done") == "1"):
            last = (stores.bulk.get_state("last_daily_tick") or "")[:10]
            if last < datetime.now(timezone.utc).date().isoformat():
                out["daily_tick"] = await ingest_sync.daily_tick(stores)

        # Quarterly universe refresh: re-pull index membership from free sources
        # and ingest any newly-added constituents (bootstrap is idempotent for
        # the rest). Gated on bootstrap_done so it never races the first sync.
        if (cfg["schedules"].get("universe_refresh") == "quarterly"
                and stores.bulk.get_state("bootstrap_done") == "1"
                and _universe_refresh_due(stores)):
            try:
                from backend.services.ingest import universe_refresh
                res = await asyncio.to_thread(universe_refresh.refresh_universe, stores)
                out["universe_refresh"] = {"refreshed": res.get("refreshed"),
                                           "added": len(res.get("added") or []),
                                           "removed": len(res.get("removed") or [])}
                if res.get("added"):
                    await ingest_sync.bootstrap(stores)  # ingest the new names
            except Exception as exc:  # never let it break the scheduler pass
                log.warning("universe refresh failed: %s", exc)
        return out


def _universe_refresh_due(stores, every_days: int = 85) -> bool:
    """True if the universe has never been refreshed or it was > a quarter ago."""
    last = stores.bulk.get_state("universe_refreshed_at")
    if not last:
        return True
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days >= every_days
    except ValueError:
        return True


async def scheduler_loop(stores, interval_s: int = INTERVAL_S) -> None:
    while True:
        try:
            await tick(stores)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the loop must outlive any one bad pass
            log.warning("scheduler tick failed: %s", exc)
        await asyncio.sleep(interval_s)


def start_scheduler(app) -> asyncio.Task:
    """Create the scheduler task on lifespan startup (caller awaits nothing)."""
    from backend.stores import get_stores

    task = asyncio.get_running_loop().create_task(
        scheduler_loop(get_stores()), name="fundops-scheduler")
    app.state.scheduler_task = task
    return task


async def stop_scheduler(app) -> None:
    task = getattr(app.state, "scheduler_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        app.state.scheduler_task = None
