"""Typed Strategy Criteria (ADR-0003, ADR-0008).

A criterion is the smallest wireable unit of strategy. Narrative philosophy
lives on the Constitution; deterministic workflow behavior depends only on
typed criteria evaluated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KINDS = ("screen", "rank", "research_review", "ic_hurdle", "preference")
DATA_SUPPORT_LEVELS = ("fully", "partial", "proxy", "research_review", "unsupported")
OPERATORS = (">", "<", ">=", "<=", "==", "!=", "between", "in", "not_in")


@dataclass
class Criterion:
    criterion_id: str            # stable id, e.g. "screen.roic_min"
    kind: str                    # screen | rank | research_review | ic_hurdle | preference
    rule_rationale: str
    rule_source: str             # proposal/chat-turn reference (ADR-0010)
    metric: str | None = None
    operator: str | None = None
    value: Any = None
    weight: float | None = None  # for rank criteria
    data_support_level: str = "fully"
    interpretation: str | None = None  # novice-friendly explanation (ADR-0005)
    id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "criterion_id": self.criterion_id,
            "kind": self.kind,
            "metric": self.metric,
            "operator": self.operator,
            "value": self.value,
            "weight": self.weight,
            "data_support_level": self.data_support_level,
            "rule_rationale": self.rule_rationale,
            "rule_source": self.rule_source,
            "interpretation": self.interpretation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Criterion":
        return cls(
            criterion_id=d["criterion_id"],
            kind=d["kind"],
            metric=d.get("metric"),
            operator=d.get("operator"),
            value=d.get("value"),
            weight=d.get("weight"),
            data_support_level=d.get("data_support_level", "fully"),
            rule_rationale=d.get("rule_rationale", ""),
            rule_source=d.get("rule_source", ""),
            interpretation=d.get("interpretation"),
            id=d.get("id"),
        )


@dataclass
class EvaluationResult:
    satisfied: bool | None       # None = unevaluable (missing data)
    observed: Any = None
    threshold: Any = None
    reason: str | None = None


def evaluate(criterion: Criterion, observed: Any) -> EvaluationResult:
    """Deterministically evaluate one criterion against an observed value.

    Missing data is unevaluable, never a silent pass or fail; the caller
    decides whether unevaluable blocks (hard screens) or degrades quality.
    """
    op, threshold = criterion.operator, criterion.value
    if observed is None:
        return EvaluationResult(None, None, threshold, "missing data")
    try:
        if op == ">":
            ok = observed > threshold
        elif op == ">=":
            ok = observed >= threshold
        elif op == "<":
            ok = observed < threshold
        elif op == "<=":
            ok = observed <= threshold
        elif op == "==":
            ok = observed == threshold
        elif op == "!=":
            ok = observed != threshold
        elif op == "between":
            lo, hi = threshold
            ok = lo <= observed <= hi
        elif op == "in":
            ok = observed in threshold
        elif op == "not_in":
            ok = observed not in threshold
        else:
            return EvaluationResult(None, observed, threshold, f"unknown operator {op!r}")
    except TypeError:
        return EvaluationResult(None, observed, threshold, "type mismatch")
    return EvaluationResult(bool(ok), observed, threshold)


def screen_criteria(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.kind == "screen" and c.data_support_level in ("fully", "partial", "proxy")]


def rank_criteria(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.kind == "rank"]


def ic_hurdles(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.kind == "ic_hurdle"]


def research_review_criteria(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.kind == "research_review"]


def normalized_rank_weights(criteria: list[Criterion]) -> dict[str, float]:
    """Equal-weight default when no explicit weights were approved."""
    ranks = rank_criteria(criteria)
    if not ranks:
        return {}
    raw = {c.criterion_id: (c.weight if c.weight and c.weight > 0 else 1.0) for c in ranks}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}
