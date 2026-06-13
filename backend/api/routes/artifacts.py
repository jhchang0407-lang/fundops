"""Artifact routes (api-contract): Workflow Artifact Reader + markdown export.

Artifacts are read-only completed outputs; export ships rendered markdown
(or a JSON dump when no rendering exists) as a download.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.stores import get_stores

router = APIRouter()


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    artifact = get_stores().artifacts.get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"unknown artifact {artifact_id}")
    return {
        "id": artifact["id"],
        "kind": artifact["kind"],
        "ticker": artifact.get("ticker"),
        "entity_id": artifact.get("entity_id"),
        "created_at": artifact["created_at"],
        "schema_version": artifact["schema_version"],
        "payload": artifact["payload"],
        "rendered_md": artifact.get("rendered_md"),
        "constitution_version_id": artifact.get("constitution_version_id"),
        "evidence_bundle_id": artifact.get("evidence_bundle_id"),
        "run_id": artifact.get("run_id"),
        "superseded_by": artifact.get("superseded_by"),
    }


@router.get("/artifacts/{artifact_id}/export")
async def export_artifact(artifact_id: str, format: str = "md"):
    if format != "md":
        raise HTTPException(status_code=400, detail="only format=md is supported")
    artifact = get_stores().artifacts.get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"unknown artifact {artifact_id}")
    body = artifact.get("rendered_md") or json.dumps(
        artifact["payload"], indent=2, ensure_ascii=False, default=str
    )
    ticker = (artifact.get("ticker") or "fundops").lower()
    filename = f"{ticker}-{artifact['kind']}-{artifact['created_at'][:10]}.md"
    return PlainTextResponse(
        body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
