"""Data-sync orchestration (ADR-0059): one-time bootstrap + the daily tick.

bootstrap() performs the full bulk download (universe identity, companyfacts,
prices, ownership, recent index files) with stage progress in sync_state so
the UI can follow along; each stage is isolated — a failure records
bootstrap_error while completed stages persist. daily_tick() is the single
recurring pass: index files → new filings → targeted top-ups → thesis health
for exactly the affected tickers → incremental prices → portfolio refresh.
Both are work-queue friendly and degrade gracefully offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from backend.core import opconfig
from backend.core.workspace import now_iso
from backend.data.universes import load_preset
from backend.services.ingest import sec_bulk, sec_index

log = logging.getLogger("fundops.ingest.sync")

TOPUP_DELAY_S = 0.15  # SEC rate-limit friendly pacing between per-CIK calls
FUNDAMENTAL_FORMS = ["10-K", "10-K/A", "10-Q", "10-Q/A"]


# --- guarded seams (sibling modules built in parallel; tests monkeypatch these) ---------

def _load_price_sync():
    try:
        from backend.services.ingest.prices import sync_price_history
        return sync_price_history
    except ImportError:
        return None


def _load_benchmark_sync():
    try:
        from backend.services.ingest.prices import sync_benchmarks
        return sync_benchmarks
    except ImportError:
        return None


def _load_events_sync():
    try:
        from backend.services.ingest.events import event_scope, sync_company_events
        return event_scope, sync_company_events
    except ImportError:
        return None


def _load_macro_sync():
    try:
        from backend.services.macro import sync_macro
        return sync_macro
    except ImportError:
        return None


def _load_ownership_sync():
    try:
        from backend.services.ingest.ownership import sync_ownership
        return sync_ownership
    except ImportError:
        return None


def _load_thesis_refresh():
    try:
        from backend.workflows.thesis_health import refresh_for
        return refresh_for
    except ImportError:
        return None


def _load_thesis_refresh_due():
    try:
        from backend.workflows.thesis_health import refresh_all
        return refresh_all
    except ImportError:
        return None


def _load_learning():
    try:
        from backend.workflows import learning
        return learning
    except ImportError:
        return None


async def _maybe_await(result):
    return await result if asyncio.iscoroutine(result) else result


# --- universe scope -----------------------------------------------------------------------

def universe_tickers() -> list[str]:
    """The configured default Screened Universe (data.universe_default)."""
    name = opconfig.load()["data"]["universe_default"]
    try:
        return [t.upper() for t in load_preset(name)]
    except (ValueError, OSError) as exc:
        log.warning("universe preset %r unavailable: %s", name, exc)
        return []


def _holdings_tickers(stores) -> list[str]:
    return [h["ticker"] for h in stores.portfolio.holdings()]


# --- bootstrap ------------------------------------------------------------------------------

async def bootstrap(stores, progress_cb=None) -> dict:
    """One-time full bulk download. Stage + progress + error live in
    sync_state (bootstrap_stage / bootstrap_progress / bootstrap_error);
    bootstrap_done flips to 1 only when every stage succeeded."""
    bulk = stores.bulk
    if bulk.get_state("bootstrap_running") == "1":
        return {"ok": False, "skipped": "bootstrap already running"}
    bulk.set_state("bootstrap_running", "1")
    cfg = opconfig.load()["data"]
    errors: list[str] = []
    summary: dict = {}

    def _progress(stage: str, done, total) -> None:
        payload = {"stage": stage, "done": done, "total": total}
        bulk.set_state("bootstrap_progress", json.dumps(payload))
        if progress_cb:
            progress_cb(payload)

    async def _stage(name: str, fn) -> None:
        bulk.set_state("bootstrap_stage", name)
        try:
            summary[name] = await fn()
        except Exception as exc:  # isolate stages; completed work persists
            log.warning("bootstrap stage %r failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
            bulk.set_state("bootstrap_error", f"{name}: {exc}")

    tickers = universe_tickers()

    async def s_universe():
        cik_map = await sec_bulk.sync_cik_map(stores, tickers)
        _progress("universe", len(cik_map), len(tickers))
        return {"universe": cfg["universe_default"], "size": len(tickers),
                "with_cik": len(cik_map)}

    async def s_companyfacts():
        out = await sec_bulk.sync_companyfacts(
            stores, tickers, progress_cb=lambda d, t: _progress("companyfacts", d, t))
        bulk.set_state("last_bulk_refresh", now_iso())
        return out

    async def s_prices():
        fn = _load_price_sync()
        if fn is None:
            return {"note": "prices ingestion module not available"}
        out = await _maybe_await(fn(stores, tickers,
                                    years=cfg["price_history_years"]))
        held = _holdings_tickers(stores)
        if held:  # holdings get deeper history for charts + outcome windows
            await _maybe_await(fn(stores, held,
                                  years=cfg["holdings_price_history_years"]))
        bench = _load_benchmark_sync()
        if bench is not None:  # index series for overlays + benchmark analytics
            await _maybe_await(bench(stores))
        if not (isinstance(out, dict) and out.get("failed_chunks")):
            # Record the achieved depth so the daily tick's catch-up pass
            # knows full-window history is already on disk.
            bulk.set_state("price_depth_years", str(cfg["price_history_years"]))
        return out

    async def s_ownership():
        if not cfg.get("ownership_ingest", True):
            return {"note": "ownership ingest disabled"}
        fn = _load_ownership_sync()
        if fn is None:
            return {"note": "ownership ingestion module not available"}
        return await _maybe_await(fn(stores, tickers))

    async def s_indexes():
        # 30-day initial window (the sec_index MAX_BACKFILL_DAYS cap): 13D/G are
        # rare per-name 5%-crossing events, so a 7-day window over the universe
        # almost always surfaced zero schedules to feed sync_beneficial (#24/2.4).
        since = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
        out = await sec_index.sync_daily_indexes(stores, since)
        # Process any 13D/G schedules the recent indexes surfaced so the
        # Ownership view has largest-holder data from day one.
        try:
            from backend.services.ingest import beneficial
            out["beneficial"] = await beneficial.sync_beneficial(stores)
        except Exception as exc:
            out["beneficial"] = {"error": str(exc)}
        bulk.set_state("last_daily_tick", now_iso())
        return out

    async def s_reconcile():
        # Runs LAST, after companyfacts + prices, so the no-data check sees the
        # freshly loaded data (else a fresh workspace would quarantine everything).
        return stores.identity.reconcile_phantom_status()

    try:
        await _stage("universe", s_universe)
        await _stage("companyfacts", s_companyfacts)
        await _stage("prices", s_prices)
        await _stage("ownership", s_ownership)
        await _stage("indexes", s_indexes)
        await _stage("reconcile", s_reconcile)
        if errors:
            bulk.set_state("bootstrap_stage", "failed")
        else:
            bulk.set_state("bootstrap_done", "1")
            bulk.set_state("bootstrap_error", "")
            bulk.set_state("bootstrap_stage", "done")
        return {"ok": not errors, "errors": errors, **summary}
    finally:
        bulk.set_state("bootstrap_running", "0")


# --- price depth catch-up ---------------------------------------------------------------------

async def ensure_price_depth(stores) -> dict | None:
    """One-time deepening pass: when the configured price depth exceeds what
    earlier syncs actually fetched (e.g. a workspace bootstrapped under an
    older, shallower default), incremental ticks would never backfill it —
    they only fetch forward from the last stored bar. Refetch the full
    window (universe + holdings + benchmarks) so long-range charts and
    outcome windows have bars, then watermark the achieved depth in
    sync_state. Returns None when the workspace is already deep enough."""
    cfg = opconfig.load()["data"]
    target = float(cfg["price_history_years"])
    have = float(stores.bulk.get_state("price_depth_years") or 0)
    if have >= target:
        return None
    fn = _load_price_sync()
    if fn is None:
        return None
    scope = sorted(set(universe_tickers()) | set(_holdings_tickers(stores)))
    if not scope:
        return None
    log.info("price depth catch-up: %.1fy on disk → %.1fy configured (%d tickers)",
             have, target, len(scope))
    out = await _maybe_await(fn(stores, scope, years=target))
    held = _holdings_tickers(stores)
    hyears = float(cfg["holdings_price_history_years"])
    if held and hyears > target:
        await _maybe_await(fn(stores, held, years=hyears))
    bench = _load_benchmark_sync()
    if bench is not None:  # benchmarks share the shallow-history problem
        await _maybe_await(bench(stores))
    if not (isinstance(out, dict) and out.get("failed_chunks")):
        stores.bulk.set_state("price_depth_years", str(target))
    elif isinstance(out, dict):
        out["note"] = "some chunks failed; depth catch-up will retry next tick"
    if isinstance(out, dict):
        out["depth_backfill"] = f"{have:g}y -> {target:g}y"
    return out


# --- daily tick ------------------------------------------------------------------------------

async def daily_tick(stores) -> dict:
    """The single recurring data-sync pass (subsumes the old per-capability
    refreshes): filings index → targeted fundamentals top-ups → thesis
    health for affected tickers → incremental prices → holdings rebuild."""
    bulk = stores.bulk
    summary: dict = {}
    today = datetime.now(timezone.utc).date()
    # Holdings can live outside the screened universe; without a CIK mapping
    # they are invisible to filing detection and fact top-ups (only the
    # universe gets mapped at bootstrap). The ticker→CIK file is cached, so
    # this is a local read on every tick but the first.
    held = _holdings_tickers(stores)
    if held:
        try:
            await sec_bulk.sync_cik_map(stores, held)
        except Exception as exc:
            log.warning("holdings CIK map failed: %s", exc)
    since = bulk.get_state("last_index_date") or (today - timedelta(days=7)).isoformat()
    try:
        summary["index"] = await sec_index.sync_daily_indexes(stores, since)
    except Exception as exc:
        summary["index"] = {"error": str(exc)}

    # Targeted top-ups: only universe/held tickers whose index rows show a
    # fresh 10-K/10-Q. A failed top-up stays unprocessed for the next tick.
    scope = set(universe_tickers()) | set(_holdings_tickers(stores))
    topped: dict[str, bool] = {}
    done_ids: list[str] = []
    for f in bulk.unprocessed_filings(forms=FUNDAMENTAL_FORMS):
        t = (f.get("ticker") or "").upper()
        if not t or (scope and t not in scope):
            done_ids.append(f["id"])  # known entity outside sync scope
            continue
        if t not in topped:
            topped[t] = bool(await sec_bulk.topup_company(stores, t))
            if topped[t]:
                await asyncio.sleep(TOPUP_DELAY_S)
        if topped[t]:
            done_ids.append(f["id"])
    bulk.mark_filings_processed(done_ids)
    affected = [t for t, ok in topped.items() if ok]
    summary["topped_up"] = affected

    # 13D/G schedules → largest-holder records (small per-filing fetches;
    # unparseable filings stay retained as index events).
    try:
        from backend.services.ingest import beneficial
        summary["beneficial"] = await beneficial.sync_beneficial(stores)
    except Exception as exc:
        summary["beneficial"] = {"error": str(exc)}

    # Insider data sets are parsed at bootstrap for the UNIVERSE; a holding
    # added later (often outside the universe) would never get them. Backfill
    # once per holding from the cached quarterly zips, marked in sync_state
    # so a genuinely filing-less ticker isn't re-parsed every tick.
    own_sync = _load_ownership_sync()
    if own_sync:
        missing = [t for t in _holdings_tickers(stores)
                   if not bulk.get_state(f"ownership_backfill_{t}")
                   and not stores.bulk.ownership_for(t, kind="insider_transaction", limit=1)]
        if missing:
            try:
                summary["ownership_backfill"] = await _maybe_await(own_sync(stores, missing))
                for t in missing:
                    bulk.set_state(f"ownership_backfill_{t}", now_iso())
            except Exception as exc:
                summary["ownership_backfill"] = {"error": str(exc)}

    # Filing alerts: new filings for HELD tickers become dashboard attention
    # items (evidence-first; the user decides what they mean).
    held = set(_holdings_tickers(stores))
    if held:
        try:
            # Only decision-relevant forms — Forms 3/4/5 and 13F would flood
            # the queue (insider activity surfaces as clusters on the Company
            # Page instead).
            from backend.services.ingest.events import EVENT_FORMS, FORM_LABELS
            for f in bulk.filings_for(forms=list(EVENT_FORMS), since=since, limit=500):
                t = (f.get("ticker") or "").upper()
                if t not in held:
                    continue
                label = FORM_LABELS.get(f["form"], f"{f['form']} filed")
                stores.dashboard.upsert_item(
                    "attention", "needs_attention", "filing_event",
                    f["id"], str(f["filed_at"])[:10],
                    title=f"{t}: {label}",
                    body=(f.get("title") or f["form"]) + " — review what changed.",
                    ticker=t, severity="normal",
                    rank_source="New filing for a held position",
                    evidence_refs=[{"kind": "filing", "id": f["id"]}],
                )
        except Exception as exc:
            log.warning("filing alerts failed: %s", exc)

    # Thesis health recalculates for precisely the tickers that filed.
    refresh = _load_thesis_refresh()
    if refresh and affected:
        try:
            summary["thesis_health"] = await _maybe_await(
                refresh(stores, affected, trigger="filing"))
        except Exception as exc:
            summary["thesis_health"] = {"error": str(exc)}
    # Then sweep any plan due by staleness (7d held / 30d non-held) that did not
    # just file, so "last checked" stays current automatically. Recalculation
    # remains metadata-gated (ADR-0014) — a no-new-filing sweep only records the
    # check; status never moves without new evidence.
    refresh_due = _load_thesis_refresh_due()
    if refresh_due:
        try:
            swept = await _maybe_await(refresh_due(stores, trigger="scheduled"))
            if swept:
                summary["thesis_health_swept"] = len(swept)
        except Exception as exc:
            summary["thesis_health_swept"] = {"error": str(exc)}

    # Learning/Evals: deterministic outcome scoring + pattern detection over
    # matured ideas (no model calls, idempotent per window). Runs every tick so
    # the loop is automatic instead of waiting on a manual /learning/evaluate
    # poke — the reason QA could not observe it. New recommendation-ready
    # patterns then surface on Home (learning_ready) and the Dashboard.
    learn = _load_learning()
    if learn:
        try:
            created = learn.run_outcome_evaluations(stores)
            # AI proposes candidate patterns (no-op offline), the deterministic
            # gate validates them into pattern/recommendation records.
            ai_candidates = await learn.propose_pattern_candidates(stores)
            patterns = learn.detect_patterns(stores, ai_candidates=ai_candidates)
            summary["learning"] = {"evaluations": created, "patterns": len(patterns),
                                   "ai_candidates": len(ai_candidates)}
        except Exception as exc:
            summary["learning"] = {"error": str(exc)}

    price_sync = _load_price_sync()
    deepened = None
    if price_sync and scope:
        try:
            # Depth catch-up supersedes the incremental pass when the stored
            # history is shallower than configured (full-window refetch,
            # benchmarks included); otherwise sync forward as usual.
            deepened = await ensure_price_depth(stores)
            summary["prices"] = (
                deepened if deepened is not None
                else await _maybe_await(price_sync(stores, sorted(scope), incremental=True)))
        except Exception as exc:
            summary["prices"] = {"error": str(exc)}
    bench_sync = _load_benchmark_sync()
    if bench_sync and deepened is None:  # depth pass already synced benchmarks in full
        try:
            summary["benchmarks"] = await _maybe_await(bench_sync(stores, incremental=True))
        except Exception as exc:
            summary["benchmarks"] = {"error": str(exc)}

    # Calendar events for the small holdings/watchlist scope + macro cache.
    events = _load_events_sync()
    if events:
        scope_fn, sync_fn = events
        try:
            ev_scope = scope_fn(stores)
            if ev_scope:
                summary["events"] = await _maybe_await(sync_fn(stores, ev_scope))
        except Exception as exc:
            summary["events"] = {"error": str(exc)}
    macro_sync = _load_macro_sync()
    if macro_sync:
        try:
            summary["macro"] = await _maybe_await(macro_sync(stores))
        except Exception as exc:
            summary["macro"] = {"error": str(exc)}

    try:
        stores.portfolio.rebuild_holdings()
    except Exception as exc:
        log.warning("holdings rebuild failed: %s", exc)
    try:  # quarantine newly-dataless names, reactivate recovered ones
        summary["reconcile"] = stores.identity.reconcile_phantom_status()
    except Exception as exc:
        log.warning("phantom-status reconcile failed: %s", exc)
    bulk.set_state("last_daily_tick", now_iso())
    return summary
