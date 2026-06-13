"""Strategy Wiring: deterministic Settings Projection (ADR-0002).

An accepted Constitution version is compiled — never AI-authored — into
per-capability settings. Ambiguity becomes a Review Item instead of an
invented default. Capability wiring summaries are durable projection text
with version provenance.
"""

from __future__ import annotations

from typing import Any

from backend.domain import labels, metric_catalog
from backend.domain.criteria import (
    Criterion, ic_hurdles, normalized_rank_weights, rank_criteria,
    research_review_criteria, screen_criteria,
)

CAPABILITIES = ("screener", "thesis", "ic_review", "memo", "portfolio_review")

# Funnel defaults from CONTEXT.md relationships.
SCREENER_REVIEW_SET_SIZE = 50
SCREENER_HANDOFF_COUNT = 20
THESIS_SELECTION_COUNT = 10
DEFAULT_IC_BLEND = {"conviction": 0.45, "constitution_fit": 0.35, "data_quality": 0.20}
DEFAULT_IC_CUTOFF = 70.0
THESIS_RETURN_CAP_THRESHOLD = 5.0  # expected-return % below which selection score is capped (global, fixed)


def project_settings(
    criteria: list[Criterion],
    north_star: str | None,
    ic_config: dict | None = None,
    universe: dict | None = None,
) -> dict[str, dict]:
    """Compile the Constitution into per-capability settings + review items.

    Returns {capability: {"settings": .., "summary": str, "review_items": [..]}}.
    """
    ic_config = ic_config or {}
    out: dict[str, dict] = {}

    # --- Screener -----------------------------------------------------------
    screens = screen_criteria(criteria)
    ranks = rank_criteria(criteria)
    weights = normalized_rank_weights(criteria)
    review: list[str] = []
    if not screens:
        review.append("No screening requirements defined; Screener would pass the whole universe.")
    if not ranks:
        review.append("No ranking priorities expressed; equal-weight ranking blend applied by default.")
    requirements = [c.to_dict() for c in screens]
    ranking = [
        {**c.to_dict(), "normalized_weight": round(weights.get(c.criterion_id, 0.0), 4)}
        for c in ranks
    ]
    key_financials = _key_financials(screens, ranks, weights)
    out["screener"] = {
        "settings": {
            "requirements": requirements,
            "ranking_blend": ranking,
            "key_financials": key_financials,
            "review_set_size": SCREENER_REVIEW_SET_SIZE,
            "handoff_count": SCREENER_HANDOFF_COUNT,
            "universe": universe or {"name": "Russell 2000", "source": "default"},
        },
        "summary": _screener_summary(screens, ranks, universe),
        "review_items": review,
    }

    # --- Thesis --------------------------------------------------------------
    rr = research_review_criteria(criteria)
    out["thesis"] = {
        "settings": {
            "research_emphasis": north_star or "",
            "research_review_criteria": [c.to_dict() for c in rr],
            "selection_count": THESIS_SELECTION_COUNT,
            "return_cap_threshold": THESIS_RETURN_CAP_THRESHOLD,
        },
        "summary": _thesis_summary(north_star, rr),
        "review_items": [],
    }

    # --- IC Review ------------------------------------------------------------
    # AI-drafted proposals may carry optional fields as explicit null rather
    # than omitting them; treat null the same as absent (dict.get's default
    # only fires on a missing key, never on a present None).
    hurdles = ic_hurdles(criteria)
    blend = dict(DEFAULT_IC_BLEND)
    blend.update({k: v for k, v in (ic_config.get("gate_score_blend") or {}).items()
                  if v is not None})
    cutoff_raw = ic_config.get("pass_cutoff")
    cutoff = float(cutoff_raw) if cutoff_raw is not None else DEFAULT_IC_CUTOFF
    ic_review_items: list[str] = []
    if not hurdles:
        ic_review_items.append(
            "No hard IC hurdles defined; IC verdicts rely on the gate score alone."
        )
    out["ic_review"] = {
        "settings": {
            "hurdles": [c.to_dict() for c in hurdles],
            "gate_score_blend": blend,
            "pass_cutoff": cutoff,
            "north_star": north_star or "",
        },
        "summary": _ic_summary(hurdles, blend, cutoff),
        "review_items": ic_review_items,
    }

    # --- Memo ------------------------------------------------------------------
    out["memo"] = {
        "settings": {
            "strategy_emphasis": north_star or "",
            "research_review_criteria": [c.to_dict() for c in rr],
        },
        "summary": (
            f"Investment Memos use the fixed seven-section outline with emphasis on: "
            f"{north_star}" if north_star else
            "Investment Memos use the fixed seven-section outline with neutral emphasis."
        ),
        "review_items": [],
    }

    # --- Portfolio Review ---------------------------------------------------------
    out["portfolio_review"] = {
        "settings": {
            "pressure_signals": ["thesis_broken", "thesis_watching", "concentration", "stale_coverage"],
            "opportunity_signals": ["ic_pass", "memo_backed", "screener_rank"],
            "concentration_flag_pct": 20.0,
        },
        "summary": (
            "Portfolio Review surfaces holdings under thesis or sizing pressure and "
            "non-held Constitution-fit opportunities, ranked by evidence. It never issues "
            "buy or sell instructions."
        ),
        "review_items": [],
    }
    return out


