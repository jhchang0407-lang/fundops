"""Memory API routes — list, read, create, and delete memories."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.api.deps import get_memory

router = APIRouter()


@router.get("/memory")
async def list_memories(type: Optional[str] = None):
    """List all memory entries, optionally filtered by type."""
    store = get_memory()
    entries = store.get_by_type(type) if type else store.get_all()
    return {
        "memories": [
            {
                "id": e.id,
                "type": e.type,
                "content": e.content,
                "why": e.why,
                "how_to_apply": e.how_to_apply,
                "created": e.created,
                "source": e.source,
                "session_id": e.session_id,
            }
            for e in entries
        ],
        "count": len(entries),
    }


@router.get("/memory/{memory_id}")
async def get_memory_entry(memory_id: str):
    """Read a single memory entry."""
    store = get_memory()
    entry = store.get_by_id(memory_id)
    if not entry:
        raise HTTPException(404, f"Memory entry {memory_id} not found")
    return {
        "id": entry.id,
        "type": entry.type,
        "content": entry.content,
        "why": entry.why,
        "how_to_apply": entry.how_to_apply,
        "created": entry.created,
        "source": entry.source,
        "session_id": entry.session_id,
    }


class CreateMemoryRequest(BaseModel):
    type: str
    rule: str
    why: str = ""
    how_to_apply: str = ""


@router.post("/memory")
async def create_memory(body: CreateMemoryRequest):
    """Manually create a memory entry."""
    from backend.core.memory import MemoryEntry
    store = get_memory()
    entry = MemoryEntry(
        id="",
        type=body.type,
        content=body.rule,
        why=body.why,
        how_to_apply=body.how_to_apply,
        created="",
        source="api",
        session_id=None,
    )
    entry_id = store.save(entry)
    return {"id": entry_id, "created": True}


@router.delete("/memory/{memory_id}")
async def delete_memory_entry(memory_id: str):
    """Delete a memory entry."""
    store = get_memory()
    deleted = store.delete(memory_id)
    if not deleted:
        raise HTTPException(404, f"Memory entry {memory_id} not found")
    return {"deleted": True, "id": memory_id}
