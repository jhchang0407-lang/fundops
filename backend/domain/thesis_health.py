"""Deterministic Thesis Health evaluation (ADR-0014).

Memo generation drafts the Investment Memo Monitoring Plan (LLM judgment);
this module validates it against the Supported Thesis Health Field Catalog
and evaluates quantitative watch items deterministically afterward. LLMs
never rejudge quantitative watch-item status during refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain import metric_catalog

ITEM_TYPES = ("assumption", "return_driver", "risk", "kill_criterion")
TRACKING_MODES = ("quantitative", "qualitative", "unsupported")
CADENCES = ("quarterly", "annual", "ttm", "slower")
LOOKBACKS = ("latest", "yoy", "ttm", "annual", "multi_period_avg")
COMPARATORS = (">", ">=", "<", "<=")
STATUSES = ("intact", "watch", "broken", "unknown", "data_gap")
DEFAULT_CONFIRMATION_PERIODS = 2


@dataclass
class WatchItemSpec:
    """A monitoring-plan watch item after validation/normalization."""
    item_type: str
    title: str
    tracking_mode: str
    why_matters: str = ""
    metric: str | None = None
    comparator: str | None = None
    threshold: float | None = None
    cadence: str = "quarterly"
    lookback: str = "latest"
    confirmation_periods: int = DEFAULT_CONFIRMATION_PERIODS
    immediate_kill: bool = False
    validation_errors: list[str] = field(default_factory=list)
    normalizations: list[str] = field(default_factory=list)

    @property
    def status_driving(self) -> bool:
        return self.tracking_mode == "quantitative" and not self.validation_errors


# Breach-framing normalization (ADR-0014): a watch item's comparator must
# express the HEALTHY band — the condition the metric STAYS in while the thesis
# holds — so a breach is when the metric LEAVES that band (evaluate_item reads
# `comparator` as the healthy test). Memo-generated kill criteria and risks are
# named after the BREACH event ("revenue growth turns negative", "debt/equity
# rises above 1.6x"), and models sometimes store the comparator in that breach
# direction instead of the healthy one — which makes a perfectly healthy current
# value read as breached (the KO false-positive). We deterministically detect the
# breach framing and, when the stored comparator points the breach way, flip it
# to its logical complement so it once again expresses health.
#
# "turns/goes negative" is adverse for ANY item type (a metric going negative is
# universally bad → breach below 0). Otherwise the direction comes from the
# threshold-relative preposition in the title ("below"/"above"), which is only a
# reliable BREACH marker on risk/kill_criterion items, whose title IS the adverse
# condition; on assumptions/return drivers the same words name the DESIRED
# condition ("revenue exceeds target"), so we never auto-flip those.
_ALWAYS_DOWN_PHRASES = (
    "turns negative", "turn negative", "turning negative", "turned negative",
    "goes negative", "go negative", "going negative", "went negative",
)
_DOWN_MARKERS = ("below", "beneath")
_UP_MARKERS = ("above", "beyond", "exceed")
# 'Stays in band' verbs reframe a title as the HEALTHY condition ("gross margin
# holds above 40%"); when present we trust the comparator as written and skip
# marker inference (the always-negative phrases above still apply).
_HEALTHY_STAY_VERBS = (
    "holds", "hold ", "stays", "stay ", "remains", "remain ", "maintain",
    "sustain", "keeps ", "at least", "at or above", "at or below",
    "no lower than", "no higher than", "no less than", "no more than",
)
# Logical complement: a breach-direction comparator negated expresses the
# healthy band (note the inclusivity flips too — `< 0` breach → `>= 0` healthy).
_COMPARATOR_COMPLEMENT = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}
# Comparators that already express health for a given breach direction.
_HEALTHY_FOR_BREACH = {"down": (">", ">="), "up": ("<", "<=")}


def _breach_direction(item_type: str, title: str) -> str | None:
    """Infer the breach direction a watch item's framing implies: 'down' when the
    metric crossing BELOW its threshold is the breach, 'up' when crossing ABOVE
    is. Returns None when the title carries no — or conflicting — directional
    breach framing (or is framed as the healthy band), so nothing is changed."""
    t = (title or "").lower()
    if any(p in t for p in _ALWAYS_DOWN_PHRASES):
        return "down"
    if item_type not in ("risk", "kill_criterion"):
        return None
    if any(v in t for v in _HEALTHY_STAY_VERBS):
        return None
    down = any(w in t for w in _DOWN_MARKERS)
    up = any(w in t for w in _UP_MARKERS)
    if down != up:
        return "down" if down else "up"
    return None


def healthy_comparator_fix(item_type: str, title: str,
                           comparator: str | None) -> str | None:
    """Corrected (healthy-band) comparator when `comparator` is stored in the
    breach direction for a breach-framed item, else None. Shared by validate_plan
    (new memos) and the repair pass (existing persisted plans) so both apply one
    rule. Idempotent: a comparator already expressing health returns None."""
    if comparator not in COMPARATORS:
        return None
    direction = _breach_direction(item_type, title)
    if direction is None or comparator in _HEALTHY_FOR_BREACH[direction]:
        return None
    return _COMPARATOR_COMPLEMENT[comparator]


def validate_plan(raw_items: list[dict]) -> list[WatchItemSpec]:
    """Validate monitoring-plan items; invalid quantitative items downgrade to
    unsupported rather than silently driving status. Breach-framed comparators
    are normalized to the healthy band before validation (see
    healthy_comparator_fix)."""
    specs: list[WatchItemSpec] = []
    for raw in raw_items or []:
        spec = WatchItemSpec(
            item_type=raw.get("item_type", "assumption"),
            title=str(raw.get("title", "")).strip(),
            tracking_mode=raw.get("tracking_mode", "unsupported"),
            why_matters=str(raw.get("why_matters", "")),
            metric=raw.get("metric"),
            comparator=raw.get("comparator"),
            threshold=_as_float(raw.get("threshold")),
            cadence=raw.get("cadence", "quarterly"),
            lookback=raw.get("lookback", "latest"),
            confirmation_periods=int(raw.get("confirmation_periods", DEFAULT_CONFIRMATION_PERIODS)),
            immediate_kill=bool(raw.get("immediate_kill", False)),
        )
        errs = spec.validation_errors
        if spec.item_type not in ITEM_TYPES:
            spec.item_type = "assumption"
        if not spec.title:
            errs.append("missing title")
        fixed = healthy_comparator_fix(spec.item_type, spec.title, spec.comparator)
        if fixed is not None:
            spec.normalizations.append(
                f"comparator {spec.comparator!r}→{fixed!r}: {spec.title!r} is "
                "breach-framed, so the stored comparator expressed the breach "
                "trigger; flipped to the healthy band the metric should stay in"
            )
            spec.comparator = fixed
        if spec.tracking_mode == "quantitative":
            if spec.cadence not in CADENCES:
                errs.append(f"invalid cadence {spec.cadence!r}")
            if spec.lookback not in LOOKBACKS:
                errs.append(f"invalid lookback {spec.lookback!r}")
            if spec.comparator not in COMPARATORS:
                errs.append(f"invalid comparator {spec.comparator!r}")
            if spec.threshold is None:
                errs.append("missing numeric threshold")
            if not spec.metric:
                errs.append("missing metric")
            elif not metric_catalog.thesis_health_combo_allowed(
                spec.metric, _cadence_for_catalog(spec.cadence), spec.lookback
            ):
                errs.append(
                    f"metric/cadence/lookback combination not in Supported Thesis Health "
                    f"Field Catalog: {spec.metric}/{spec.cadence}/{spec.lookback}"
                )
            if errs:
                spec.tracking_mode = "unsupported"
        elif spec.tracking_mode not in TRACKING_MODES:
            spec.tracking_mode = "unsupported"
        if spec.immediate_kill:
            spec.confirmation_periods = 1
        specs.append(spec)
    return specs


def _cadence_for_catalog(cadence: str) -> str:
    return "annual" if cadence == "slower" else cadence


def _as_float(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def plan_is_thesis_health_ready(specs: list[WatchItemSpec], baseline_available: dict[str, bool]) -> bool:
    """Thesis-health ready = at least one valid quantitative item with baseline
    evidence available (ADR-0014)."""
    return any(
        s.status_driving and baseline_available.get(s.metric or "", False)
        for s in specs
    )


@dataclass
class EvaluationOutcome:
    status: str               # intact | watch | broken | unknown | data_gap
    observed: float | None
    breached: bool | None
    consecutive_breaches: int
    note: str = ""


def evaluate_item(
    spec_threshold: float,
    comparator: str,
    observed: float | None,
    prior_consecutive_breaches: int,
    confirmation_periods: int,
    is_baseline: bool = False,
) -> EvaluationOutcome:
    """Deterministic Thesis Health Evaluation for one quantitative watch item.

    The comparator expresses the HEALTHY condition (e.g. gross_margin >= 0.40).
    A breach in one period moves the item to watch; `confirmation_periods`
    consecutive breaches confirm broken. Baselines never produce broken unless
    the item is an explicit immediate kill criterion (confirmation_periods=1).
    """
    if observed is None:
        return EvaluationOutcome("data_gap", None, None, prior_consecutive_breaches,
                                 "required data unavailable; prior status preserved by caller")
    healthy = {
        ">": observed > spec_threshold,
        ">=": observed >= spec_threshold,
        "<": observed < spec_threshold,
        "<=": observed <= spec_threshold,
    }.get(comparator)
    if healthy is None:
        return EvaluationOutcome("unknown", observed, None, prior_consecutive_breaches,
                                 f"invalid comparator {comparator!r}")
    if healthy:
        return EvaluationOutcome("intact", observed, False, 0)
    breaches = prior_consecutive_breaches + 1
    if is_baseline and confirmation_periods > 1:
        # Baseline evidence initializes at watch, never broken (ADR-0014).
        return EvaluationOutcome("watch", observed, True, breaches,
                                 "baseline breach; needs post-memo confirmation")
    if breaches >= confirmation_periods:
        return EvaluationOutcome("broken", observed, True, breaches,
                                 f"breached {breaches} consecutive period(s)")
    return EvaluationOutcome(
        "watch", observed, True, breaches,
        f"breached {breaches}/{confirmation_periods} periods needed to confirm broken",
    )


def summary_label(statuses: list[str]) -> str:
    """Qualitative Thesis Health Summary Label from status-driving items."""
    checked = [s for s in statuses if s in STATUSES]
    if not checked or all(s in ("unknown", "data_gap") for s in checked):
        return "Not Checked"
    if "broken" in checked:
        return "Broken"
    if "watch" in checked:
        return "Watching"
    return "Intact"


STATUS_ORDER = {"broken": 0, "watch": 1, "unknown": 2, "data_gap": 2, "intact": 3}


def sort_items_for_display(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: STATUS_ORDER.get(i.get("status", "unknown"), 2))
