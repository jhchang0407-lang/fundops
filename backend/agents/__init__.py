"""FundOps Agent Framework.

Each agent implements the AgentPlugin interface and registers via entry_points.
Agents have one job, no overlap. The orchestrator runs them based on workflow.yaml.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone


@dataclass
class AgentResult:
    """Standard result from any agent run."""
    agent: str
    ticker: Optional[str] = None
    status: str = "complete"  # complete, failed, skipped, blocked
    event_type: str = "complete"  # complete, handoff, pass, fail, alert — set explicitly by agent
    data: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def ok(self) -> bool:
        return self.status == "complete" and not self.errors


@dataclass
class OutcomeRecord:
    """Trade outcome for the feedback loop."""
    ticker: str
    action: str  # buy, sell, trim, add
    shares: float
    price: float
    date: str
    source_agent: str  # which agent surfaced this
    scout_lens: Optional[str] = None
    val_expected_return: Optional[float] = None
    judge_verdict: Optional[str] = None
    notes: str = ""


class AgentPlugin(ABC):
    """Base class for all FundOps agents.

    Each agent has one job:
    - Screener: discover opportunities (dual lens scoring)
    - Thesis: write quick thesis with web research
    - IC Review: stress-test thesis (binary PASS/NO_PASS)
    - Memo: full deep-dive analysis (research + investment modes)
    - Library: store and retrieve research
    - Portfolio: monitor held positions (P&L, alerts)
    - Allocator: size positions and recommend actions
    """

    name: str = ""
    description: str = ""

    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    async def run(self, context: dict) -> AgentResult:
        """Execute the agent's one job.

        Args:
            context: Pipeline context with data from upstream agents,
                     connector results, and workflow config.

        Returns:
            AgentResult with structured output data.
        """
        ...

    def validate_config(self) -> list[str]:
        """Validate agent configuration. Returns list of error messages."""
        return []

    async def health_check(self) -> bool:
        """Check if the agent's dependencies are available."""
        return True

    async def teardown(self) -> None:
        """Clean up resources."""
        pass
