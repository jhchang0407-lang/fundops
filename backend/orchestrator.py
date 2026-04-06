"""FundOps Workflow Orchestrator.

Event-driven state machine that processes agent events based on workflow.yaml.
Each agent has a trigger condition (schedule, upstream event, or manual).
When an agent completes, it emits an event that may trigger downstream agents.

Phase 2 upgrade: Durable workflow with persistent event store.
- Events are written to DB before triggering agents (write-ahead)
- Status tracking: pending -> processing -> completed/failed
- Idempotency keys prevent duplicate processing
- run_id groups events in a pipeline execution
- Replay support for crash recovery

Max-depth guard prevents infinite trigger loops (default: 10 levels).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
import uuid
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.agents import AgentPlugin, AgentResult

log = logging.getLogger("fundops.orchestrator")

MAX_TRIGGER_DEPTH = 10


@dataclass
class WorkflowEvent:
    """An event emitted by an agent."""
    source: str       # agent name
    event: str        # complete, handoff, pass, fail, alert
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""  # groups events in a pipeline execution
    ticker: str = ""  # extracted from data for indexing

    @property
    def key(self) -> str:
        return f"{self.source}.{self.event}"


@dataclass
class AgentRegistration:
    """A registered agent with its trigger and config."""
    name: str
    plugin: AgentPlugin
    trigger: str           # "screener.handoff", "weekly", "manual", "A OR B"
    config: dict = field(default_factory=dict)


class Orchestrator:
    """Manages the agent pipeline based on workflow configuration.

    Supports durable event storage when a DB connection is provided.
    Falls back to in-memory event log when no DB is available.
    """

    def __init__(
        self,
        workflow_path: str = None,
        max_depth: int = MAX_TRIGGER_DEPTH,
        db_conn=None,
    ):
        self.agents: dict[str, AgentRegistration] = {}
        self.event_log: list[WorkflowEvent] = []
        self.listeners: dict[str, list[Callable]] = {}
        self.workflow_config: dict = {}
        self.max_depth = max_depth
        self._current_depth = 0
        self._db_conn = db_conn
        self._active_run_id: str = ""

        if workflow_path:
            self.load_workflow(workflow_path)

    def load_workflow(self, path: str) -> None:
        """Load workflow configuration from YAML."""
        with open(path) as f:
            self.workflow_config = yaml.safe_load(f)

    def register_agent(self, name: str, plugin: AgentPlugin, trigger: str = "manual") -> None:
        """Register an agent with the orchestrator."""
        self.agents[name] = AgentRegistration(
            name=name,
            plugin=plugin,
            trigger=trigger,
            config=plugin.config,
        )

    def start_pipeline_run(self) -> str:
        """Start a new pipeline run and return the run_id.

        Call this before running a full pipeline to group all events.
        """
        self._active_run_id = f"run-{uuid.uuid4().hex[:12]}"
        log.info(f"Pipeline run started: {self._active_run_id}")
        return self._active_run_id

    def end_pipeline_run(self) -> None:
        """End the active pipeline run."""
        if self._active_run_id:
            log.info(f"Pipeline run ended: {self._active_run_id}")
        self._active_run_id = ""

    async def emit(self, event: WorkflowEvent) -> list[AgentResult]:
        """Emit an event and trigger any listening agents.

        If a DB connection is available, persists events before processing.
        Max-depth guard prevents infinite trigger loops.
        """
        if self._current_depth >= self.max_depth:
            log.error(
                f"Max trigger depth ({self.max_depth}) reached at "
                f"{event.key}. Stopping chain to prevent infinite loop."
            )
            return []

        # Assign run_id if in an active pipeline
        if self._active_run_id and not event.run_id:
            event.run_id = self._active_run_id

        # Extract ticker from event data for indexing
        if not event.ticker:
            event.ticker = event.data.get("ticker", "")

        # Persist event (write-ahead)
        event_id = self._persist_event(event, status="pending")

        # Check idempotency
        if event_id and self._is_duplicate(event):
            log.info(f"Skipping duplicate event: {event.key} (ticker={event.ticker})")
            return []

        self.event_log.append(event)
        results = []

        self._current_depth += 1
        try:
            for name, reg in self.agents.items():
                if self._matches_trigger(event.key, reg.trigger):
                    self._update_event_status(event_id, "processing")
                    result = await self._run_agent(name, event.data)
                    results.append(result)
            self._update_event_status(event_id, "completed")
        except Exception as e:
            self._update_event_status(event_id, "failed")
            raise
        finally:
            self._current_depth -= 1

        return results

    async def run_agent(self, name: str, context: dict = None) -> AgentResult:
        """Manually run a specific agent."""
        return await self._run_agent(name, context or {})

    async def _run_agent(self, name: str, context: dict) -> AgentResult:
        """Internal: execute an agent and emit its completion event.

        Injects active constitution into context so every agent can adapt.
        Event type is read from result.event_type (set explicitly by agent).
        Falls back to "complete" if not set.
        """
        reg = self.agents.get(name)
        if not reg:
            return AgentResult(agent=name, status="failed",
                               errors=[f"Agent '{name}' not registered"])

        # Inject constitution if not already present
        if "constitution" not in context:
            try:
                from backend.core.db_v2 import ScreenerV2DB
                db_path = os.environ.get("FUNDOPS_DB_PATH", str(Path.home() / ".fundops" / "fundops.db"))
                db = ScreenerV2DB(db_path=db_path)
                constitution = db.get_active_constitution()
                if constitution:
                    context["constitution"] = constitution
                db.close()
            except Exception as e:
                log.debug(f"Could not inject constitution: {e}")

        t0 = time.time()

        # Constitution pre-flight check (Phase 3)
        constitution = context.get("constitution")
        if constitution and name in ("thesis", "ic_review", "memo"):
            try:
                from backend.core.constitution_gates import check_preflight
                preflight_data = context.get("thesis") or context
                preflight = check_preflight(constitution, preflight_data, agent=name)

                autonomy = constitution.get("autonomy_mode", "auto")
                if preflight["violations"] and autonomy in ("suggest", "copilot"):
                    log.warning(
                        f"Agent '{name}' blocked by constitution: "
                        f"{preflight['violations']}"
                    )
                    return AgentResult(
                        agent=name,
                        ticker=context.get("ticker", ""),
                        status="blocked",
                        errors=preflight["violations"],
                        data={"preflight": preflight},
                        duration_s=time.time() - t0,
                    )
                elif preflight["violations"]:
                    # Auto mode: log violations but proceed
                    log.warning(
                        f"Agent '{name}' has constitution violations (proceeding in auto mode): "
                        f"{preflight['violations']}"
                    )
                    context["constitution_preflight"] = preflight
            except Exception as e:
                log.debug(f"Constitution pre-flight check failed: {e}")
        try:
            result = await reg.plugin.run(context)
            result.duration_s = time.time() - t0

            # Use explicit event_type from agent (no magic key inference)
            event_type = getattr(result, "event_type", None) or "complete"

            await self.emit(WorkflowEvent(
                source=name,
                event=event_type,
                data=result.data,
                run_id=self._active_run_id,
                ticker=context.get("ticker", ""),
            ))

            return result

        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"Agent '{name}' failed after {elapsed:.1f}s: {e}")
            return AgentResult(
                agent=name,
                status="failed",
                errors=[str(e)],
                duration_s=elapsed,
            )

    def _matches_trigger(self, event_key: str, trigger: str) -> bool:
        """Check if an event matches a trigger expression.

        Trigger grammar:
        - "agent.event"     — exact match
        - "A OR B"          — matches if event_key matches A or B
        - "manual"          — never matches events (only manual runs)
        - "daily"/"weekly"  — never matches events (scheduler handles these)
        """
        if trigger in ("manual", "daily", "weekly", "monthly"):
            return False

        if " OR " in trigger:
            parts = [p.strip() for p in trigger.split(" OR ")]
            return event_key in parts

        return event_key == trigger

    # -----------------------------------------------------------------------
    # Durable event persistence
    # -----------------------------------------------------------------------

    def _persist_event(self, event: WorkflowEvent, status: str = "pending") -> str | None:
        """Write event to DB before processing (write-ahead pattern)."""
        if not self._db_conn:
            return None

        event_id = uuid.uuid4().hex
        # Idempotency key: source + event + ticker + hour bucket
        hour_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        idempotency_key = f"{event.source}:{event.event}:{event.ticker}:{hour_bucket}"

        try:
            import json
            self._db_conn.execute(
                """INSERT OR IGNORE INTO workflow_events
                   (event_id, run_id, source, event, ticker, data, status,
                    idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    event.run_id or None,
                    event.source,
                    event.event,
                    event.ticker,
                    json.dumps(event.data, default=str),
                    status,
                    idempotency_key,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._db_conn.commit()
            return event_id
        except Exception as e:
            log.debug(f"Event persistence failed (non-critical): {e}")
            return None

    def _update_event_status(self, event_id: str | None, status: str) -> None:
        """Update the status of a persisted event."""
        if not self._db_conn or not event_id:
            return
        try:
            completed_at = datetime.now(timezone.utc).isoformat() if status in ("completed", "failed") else None
            self._db_conn.execute(
                "UPDATE workflow_events SET status = ?, completed_at = ? WHERE event_id = ?",
                (status, completed_at, event_id),
            )
            self._db_conn.commit()
        except Exception:
            pass

    def _is_duplicate(self, event: WorkflowEvent) -> bool:
        """Check if an event with the same idempotency key already completed."""
        if not self._db_conn:
            return False
        hour_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        idempotency_key = f"{event.source}:{event.event}:{event.ticker}:{hour_bucket}"
        try:
            row = self._db_conn.execute(
                "SELECT status FROM workflow_events WHERE idempotency_key = ? AND status = 'completed'",
                (idempotency_key,),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def get_incomplete_events(self, run_id: str = None) -> list[dict]:
        """Get events with status 'processing' (indicates a crash during execution)."""
        if not self._db_conn:
            return []
        try:
            if run_id:
                rows = self._db_conn.execute(
                    "SELECT * FROM workflow_events WHERE run_id = ? AND status = 'processing'",
                    (run_id,),
                ).fetchall()
            else:
                rows = self._db_conn.execute(
                    "SELECT * FROM workflow_events WHERE status = 'processing'"
                ).fetchall()
            cols = [d[0] for d in self._db_conn.execute(
                "SELECT * FROM workflow_events LIMIT 0"
            ).description]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    async def replay_run(self, run_id: str) -> list[AgentResult]:
        """Replay incomplete events from a previous pipeline run."""
        incomplete = self.get_incomplete_events(run_id)
        if not incomplete:
            log.info(f"No incomplete events found for run {run_id}")
            return []

        log.info(f"Replaying {len(incomplete)} incomplete events for run {run_id}")
        results = []
        for evt in incomplete:
            import json
            event = WorkflowEvent(
                source=evt["source"],
                event=evt["event"],
                data=json.loads(evt["data"]) if evt["data"] else {},
                run_id=run_id,
                ticker=evt.get("ticker", ""),
            )
            result_list = await self.emit(event)
            results.extend(result_list)
        return results

    def get_status(self) -> dict:
        """Get current orchestrator status."""
        status = {
            "agents": {
                name: {
                    "trigger": reg.trigger,
                    "config": reg.config,
                }
                for name, reg in self.agents.items()
            },
            "recent_events": [
                {"source": e.source, "event": e.event, "timestamp": e.timestamp}
                for e in self.event_log[-20:]
            ],
            "active_run_id": self._active_run_id,
        }

        # Add DB event counts if available
        if self._db_conn:
            try:
                row = self._db_conn.execute(
                    "SELECT COUNT(*) FROM workflow_events"
                ).fetchone()
                status["total_persisted_events"] = row[0] if row else 0
                row = self._db_conn.execute(
                    "SELECT COUNT(*) FROM workflow_events WHERE status = 'processing'"
                ).fetchone()
                status["incomplete_events"] = row[0] if row else 0
            except Exception:
                pass

        return status
