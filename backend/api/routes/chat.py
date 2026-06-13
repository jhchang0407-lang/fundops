"""FundOps Chat routes (api-contract): message handling + retained history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.chat.service import handle_message
from backend.stores import get_stores

router = APIRouter()


class ChatMessageIn(BaseModel):
    session_id: str | None = None
    message: str
    # Ambient page context from the chat drawer: {"page": "company", "ticker": "NVDA"}
    context: dict | None = None


@router.post("/chat/message")
async def chat_message(body: ChatMessageIn):
    from backend.core.ai import AIError

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    try:
        return await handle_message(get_stores(), body.session_id, body.message.strip(),
                                    context=body.context)
    except AIError as exc:
        # A transient provider failure should degrade, not 500: the client
        # shows the error inline and the user can simply retry.
        raise HTTPException(
            status_code=503,
            detail=f"AI provider error — please retry: {exc}")


@router.get("/chat/session")
async def chat_session():
    """Server-side session anchor: lets a client with no stored session id
    resume the latest conversation instead of minting a new one."""
    return {"session_id": get_stores().constitution.latest_chat_session()}


@router.get("/chat/history")
async def chat_history(session_id: str):
    messages = get_stores().constitution.chat_history(session_id)
    return {
        "messages": [
            {
                "role": m["role"],
                "mode": m["mode"],
                "content": m["content"],
                "refs": m["refs"],
                "created_at": m["created_at"],
            }
            for m in messages
        ]
    }


@router.get("/chat/threads")
async def chat_threads(limit: int = 30):
    """Conversations as durable objects, browsable from the Library."""
    limit = max(1, min(limit, 200))
    return {"threads": get_stores().constitution.chat_threads(limit=limit)}


@router.get("/chat/memory")
async def chat_memory():
    """What the conversation remembers about you — active strategy memory
    with provenance, readable and forgettable from the Library."""
    records = get_stores().constitution.memory()
    return {
        "memory": [
            {
                "id": m["id"],
                "kind": m["kind"],
                "content": m["content"],
                "source": m.get("source"),
                "created_at": m["created_at"],
            }
            for m in records
        ]
    }


@router.post("/chat/memory/{memory_id}/forget")
async def chat_memory_forget(memory_id: str):
    """Append-only forget: the record is retained for history but leaves
    every active read (prompts, recommendations)."""
    if not get_stores().constitution.forget_memory(memory_id):
        raise HTTPException(status_code=404, detail=f"unknown or already forgotten memory {memory_id}")
    return {"forgotten": memory_id}
