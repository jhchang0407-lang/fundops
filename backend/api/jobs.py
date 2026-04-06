"""FundOps Job Queue.

Manages async agent execution. Jobs are written to DB on start (status='running')
and updated on completion (status='complete'/'failed'). This ensures crash recovery:
if the server restarts, orphaned 'running' jobs are detectable.

In-memory dict tracks active jobs for fast polling. DB is the durable store.

Usage:
    jobs = JobQueue(db)
    job_id = await jobs.submit("screener", agent_fn, context)
    status = jobs.get(job_id)  # {"id": ..., "status": "running", ...}
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

log = logging.getLogger("fundops.jobs")


@dataclass
class Job:
    """A single job in the queue."""
    id: str
    agent: str
    ticker: str = ""
    status: str = "pending"  # pending, running, complete, failed
    progress: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "ticker": self.ticker,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": self.duration_s,
        }


class JobQueue:
    """Async job queue with DB persistence for crash recovery."""

    # Agent types that should run one at a time (expensive / API-heavy)
    SERIALIZED_AGENTS = {"research_report", "investment_memo", "memo", "ic_review", "thesis"}

    def __init__(self, db=None):
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._serial_lock = asyncio.Lock()
        self.db = db

    async def submit(
        self,
        agent: str,
        fn: Callable[..., Coroutine],
        context: dict = None,
        ticker: str = "",
        on_complete: Callable | None = None,
    ) -> str:
        """Submit a job for async execution.

        Args:
            agent: Agent name (e.g., "screener", "thesis").
            fn: Async callable that returns an AgentResult.
            context: Context dict passed to the agent.
            ticker: Optional ticker for per-ticker jobs.

        Returns:
            Job ID for polling.
        """
        job_id = f"{agent}-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, agent=agent, ticker=ticker, status="running")
        job.started_at = time.time()
        self._jobs[job_id] = job

        # Write to DB on start (crash recovery)
        if self.db:
            try:
                # Ensure ticker exists in tickers table (foreign key)
                t = ticker or "PIPELINE"
                self.db.upsert_ticker(t)
                self.db.record_run(
                    agent=agent,
                    ticker=t,
                    run_type="job_start",
                    summary=f"Job {job_id} started",
                )
            except Exception as e:
                log.warning(f"Failed to record job start: {e}")

        # Run in background. Pass job ref so fn can update progress.
        task = asyncio.create_task(self._execute(job, fn, context or {}, on_complete=on_complete))
        self._tasks[job_id] = task

        log.info(f"Job {job_id} submitted: {agent} {ticker}")
        return job_id

    def update_progress(self, job_id: str, progress: str):
        """Update the progress message for a running job."""
        job = self._jobs.get(job_id)
        if job:
            job.progress = progress
            log.info(f"Job {job_id} progress: {progress}")

    async def _execute(self, job: Job, fn: Callable, context: dict, on_complete: Callable | None = None):
        """Execute the job and update status."""
        if job.agent in self.SERIALIZED_AGENTS:
            # Wait for any other serialized job to finish first
            log.info(f"Job {job.id} waiting for serial lock...")
            job.progress = "queued"
            async with self._serial_lock:
                log.info(f"Job {job.id} acquired serial lock")
                await self._execute_inner(job, fn, context, on_complete)
        else:
            await self._execute_inner(job, fn, context, on_complete)

    async def _execute_inner(self, job: Job, fn: Callable, context: dict, on_complete: Callable | None = None):
        """Inner execution logic."""
        job.started_at = time.time()  # Reset to actual start (after queue wait)
        job.progress = ""
        try:
            # Inject progress callback into context
            context["_update_progress"] = lambda msg: setattr(job, "progress", msg)
            result = await fn(context)
            job.status = "complete"
            job.result = getattr(result, "data", {}) if result else {}
            job.completed_at = time.time()
            job.duration_s = job.completed_at - job.started_at

            # Write completion to DB
            if self.db:
                try:
                    t = job.ticker or "PIPELINE"
                    self.db.upsert_ticker(t)
                    self.db.record_run(
                        agent=job.agent,
                        ticker=t,
                        run_type="job_complete",
                        summary=f"Job {job.id} completed in {job.duration_s:.1f}s",
                        full_output=job.result,
                    )
                except Exception as e:
                    log.warning(f"Failed to record job completion: {e}")

            log.info(f"Job {job.id} completed: {job.duration_s:.1f}s")

            # Fire on_complete callback (non-blocking)
            if on_complete:
                try:
                    cb_result = on_complete(job)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception as e:
                    log.warning(f"Job {job.id} on_complete callback failed (non-blocking): {e}")

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = "Cancelled by user"
            job.completed_at = time.time()
            job.duration_s = job.completed_at - job.started_at
            log.info(f"Job {job.id} cancelled")
            # Do not re-raise — task is already being cancelled

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = time.time()
            job.duration_s = job.completed_at - job.started_at

            if self.db:
                try:
                    t = job.ticker or "PIPELINE"
                    self.db.upsert_ticker(t)
                    self.db.record_run(
                        agent=job.agent,
                        ticker=t,
                        run_type="job_failed",
                        summary=f"Job {job.id} failed: {e}",
                    )
                except Exception as ex:
                    log.warning(f"Failed to record job failure: {ex}")

            log.error(f"Job {job.id} failed: {e}")

    def get(self, job_id: str) -> dict | None:
        """Get job status by ID."""
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def list_jobs(self, status: str = None, agent: str = None) -> list[dict]:
        """List all jobs, optionally filtered."""
        jobs = self._jobs.values()
        if status:
            jobs = [j for j in jobs if j.status == status]
        if agent:
            jobs = [j for j in jobs if j.agent == agent]
        return [j.to_dict() for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)]

    def cancel(self, job_id: str) -> bool:
        """Cancel a running job.

        Cancels the underlying asyncio.Task. Returns True if the job was found
        and cancellation was requested, False if not found or already done.
        """
        job = self._jobs.get(job_id)
        if not job or job.status not in ("running", "pending"):
            return False

        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        # Mark immediately so polling reflects cancelled state right away
        job.status = "cancelled"
        job.error = "Cancelled by user"
        job.completed_at = time.time()
        job.duration_s = job.completed_at - job.started_at
        log.info(f"Job {job_id} cancellation requested")
        return True

    def cleanup(self, max_age_s: float = 3600):
        """Remove completed/failed jobs older than max_age_s."""
        now = time.time()
        to_remove = [
            jid for jid, job in self._jobs.items()
            if job.status in ("complete", "failed") and (now - job.completed_at) > max_age_s
        ]
        for jid in to_remove:
            del self._jobs[jid]
            self._tasks.pop(jid, None)
