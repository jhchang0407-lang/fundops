"""FundOps REST API.

FastAPI backend that wraps agents and connectors with HTTP endpoints.
Serves the React frontend as static files in production.
"""

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FundOps",
    description="AI-powered hedge fund operations platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes at import time so `uvicorn backend.api:app` works correctly.
from backend.api.routes import register_routes  # noqa: E402
register_routes(app)


@app.on_event("startup")
async def _startup():
    """Initialize database and background scheduler on startup."""
    import logging
    _log = logging.getLogger("fundops.startup")
    try:
        from backend.api.deps import get_db, get_v2db, get_config
        get_db()
        get_v2db()
        _log.info("Database initialized — all data preserved")

        # Initialize SEC EDGAR user agent from config
        config = get_config()
        filings_cfg = config.resolved.get("connectors", {}).get("filings", {})
        user_agent = filings_cfg.get("user_agent", "")
        if user_agent:
            from backend.core.sec.client import set_user_agent
            set_user_agent(user_agent)
            _log.info(f"SEC EDGAR user agent set from config")
    except Exception as e:
        _log.warning(f"Startup init failed (non-fatal): {e}")

    # Start background scheduler
    asyncio.create_task(_run_scheduler())


async def _run_scheduler():
    """Background scheduler that checks schedule configs and triggers agent runs."""
    import logging
    import datetime
    _log = logging.getLogger("uvicorn.error")  # Use uvicorn logger so messages are visible
    _log.info("Scheduler started — checking schedules every 30s")

    # Map schedule agent names to API endpoints (self-call via HTTP)
    AGENT_ENDPOINTS: dict[str, tuple[str, str]] = {
        "Screener": ("POST", "/api/screener/run"),
        "Portfolio Monitor": ("POST", "/api/portfolio/run"),
        "Full Pipeline": ("POST", "/api/pipeline/run"),
        "Allocator": ("POST", "/api/allocator/run"),
        "Library Sync": ("POST", "/api/library/sync"),
    }

    # Track last-run times to avoid duplicate triggers
    last_runs: dict[str, str] = {}  # agent -> "YYYY-MM-DD HH" last triggered

    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds

            from backend.api.deps import get_config
            config = get_config()
            schedules = config.resolved.get("system", {}).get("schedules", [])

            now = datetime.datetime.now()
            now_key = now.strftime("%Y-%m-%d %H")
            weekday = now.strftime("%a")  # Mon, Tue, etc.
            hour_min = now.strftime("%-I:%M %p")  # e.g. "8:00 AM"

            for sched in schedules:
                agent = sched.get("agent", "")
                status = sched.get("status", "manual")
                freq = sched.get("frequency", "Manual")
                time_str = sched.get("time", "")

                if status != "active" or freq == "Manual":
                    continue

                endpoint = AGENT_ENDPOINTS.get(agent)
                if not endpoint:
                    continue

                # Check if already ran this hour
                run_key = f"{agent}-{now_key}"
                if run_key in last_runs:
                    continue

                # Parse schedule time and check if it matches now
                should_run = False
                if freq == "Daily" and _time_matches(time_str, hour_min):
                    should_run = True
                elif freq == "Weekly" and _weekly_matches(time_str, weekday, hour_min):
                    should_run = True
                elif freq == "Every 6 hours" and now.hour % 6 == 0 and now.minute < 1:
                    should_run = True

                if should_run:
                    last_runs[run_key] = now_key
                    method, path = endpoint
                    _log.info(f"Scheduler triggering {agent} → {method} {path}")
                    try:
                        import httpx
                        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=300) as client:
                            if method == "POST":
                                await client.post(path)
                        _log.info(f"Scheduler: {agent} triggered successfully")
                    except Exception as e:
                        _log.warning(f"Scheduler: {agent} trigger failed: {e}")

        except asyncio.CancelledError:
            _log.info("Scheduler shutting down")
            break
        except Exception as e:
            _log.warning(f"Scheduler loop error (continuing): {e}")


def _time_matches(sched_time: str, current_hm: str) -> bool:
    """Check if schedule time matches current hour:minute (fuzzy on AM/PM format)."""
    # sched_time could be "7:00 AM" or "Sun 8:00 AM" — extract just the time part
    parts = sched_time.strip().split()
    if len(parts) >= 2:
        time_part = " ".join(parts[-2:])  # last two parts = "8:00 AM"
    else:
        time_part = sched_time.strip()
    return time_part.lower() == current_hm.lower()


def _weekly_matches(sched_time: str, weekday: str, current_hm: str) -> bool:
    """Check if weekly schedule matches (e.g., 'Sun 8:00 AM')."""
    parts = sched_time.strip().split()
    if len(parts) >= 3:
        day_part = parts[0][:3]  # "Sun", "Mon", etc.
        time_part = " ".join(parts[1:3])
        return day_part.lower() == weekday.lower() and time_part.lower() == current_hm.lower()
    return _time_matches(sched_time, current_hm)

# --- Scheduler status endpoint ---
@app.get("/api/scheduler/status")
async def scheduler_status():
    """Show scheduler state: active schedules, next run times, and last triggered."""
    import datetime
    from backend.api.deps import get_config
    config = get_config()
    schedules = config.resolved.get("system", {}).get("schedules", [])
    now = datetime.datetime.now()

    AGENT_ENDPOINTS = {
        "Screener": "/api/screener/run",
        "Portfolio Monitor": "/api/portfolio/run",
        "Full Pipeline": "/api/pipeline/run",
        "Allocator": "/api/allocator/run",
        "Library Sync": "/api/library/sync",
    }

    result = []
    for s in schedules:
        agent = s.get("agent", "")
        has_endpoint = agent in AGENT_ENDPOINTS
        result.append({
            "agent": agent,
            "status": s.get("status", "manual"),
            "frequency": s.get("frequency", "Manual"),
            "time": s.get("time", "—"),
            "has_endpoint": has_endpoint,
            "endpoint": AGENT_ENDPOINTS.get(agent),
        })

    return {
        "server_time": now.strftime("%Y-%m-%d %I:%M:%S %p"),
        "weekday": now.strftime("%A"),
        "schedules": result,
    }


# Serve built frontend static files (only when dist/ exists, i.e. production build)
from pathlib import Path as _Path  # noqa: E402
_dist = _Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    from starlette.responses import FileResponse as _FileResponse  # noqa: E402

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = (_dist / full_path).resolve()
        if file.is_relative_to(_dist) and file.exists() and file.is_file():
            return _FileResponse(file)
        return _FileResponse(_dist / "index.html")


def create_app() -> FastAPI:
    """Factory for uvicorn --factory mode. Routes are already registered at import time."""
    return app
