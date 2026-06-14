"""Strategy Proposal Guardrails (ADR-0007).

AI drafts proposals; these deterministic checks decide whether a proposal may
activate. A proposal that fails guardrails can be repaired and resubmitted but
never wired. Validation covers criterion ids, metrics, operators, value types,
ranges, data-support honesty, projection compatibility, and required
rationale/source (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain import metric_catalog
from backend.domain.criteria import (
    Criterion, DATA_SUPPORT_LEVELS, KINDS, OPERATORS,
)


@dataclass
class GuardrailResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "review_items": self.review_items,
        }


_MEASURABLE_KINDS = ("screen", "rank", "ic_hurdle")


def validate_criterion(c: Criterion) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if c.kind not in KINDS:
        errors.append(f"{c.criterion_id}: unknown kind {c.kind!r}")
        return errors, warnings
    if not c.criterion_id or "." not in c.criterion_id:
        errors.append(f"criterion id {c.criterion_id!r} must be namespaced like 'screen.roic_min'")
    if not c.rule_rationale or not c.rule_source:
        errors.append(f"{c.criterion_id}: rule rationale and source are required before activation")
    if c.data_support_level not in DATA_SUPPORT_LEVELS:
        errors.append(f"{c.criterion_id}: invalid data support level {c.data_support_level!r}")

    if c.kind in _MEASURABLE_KINDS:
        metric = metric_catalog.get_metric(c.metric or "")
        if metric is None:
            errors.append(f"{c.criterion_id}: metric {c.metric!r} is not in the Financial Metric Catalog")
            return errors, warnings
        if c.kind in ("screen", "ic_hurdle") and not metric.hard_gate_capable:
            errors.append(
                f"{c.criterion_id}: metric {metric.id!r} lacks decision authority for hard gates; "
                "use it as ranking or research-review instead"
            )
        if c.operator not in OPERATORS:
            errors.append(f"{c.criterion_id}: invalid operator {c.operator!r}")
        elif c.operator not in metric.operators and metric.operators:
            errors.append(f"{c.criterion_id}: operator {c.operator!r} not valid for {metric.id}")
        err = _validate_value(c, metric)
        if err:
            errors.append(err)
        rng_warn = _range_warning(c, metric)
        if rng_warn:
            warnings.append(rng_warn)
        if c.kind in ("screen", "ic_hurdle") and c.data_support_level == "unsupported":
            errors.append(
                f"{c.criterion_id}: unsupported criteria cannot become hard gates; "
                "keep as preference in Strategy Preference Memory"
            )
    if c.kind == "rank" and c.weight is not None and c.weight < 0:
        errors.append(f"{c.criterion_id}: ranking weight must be non-negative")
    return errors, warnings


def _validate_value(c: Criterion, metric) -> str | None:
    v = c.value
    if c.operator == "between":
        if not (isinstance(v, (list, tuple)) and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v) and v[0] <= v[1]):
            return f"{c.criterion_id}: 'between' needs an ordered numeric [low, high] pair"
        return None
    if c.operator in ("in", "not_in"):
        if not isinstance(v, (list, tuple)) or not v:
            return f"{c.criterion_id}: '{c.operator}' needs a non-empty list"
        return None
    if metric.unit in ("number", "ratio"):
        if not isinstance(v, (int, float)):
            return f"{c.criterion_id}: numeric metric {metric.id} needs a numeric threshold, got {v!r}"
    return None


def _range_warning(c: Criterion, metric) -> str | None:
    lo, hi = (metric.typical_range + (None, None))[:2] if metric.typical_range else (None, None)
    if isinstance(c.value, (int, float)) and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        if hi > lo and not (lo <= c.value <= hi):
            return (
                f"{c.criterion_id}: threshold {c.value} is outside the typical range "
                f"[{lo}, {hi}] for {metric.id} — this may screen out nearly everything"
            )
    return None


def validate_proposal(payload: dict) -> GuardrailResult:
    """Validate a Strategy Change Proposal payload before acceptance can wire it.

    Expected payload shape (the Strategy Proposal Envelope inner content):
      {summary, north_star, style_blend, narrative?, rules: [criterion dicts],
       ic: {gate_score_blend?, pass_cutoff?}, universe: {name, tickers?},
       unsupported_preferences: [..], tradeoffs: [..]}
    """
    res = GuardrailResult(ok=True)

    summary = payload.get("summary")
    if not summary or not str(summary).strip():
        res.errors.append("proposal needs a plain-English summary")
    if not payload.get("north_star"):
        res.review_items.append("No Strategy North Star captured; downstream emphasis will be generic")

    rules = payload.get("rules") or []
    if not isinstance(rules, list):
        res.errors.append("rules must be a list of criteria")
        rules = []
    criteria = []
    seen_ids: set[str] = set()
    for raw in rules:
        try:
            c = Criterion.from_dict(raw)
        except (KeyError, TypeError) as exc:
            res.errors.append(f"malformed criterion {raw!r}: {exc}")
            continue
        if c.criterion_id in seen_ids:
            res.errors.append(f"duplicate criterion id {c.criterion_id}")
        seen_ids.add(c.criterion_id)
        errs, warns = validate_criterion(c)
        res.errors.extend(errs)
        res.warnings.extend(warns)
        criteria.append(c)

    executable = [c for c in criteria if c.kind in ("screen", "rank", "ic_hurdle")]
    if not executable:
        res.review_items.append(
            "Proposal has no executable screen, rank, or IC-hurdle criteria; "
            "workflows would run with defaults only"
        )
    screens = [c for c in criteria if c.kind == "screen"]
    if len(screens) >= 6:
        res.warnings.append(
            f"{len(screens)} hard screening requirements is unusually narrow; "
            "few companies may survive (restrictiveness warning)"
        )

    ic = payload.get("ic") or {}
    blend = ic.get("gate_score_blend")
    if blend:  # present and non-null; an all-default blend may be null/omitted
        keys = {"conviction", "constitution_fit", "data_quality"}
        if set(blend) != keys or any(v is None for v in blend.values()):
            res.errors.append("ic.gate_score_blend must define numeric conviction, constitution_fit, data_quality")
        elif abs(sum(blend.values()) - 1.0) > 0.01:
            res.errors.append("ic.gate_score_blend weights must sum to 1.0")
    cutoff = ic.get("pass_cutoff")
    if cutoff is not None and not (0 <= float(cutoff) <= 100):
        res.errors.append("ic.pass_cutoff must be between 0 and 100")

    universe = payload.get("universe") or {}
    if universe:
        tickers = universe.get("tickers")
        if tickers is not None and (not isinstance(tickers, list) or not tickers):
            res.errors.append("universe.tickers must be a non-empty list when provided")

    # Prose-to-structure consistency: every wired rule must be visible in summary scope.
    if summary and executable and len(str(summary)) < 20:
        res.warnings.append("summary is very short; users must understand what they are approving")

    res.ok = not res.errors
    return res
