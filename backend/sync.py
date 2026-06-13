"""Headless data sync entrypoint (ADR-0061).

FundOps is a sometimes-on app: the in-app scheduler catches up on launch, and
this CLI lets the OS own wall-clock scheduling so data stays current even on
days the app never opens.

    .venv/bin/python -m backend.sync            # catch-up tick (or bootstrap if never run)
    .venv/bin/python -m backend.sync bootstrap  # force the one-time bulk download
    npm run sync                                # same as the first form

Schedule it with cron (`30 18 * * 1-5 cd ~/Repos/fundops && npm run sync`) or a
launchd agent. The tick is idempotent — index files sync since the last
recorded day (capped at 30 days), so missed days are simply caught up.
"""

from __future__ import annotations

import asyncio
import json
import sys


def _progress(stage: str, detail: dict | None = None) -> None:
    line = f"[fundops sync] {stage}"
    if detail:
        line += f" {json.dumps(detail, default=str)}"
    print(line, flush=True)


async def _main(force_bootstrap: bool) -> int:
    from backend.core.workspace import get_workspace
    from backend.services.ingest import sync as ingest_sync
    from backend.stores import Stores

    stores = Stores(get_workspace())
    # Recover anything a previously killed process left mid-flight (stuck
    # bootstrap flag, orphaned work items) before deciding what to run.
    from backend.services.ingest.scheduler import reconcile_interrupted_work
    reconcile_interrupted_work(stores)
    bootstrapped = stores.bulk.get_state("bootstrap_done") == "1"
    if force_bootstrap or not bootstrapped:
        _progress("bootstrap starting (one-time bulk download — this can take a while)")
        await ingest_sync.bootstrap(stores)
        err = stores.bulk.get_state("bootstrap_error")
        if err:
            _progress("bootstrap finished with errors", {"error": err})
            return 1
        _progress("bootstrap complete", stores.bulk.state_snapshot())
        return 0
    _progress("daily tick starting")
    summary = await ingest_sync.daily_tick(stores)
    _progress("daily tick complete", summary)
    # Cron monitoring should see a nonzero exit when any stage failed —
    # otherwise an all-offline tick looks like success.
    stage_errors = {k: v["error"] for k, v in summary.items()
                    if isinstance(v, dict) and v.get("error")}
    if stage_errors:
        _progress("daily tick had stage errors", stage_errors)
        return 1
    return 0


def main() -> int:
    force_bootstrap = len(sys.argv) > 1 and sys.argv[1] == "bootstrap"
    return asyncio.run(_main(force_bootstrap))


if __name__ == "__main__":
    raise SystemExit(main())
