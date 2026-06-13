"""Dashboard routes (api-contract): decision/attention queue projected from
sources, item responses, explicit rebuild."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import dashboard_service
from backend.stores import get_stores

router = APIRouter()


class ResponseIn(BaseModel):
    response: str
    payload: dict | None = None


@router.get("/dashboard")
async def get_dashboard():
    return dashboard_service.overview(get_stores())


@router.post("/dashboard/items/{item_id}/respond")
async def respond(item_id: str, body: ResponseIn):
    try:
        return dashboard_service.respond_item(get_stores(), item_id,
                                              body.response, body.payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/dashboard/refresh")
async def refresh_dashboard():
    dashboard_service.rebuild(get_stores())
    return {"ok": True}
