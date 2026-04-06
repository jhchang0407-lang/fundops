"""Dashboard routes."""

from fastapi import APIRouter

from backend.api.deps import get_db, get_job_queue

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard():
    """Get dashboard data: KPIs, funnel, recent activity, agent status."""
    db = get_db()
    jobs = get_job_queue()

    dashboard = db.get_dashboard_data()

    # Parse JSON string fields in portfolio snapshot
    import json as _json
    portfolio = dashboard.get("latest_portfolio")
    if portfolio:
        for field in ("holdings", "alerts"):
            val = portfolio.get(field)
            if isinstance(val, str):
                try:
                    portfolio[field] = _json.loads(val)
                except Exception:
                    portfolio[field] = []

    # Add job status
    running_jobs = jobs.list_jobs(status="running")
    dashboard["running_jobs"] = running_jobs
    dashboard["agent_status"] = {
        "screener": "running" if any(j["agent"] == "screener" for j in running_jobs) else "idle",
        "thesis": "running" if any(j["agent"] == "thesis" for j in running_jobs) else "idle",
        "ic_review": "running" if any(j["agent"] == "ic_review" for j in running_jobs) else "idle",
        "memo": "running" if any(j["agent"] == "memo" for j in running_jobs) else "idle",
        "library": "idle",
        "portfolio": "running" if any(j["agent"] == "portfolio" for j in running_jobs) else "idle",
        "allocator": "running" if any(j["agent"] == "allocator" for j in running_jobs) else "idle",
    }

    return dashboard
