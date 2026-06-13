"""Learning/Evals routes (api-contract): outcome evaluations, patterns,
recommendations, and the evaluate action."""

from __future__ import annotations

from fastapi import APIRouter

from backend.stores import get_stores
from backend.workflows import learning

router = APIRouter()

# Legacy mount shim: the old register_routes imports `library_router` from this
# module. Empty router; removed together with the old backend.api.routes.__init__.
library_router = APIRouter()


@router.get("/learning")
async def get_learning():
    return learning.learning_view(get_stores())


@router.post("/learning/evaluate")
async def evaluate():
    """Run due outcome evaluations, then pattern detection: AI proposes
    candidate patterns, the deterministic gate validates them."""
    stores = get_stores()
    created = learning.run_outcome_evaluations(stores)
    ai_candidates = await learning.propose_pattern_candidates(stores)
    patterns = learning.detect_patterns(stores, ai_candidates=ai_candidates)
    return {"created": created, "patterns": len(patterns),
            "ai_candidates": len(ai_candidates)}