def _key_financials(screens, ranks, weights) -> list[str]:
    """Stable Screener Key Financials strip: screened metrics ordered by ranking priority."""
    metrics: list[str] = []
    ranked = sorted(ranks, key=lambda c: -(weights.get(c.criterion_id, 0.0)))
    priority = [c.metric for c in ranked if c.metric] + [c.metric for c in screens if c.metric]
    for m in priority:
        if m not in metrics and metric_catalog.is_supported(m):
            metrics.append(m)
    return metrics[:6]


def _fmt_value(c: Criterion) -> str:
    """Human threshold text ('≥ 15%'), unit-aware via the labels module."""
    return labels.threshold_display(c.metric, c.operator, c.value)


def _screener_summary(screens, ranks, universe) -> str:
    uni = (universe or {}).get("name", "Russell 2000")
    parts = [f"Screens {uni}."]
    if screens:
        reqs = "; ".join(labels.describe_criterion(c) for c in screens)
        parts.append(f"Requirements: {reqs}.")
    else:
        parts.append("No hard requirements; all universe members are candidates.")
    if ranks:
        parts.append("Ranked by " + ", ".join(
            labels.metric_label(c.metric) if c.metric else c.criterion_id
            for c in ranks) + ".")
    else:
        parts.append("Equal-weight ranking.")
    parts.append(
        f"Keeps top {SCREENER_REVIEW_SET_SIZE} for review; top {SCREENER_HANDOFF_COUNT} hand off to Thesis."
    )
    return " ".join(parts)


def _thesis_summary(north_star, rr) -> str:
    parts = [
        "Thesis answers the fixed research scope (why the opportunity exists, mispricing, "
        "return sources, strategy fit, path, key risk, evidence freshness)."
    ]
    if north_star:
        parts.append(f"Emphasis: {north_star}.")
    if rr:
        parts.append("Research review attention: " + "; ".join(c.interpretation or c.criterion_id for c in rr) + ".")
    parts.append(f"Top {THESIS_SELECTION_COUNT} completed theses by return profile advance to IC Review.")
    return " ".join(parts)


def _ic_summary(hurdles, blend, cutoff) -> str:
    parts = []
    if hurdles:
        parts.append("Hard hurdles: " + "; ".join(
            labels.describe_criterion(c) for c in hurdles) + ".")
    parts.append(
        f"Gate score = {blend['conviction']:.0%} conviction + {blend['constitution_fit']:.0%} "
        f"constitution fit + {blend['data_quality']:.0%} data quality; pass at {cutoff:.0f}/100."
    )
    parts.append("A confirmed hurdle miss fails automatically unless the user overrides.")
    return " ".join(parts)
