"""IC Gate Scoring Model (ADR-0012).

IC Gate judges memo-worthiness. Hard hurdles are evaluated first; a confirmed
miss is an automated IC Fail unless the user overrides. If hurdles pass, the
gate score blends three 0-100 scores. Components are equal-weighted within
each score; unknown components score neutral 50 and lower data quality;
contradicted components score below neutral and lower both the affected score
and data quality.

The semantic judgment of each component (supported / unknown / contradicted +
strength) comes from an AI review step; the arithmetic that turns components
into scores and verdicts lives here, deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_BLEND = {"conviction": 0.45, "constitution_fit": 0.35, "data_quality": 0.20}
DEFAULT_CUTOFF = 70.0
NEUTRAL = 50.0
SEVERE_WEAKNESS_FLOOR = 25.0  # any pillar below this forces a fail guardrail

CONVICTION_COMPONENTS = (
    "argument_strength", "evidence_support", "catalyst_or_path_clarity",
    "risk_adjusted_downside", "assumption_sensitivity", "precedent_support",
)
FIT_COMPONENTS = (
    "exact_criteria_alignment", "north_star_alignment",
    "anti_signal_avoidance", "data_support_confidence",
)
DATA_QUALITY_COMPONENTS = (
    "data_freshness", "financial_completeness", "source_grounding",
    "entity_correctness", "return_source_validation", "contradictions",
)


@dataclass
class ComponentJudgment:
    """One auditable IC Score Component as judged by semantic review."""
    component: str
    state: str            # supported | unknown | contradicted
    score: float | None   # 0-100 when supported; ignored otherwise
    note: str = ""

    def effective_score(self) -> float:
        if self.state == "unknown":
            return NEUTRAL
        if self.state == "contradicted":
            base = self.score if self.score is not None else NEUTRAL
            return min(base, NEUTRAL - 15.0)
        return max(0.0, min(100.0, self.score if self.score is not None else NEUTRAL))


@dataclass
class HurdleFinding:
    criterion_id: str
    metric: str | None
    met: bool
    explanation: str
    observed: object = None
    threshold: object = None

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id, "metric": self.metric,
            "met": self.met, "explanation": self.explanation,
            "observed": self.observed, "threshold": self.threshold,
        }


@dataclass
class GateResult:
    verdict: str                       # pass | fail
    conviction: float
    constitution_fit: float
    data_quality: float
    gate_score: float
    blend: dict
    cutoff: float
    hurdle_findings: list[HurdleFinding]
    components: dict = field(default_factory=dict)
    fail_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "conviction": round(self.conviction, 1),
            "constitution_fit": round(self.constitution_fit, 1),
            "data_quality": round(self.data_quality, 1),
            "gate_score": round(self.gate_score, 1),
            "blend": self.blend,
            "cutoff": self.cutoff,
            "hurdle_findings": [h.to_dict() for h in self.hurdle_findings],
            "components": self.components,
            "fail_reason": self.fail_reason,
        }


def _pillar_score(judgments: list[ComponentJudgment], expected: tuple[str, ...]) -> float:
    by_name = {j.component: j for j in judgments}
    scores = []
    for name in expected:
        j = by_name.get(name) or ComponentJudgment(name, "unknown", None, "not judged")
        scores.append(j.effective_score())
    return sum(scores) / len(scores)


def _quality_penalty(judgments: list[ComponentJudgment]) -> float:
    """Unknown/contradicted evidence anywhere degrades data quality."""
    penalty = 0.0
    for j in judgments:
        if j.state == "unknown":
            penalty += 4.0
        elif j.state == "contradicted":
            penalty += 8.0
    return min(penalty, 35.0)


def score_gate(
    conviction_judgments: list[ComponentJudgment],
    fit_judgments: list[ComponentJudgment],
    data_quality_judgments: list[ComponentJudgment],
    hurdle_findings: list[HurdleFinding],
    blend: dict | None = None,
    cutoff: float | None = None,
) -> GateResult:
    blend = {**DEFAULT_BLEND, **(blend or {})}
    cutoff = DEFAULT_CUTOFF if cutoff is None else float(cutoff)

    conviction = _pillar_score(conviction_judgments, CONVICTION_COMPONENTS)
    fit = _pillar_score(fit_judgments, FIT_COMPONENTS)
    dq = _pillar_score(data_quality_judgments, DATA_QUALITY_COMPONENTS)
    dq = max(0.0, dq - _quality_penalty(conviction_judgments + fit_judgments))

    gate_score = (
        blend["conviction"] * conviction
        + blend["constitution_fit"] * fit
        + blend["data_quality"] * dq
    )
    components = {
        "conviction": {j.component: {"state": j.state, "score": j.effective_score(), "note": j.note}
                       for j in conviction_judgments},
        "constitution_fit": {j.component: {"state": j.state, "score": j.effective_score(), "note": j.note}
                             for j in fit_judgments},
        "data_quality": {j.component: {"state": j.state, "score": j.effective_score(), "note": j.note}
                         for j in data_quality_judgments},
    }

    missed = [h for h in hurdle_findings if not h.met]
    if missed:
        return GateResult(
            "fail", conviction, fit, dq, gate_score, blend, cutoff, hurdle_findings,
            components, fail_reason=f"hard hurdle miss: {', '.join(h.criterion_id for h in missed)}",
        )
    weakest = min(conviction, fit, dq)
    if weakest < SEVERE_WEAKNESS_FLOOR:
        return GateResult(
            "fail", conviction, fit, dq, gate_score, blend, cutoff, hurdle_findings,
            components, fail_reason="severe weakness guardrail: one IC score below floor",
        )
    if gate_score >= cutoff:
        return GateResult("pass", conviction, fit, dq, gate_score, blend, cutoff,
                          hurdle_findings, components)
    return GateResult(
        "fail", conviction, fit, dq, gate_score, blend, cutoff, hurdle_findings,
        components, fail_reason=f"gate score {gate_score:.0f} below cutoff {cutoff:.0f}",
    )
