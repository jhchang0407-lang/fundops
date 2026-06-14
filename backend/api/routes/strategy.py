"""Strategy routes (api-contract): Constitution versions, proposals, wiring.

Reads come straight from the constitution store; mutation goes through the
strategy service so acceptance always re-validates guardrails and wires
settings projections.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.domain import wiring
from backend.services import strategy_service
from backend.stores import get_stores

router = APIRouter()


def _version_summary(version: dict) -> dict:
    return {
        "id": version["id"],
        "version_number": version["version_number"],
        "status": version["status"],
        "north_star": version.get("north_star"),
        "style_blend": version.get("style_blend"),
        "narrative": version.get("narrative"),
        "version_rationale": version.get("version_rationale"),
        "criteria_count": len(version.get("criteria", [])),
        "activated_at": version.get("activated_at"),
    }


@router.get("/strategy")
async def get_strategy():
    stores = get_stores()
    active = stores.constitution.active_version()
    out = {
        "active_version": None,
        "pending_proposal": stores.constitution.pending_proposal(),
        "projections": [],
        "universe": None,
    }
    if active:
        out["active_version"] = _version_summary(active)
        out["projections"] = [
            {
                "capability": p["capability"],
                "summary_text": p["summary_text"],
                "review_items": p["review_items"],
            }
            for p in stores.constitution.projections_for(active["id"])
        ]
        universe = stores.constitution.active_universe()
        if universe:
            out["universe"] = {
                "name": universe["name"],
                "tickers_count": len(universe.get("tickers") or []),
            }
    return out


@router.get("/strategy/versions")
async def list_versions():
    stores = get_stores()
    return [
        {
            "id": v["id"],
            "version_number": v["version_number"],
            "status": v["status"],
            "north_star": v.get("north_star"),
            "version_rationale": v.get("version_rationale"),
            "activated_at": v.get("activated_at"),
        }
        for v in stores.constitution.list_versions()
    ]


@router.get("/strategy/diff")
async def strategy_diff(from_id: str, to_id: str):
    try:
        return strategy_service.version_diff(get_stores(), from_id, to_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/strategy/versions/{version_id}")
async def get_version(version_id: str):
    stores = get_stores()
    version = stores.constitution.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"unknown constitution version {version_id}")
    version = dict(version)
    version["projections"] = stores.constitution.projections_for(version_id)
    return version


@router.post("/strategy/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: str):
    try:
        version = strategy_service.accept_proposal(get_stores(), proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"version": version}


@router.post("/strategy/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    try:
        strategy_service.reject_proposal(get_stores(), proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/strategy/wiring/{capability}")
async def get_wiring(capability: str):
    stores = get_stores()
    # Universe is a Constitution-owned Universe Version, not a settings
    # projection — surface it as its own read-only wiring panel.
    if capability == "universe":
        return _universe_wiring(stores)
    if capability not in wiring.CAPABILITIES:
        raise HTTPException(status_code=404, detail=f"unknown capability {capability}")
    projection = stores.constitution.projection(capability)
    if not projection:
        raise HTTPException(
            status_code=404,
            detail=f"no settings projection for {capability}; no Constitution is active",
        )
    return {
        "capability": capability,
        "settings": projection["settings"],
        "summary_text": projection["summary_text"],
        "review_items": projection["review_items"],
        "version_id": projection["version_id"],
    }


def _universe_wiring(stores) -> dict:
    active = stores.constitution.active_version()
    universe = stores.constitution.active_universe()
    if not universe:
        raise HTTPException(
            status_code=404,
            detail="no universe selected; no Constitution is active",
        )
    tickers = universe.get("tickers") or []
    count = len(tickers)
    source = universe.get("source") or "—"
    if count:
        summary = (f"Screens {universe['name']} — {count} resolved constituents. "
                   "Screener evaluates this set each run.")
    else:
        summary = (f"Screens {universe['name']}. Constituents resolve at run time; "
                   "no fixed snapshot is stored.")
    return {
        "capability": "universe",
        "settings": {
            "name": universe["name"],
            "constituents": count,
            "source": source,
            "sample_tickers": tickers[:15],
            "exclusions": universe.get("exclusions") or [],
        },
        "summary_text": summary,
        "review_items": [],
        "version_id": active["id"] if active else None,
    }
