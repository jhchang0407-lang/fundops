"""Run Full Pipeline: chains Screener → Thesis → IC → Memo via stage handoffs
(CONTEXT workflow lifecycle; ADR-0036).

One pipeline run record with one step per stage; each stage executes its own
durable run and writes the next stage's intake. A failed funnel stage
(screener/thesis/ic) stops the chain and fails the pipeline; memo-stage errors
are recorded as a failed step but never fail the pipeline."""

from __future__ import annotations

from backend.workflows import ic_review, memo, screener, thesis

CAPABILITY = "pipeline"


def prepare_run(stores, trigger: str = "user") -> str:
    active = stores.constitution.active_version()
    uni = stores.constitution.active_universe()
    return stores.runs.start_run(
        CAPABILITY, trigger,
        constitution_version_id=active["id"] if active else None,
        universe_version_id=uni["id"] if uni else None,
    )


async def run_pipeline(stores) -> str:
    rid = prepare_run(stores)
    await execute_run(stores, rid)
    return rid


async def execute_run(stores, run_id: str) -> None:
    stats = {"candidates": 0, "theses": 0, "ic_passes": 0, "memos": 0}
    try:
        # Screener
        ok, s = await _stage(stores, run_id, "screener",
                             screener.run_screener(stores, trigger="pipeline"))
        if not ok:
            stores.runs.finish_run(run_id, "failed", stats=stats,
                                   error="screener stage failed")
            return
        stats["candidates"] = s.get("passed", 0)

        # Thesis (intake = screener handoff)
        ok, s = await _stage(stores, run_id, "thesis",
                             thesis.run_thesis(stores, trigger="pipeline"))
        if not ok:
            stores.runs.finish_run(run_id, "failed", stats=stats,
                                   error="thesis stage failed")
            return
        stats["theses"] = s.get("completed", 0)

        # IC Review (intake = thesis selection handoff)
        ok, s = await _stage(stores, run_id, "ic_review",
                             ic_review.run_ic(stores, trigger="pipeline"))
        if not ok:
            stores.runs.finish_run(run_id, "failed", stats=stats,
                                   error="ic_review stage failed")
            return
        stats["ic_passes"] = s.get("passes", 0)

        # Memo (intake = IC selection) — never fails the pipeline.
        ok, s = await _stage(stores, run_id, "memo",
                             memo.run_memo(stores, trigger="pipeline"))
        if ok:
            stats["memos"] = s.get("memos", 0)

        stores.runs.finish_run(run_id, "completed", stats=stats)
    except Exception as exc:  # noqa: BLE001
        stores.runs.finish_run(run_id, "failed", stats=stats, error=str(exc))


async def _stage(stores, pipeline_run_id: str, name: str, coro) -> tuple[bool, dict]:
    """Await one stage run as a pipeline step; returns (ok, stage stats)."""
    step_id = stores.runs.add_step(pipeline_run_id, name)
    try:
        stage_run_id = await coro
    except Exception as exc:  # noqa: BLE001 — stage workflows normally self-contain
        stores.runs.finish_step(step_id, "failed", error=str(exc))
        return False, {}
    run = stores.runs.get_run(stage_run_id) or {}
    ok = run.get("status") == "completed"
    stores.runs.finish_step(
        step_id, "completed" if ok else "failed",
        detail={"run_id": stage_run_id, "stats": run.get("stats")},
        error=None if ok else (run.get("error") or f"{name} run {run.get('status')}"),
    )
    return ok, run.get("stats") or {}
