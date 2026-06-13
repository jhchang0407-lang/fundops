"""FundOps REST API: thin FastAPI adapter over services and stores (ADR-0050).

`create_app()` mounts every contract route module under /api, exposes the
health probe, and serves the built frontend with an SPA fallback. Route
imports are tolerant so the app boots while parallel modules land; missing
routers are logged, never fatal.
"""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

log = logging.getLogger("fundops.api")

# Route module ownership (docs/api-contract.md).
ROUTE_MODULES = (
    "workflows", "portfolio", "company", "monitoring", "learning",
    "chat", "strategy", "dashboard", "settings", "artifacts", "library",
    "sync", "context", "research", "exports", "home",
)

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Ensure the workspace exists and migrations are applied before serving.
    from backend.core.workspace import get_workspace
    get_workspace()
    # Fail any runs orphaned by a previous process so they don't show as
    # forever-running or block new runs (concurrency guard depends on this).
    try:
        from backend.stores import get_stores
        n = get_stores().runs.reconcile_orphans()
        if n:
            log.info("reconciled %d orphaned run(s) from a prior session", n)
        # Reclaim evidence bundles frozen by a run that died before its artifact
        # write (startup-only — never mid-run, where the bundle is in flight).
        g = get_stores().evidence.gc_orphan_bundles()
        if g:
            log.info("garbage-collected %d orphaned evidence bundle(s)", g)
    except Exception as exc:  # never fatal at boot
        log.warning("run reconciliation skipped: %s", exc)
    # Heal thesis-health plans whose kill-criterion/risk comparators were stored
    # in the breach direction (ADR-0014) — they fire false breaches until flipped
    # to the healthy band. Deterministic + idempotent, so safe to run each boot.
    try:
        from backend.stores import get_stores
        from backend.workflows import thesis_health as th_wf
        fixed = th_wf.repair_inverted_comparators(get_stores())
        if fixed:
            log.info("repaired %d inverted thesis-health comparator(s): %s", len(fixed),
                     ", ".join(f"{r['ticker']}:{r['title']} {r['from']}->{r['to']}"
                               for r in fixed))
    except Exception as exc:  # never fatal at boot
        log.warning("thesis-health comparator repair skipped: %s", exc)
    # Recover work a previous process never finished: stuck bootstrap flag,
    # work-queue items left 'running', mid-flight coverage states.
    try:
        from backend.services.ingest.scheduler import reconcile_interrupted_work
        from backend.stores import get_stores
        recovered = reconcile_interrupted_work(get_stores())
        if recovered.get("work", {}).get("requeued") or recovered.get("bootstrap_flag_cleared"):
            log.info("recovered interrupted work from a prior session: %s", recovered)
    except Exception as exc:  # never fatal at boot
        log.warning("work-queue reconciliation skipped: %s", exc)
    started = False
    # FUNDOPS_NO_SCHEDULER=1 serves the app read-only (no background work-queue
    # drain or daily sync) — for inspection, audits, and CI against a real
    # workspace without mutating it.
    if os.environ.get("FUNDOPS_NO_SCHEDULER") == "1":
        log.info("scheduler disabled (FUNDOPS_NO_SCHEDULER=1) — serving read-only")
    else:
        try:  # background work-queue + daily data-sync loop (ADR-0059)
            from backend.services.ingest.scheduler import start_scheduler
            start_scheduler(app)
            started = True
        except Exception as exc:  # scheduler is best-effort at boot, never fatal
            log.warning("scheduler not started: %s", exc)
    yield
    if started:
        from backend.services.ingest.scheduler import stop_scheduler
        await stop_scheduler(app)


def create_app() -> FastAPI:
    app = FastAPI(title="FundOps", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for name in ROUTE_MODULES:
        try:
            module = importlib.import_module(f"backend.api.routes.{name}")
            app.include_router(module.router, prefix="/api", tags=[name])
        except ImportError as exc:
            log.warning("route module %r not available yet (skipped): %s", name, exc)
        except Exception as exc:  # tolerate half-landed parallel modules
            log.warning("route module %r failed to load (skipped): %s", name, exc)

    @app.get("/api/health")
    async def health():
        from backend.core.ai import get_ai
        from backend.stores import get_stores
        stores = get_stores()
        row = stores.ws.query_one(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        )
        # Reflect the RESOLVED provider, not just the OpenAI key: agent_cli
        # (Claude Code / Codex headless) is a fully configured provider that
        # uses its own auth and needs no key.
        provider = get_ai().provider
        return {
            "ok": True,
            "ai_configured": provider != "stub",
            "ai_provider": provider,
            "has_constitution": stores.constitution.active_version() is not None,
            "workspace_schema_version": int(row["value"]) if row else None,
        }

    if _DIST.exists():
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="not found")
            file = (_DIST / full_path).resolve()
            if file.is_relative_to(_DIST) and file.is_file():
                return FileResponse(file)
            return FileResponse(_DIST / "index.html")

    return app


# `uvicorn backend.api:app` (scripts/start.mjs) imports this module-level app.
app = create_app()
