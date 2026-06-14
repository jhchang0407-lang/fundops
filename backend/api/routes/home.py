"""Home routes: the briefing + Now-panel payload.

The briefing is a deterministic composition over retained records — filings
for held tickers, thesis-health movement, learning readiness, upcoming
events, macro, live runs, pending approvals. No model call: the system reads
its own data; every item carries the reference its claim came from.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from backend.stores import get_stores

router = APIRouter()

# Held names file infrequently; a 3-day window almost always read empty even
# though the universe-wide filings index was full (#24 — a read bug, not ingest
# scope). 14 days matches the event horizon and surfaces recent 10-K/Q/8-K.
FILING_LOOKBACK_DAYS = 14
EVENT_HORIZON_DAYS = 14


@router.get("/home/briefing")
async def briefing():
    from backend.services import macro
    from backend.services.ingest.events import EVENT_FORMS, FORM_LABELS, upcoming_view
    from backend.workflows import thesis_health

    stores = get_stores()
    today = datetime.now(timezone.utc).date()
    since = (today - timedelta(days=FILING_LOOKBACK_DAYS)).isoformat()

    held = [h["ticker"] for h in stores.portfolio.holdings()]
    held_set = set(held)

    filings = [
        {"ticker": f["ticker"], "form": f["form"],
         "label": FORM_LABELS.get(f["form"], f"{f['form']} filed"),
         "filed_at": str(f["filed_at"])[:10]}
        for f in stores.bulk.filings_for(forms=list(EVENT_FORMS), since=since, limit=50)
        if (f.get("ticker") or "").upper() in held_set
    ][:5]

    health = {"broken": [], "watching": [], "intact": 0, "unchecked": 0}
    for t in held:
        label = (thesis_health.summary_for(stores, t) or "").lower()
        if label == "broken":
            health["broken"].append(t)
        elif label == "watching":
            health["watching"].append(t)
        elif label == "intact":
            health["intact"] += 1
        else:
            health["unchecked"] += 1

    learning_ready = sum(
        1 for r in stores.learning.records(kind="recommendation", limit=50)
        if r.get("confidence_label") == "recommendation_ready"
    )
    # Visible learning status even before a recommendation matures, so the loop
    # reads as working-but-quiet rather than dormant (the QA blind spot).
    learning = {
        "ready": learning_ready,
        "evaluations": len(stores.learning.records(kind="outcome_evaluation", limit=1000)),
        "patterns": len(stores.learning.records(kind="pattern", limit=200)),
    }

    pending = stores.constitution.pending_proposal()
    running = [
        {"id": r["id"], "kind": r["kind"], "started_at": r.get("started_at")}
        for r in stores.runs.recent_runs(limit=10)
        if r.get("status") == "running"
    ]

    return {
        "date": today.isoformat(),
        "filings": filings,
        "health": health,
        "learning_ready": learning_ready,
        "learning": learning,
        "pending_proposal": (
            {"id": pending["id"],
             "summary": (pending.get("payload") or {}).get("summary")}
            if pending else None
        ),
        "running": running,
        "events": upcoming_view(stores, days_ahead=EVENT_HORIZON_DAYS, limit=6),
        "macro": macro.macro_strip(stores),
        "watch_total": len(held),
    }
