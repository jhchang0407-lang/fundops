"""Governed AI-assisted XBRL tag mapping (ADR-0015).

The deterministic GAAP tag-map (sec_bulk.GAAP_TAG_METRICS) covers common tags;
many sector lines (REIT FFO/capex components, bank/insurance KPIs) are reported
under tags it doesn't know, so they never become observations. This module lets
a governed AI mapper PROPOSE a mapping from a retained unmapped tag to a known
Supported Financial Metric — but only behind hard deterministic governance:

  - LAZY: only runs for entities where a useful metric is missing (caller passes
    the missing set); it never exhaustively analyses every custom tag.
  - VALIDATED: every proposal passes a deterministic validator (unit/data-type
    compatibility, value-shape vs the metric's typical range, no conflict with an
    existing accepted mapping, never a HARD-GATE metric) BEFORE acceptance.
  - EVIDENCED: a rejected proposal is retained with its reason as data-quality
    evidence; it creates NO observation and carries no decision authority.
  - COMPANY-LOCAL FIRST: an accepted mapping is local (accepted_local). Global
    promotion needs repeated cross-company evidence and is out of scope here.

Offline-safe: with no provider configured the AI gateway returns the stub, which
proposes nothing — so unit tests and offline syncs never invent a mapping.
"""

from __future__ import annotations

import logging

from backend.core import metric_schema
from backend.core.ai import get_ai
from backend.domain import metric_catalog
from backend.domain.metric_catalog import MAPPING_VERSION

log = logging.getLogger("fundops.ingest.ai_mapping")

CAPABILITY = "financial_tag_mapping"

SYSTEM = (
    "You map an unmapped SEC XBRL tag to ONE known Supported Financial Metric, "
    "using the tag's reported field definition (label/description) as the primary "
    "evidence. Propose a mapping ONLY when the definition clearly supports it; "
    "when unsure, return target_metric=null. Never guess — a wrong mapping "
    "corrupts a financial metric."
)

SHAPE = ('{"target_metric": "metric id or null", "confidence": 0.0, '
         '"rationale": "one line citing the field definition"}')


def _stub(_seed: int = 0) -> dict:
    """Offline default: never propose a mapping (governance-safe)."""
    return {"target_metric": None, "confidence": 0.0,
            "rationale": "offline stub — no mapping proposed"}


def validate_mapping(target_metric: str, fact: dict,
                     existing_metrics: set[str] | None = None) -> tuple[bool, str]:
    """Deterministic pre-accept governance (ADR-0015 ¶2). Returns (ok, reason)."""
    canonical = metric_schema.resolve_alias(target_metric) or target_metric
    mdef = metric_schema.get_metric(canonical)
    if mdef is None:
        return False, f"unknown target metric {target_metric!r}"

    # Never let an AI proposal feed a hard-gate metric (screening/IC authority).
    if metric_catalog.supports_hard_gate(canonical):
        return False, f"{canonical} is a hard-gate metric — AI mappings are not eligible"

    # Conflict: a deterministic/accepted mapping already feeds this metric.
    if existing_metrics and canonical in existing_metrics:
        return False, f"{canonical} already has an accepted mapping for this entity"

    # Unit / data-type compatibility: a USD line can't become a ratio/percent.
    unit = str(fact.get("unit") or "").upper()
    is_money = unit.startswith("USD") and "SHARES" not in unit
    if mdef.data_type in ("percent",) and is_money:
        return False, f"unit {unit} is monetary but {canonical} is a percent metric"
    if mdef.data_type == "int" and "SHARES" not in unit and not is_money:
        return False, f"unit {unit} incompatible with {canonical} ({mdef.data_type})"

    # Value-shape sanity vs the metric's typical range (loose 5x band tolerance).
    value = fact.get("value")
    rng = mdef.typical_range if isinstance(mdef.typical_range, (tuple, list)) else None
    if isinstance(value, (int, float)) and rng and len(rng) == 2 \
            and all(isinstance(x, (int, float)) for x in rng):
        lo, hi = rng
        span = (hi - lo) or abs(hi) or 1.0
        if value < lo - 5 * span or value > hi + 5 * span:
            return False, (f"value {value:g} is far outside the typical range "
                           f"[{lo:g}, {hi:g}] for {canonical}")
    return True, f"mapped to {canonical} (field definition supports it)"


async def propose_mappings(stores, entity_id: str, missing_metrics: list[str],
                           run_id: str | None = None) -> dict:
    """LAZY governed proposal pass for one entity. Only considers unmapped facts
    when `missing_metrics` is non-empty (a Material Coverage Gap exists). Returns
    {accepted, rejected, considered}. Accepted mappings create an observation;
    rejected proposals are retained as evidence with no decision authority."""
    if not missing_metrics:
        return {"accepted": 0, "rejected": 0, "considered": 0}
    facts = stores.financial.unmapped_facts(entity_id)
    if not facts:
        return {"accepted": 0, "rejected": 0, "considered": 0}

    wanted = {metric_schema.resolve_alias(m) or m for m in missing_metrics}
    # Metrics already fed by a deterministic (or prior) mapping — a genuine
    # conflict. Frozen on entry: additional PERIODS of a tag we accept this run
    # must NOT count as conflicts against the mapping they belong to.
    pre_existing = {r["metric"] for r in stores.financial.observations(entity_id, limit=100_000)}
    accepted_tag: dict[str, str] = {}  # metric -> the tag (concept) accepted this run
    accepted = rejected = 0
    ai = get_ai()
    for fact in facts:
        user = (
            f"Unmapped SEC tag: {fact['concept']}\n"
            f"Field definition: {fact.get('field_label') or '(none)'}\n"
            f"Unit: {fact.get('unit')}  Period: {fact.get('period_end')}  "
            f"Value: {fact.get('value')}\n"
            f"Candidate target metrics (only these are useful here): "
            f"{sorted(wanted)}\n"
            "Map the tag to ONE of the candidate metrics, or null."
        )
        try:
            result = await ai.complete_json(
                CAPABILITY, SYSTEM, user, SHAPE, tier="fast", run_id=run_id, stub=_stub)
        except Exception as exc:  # operational failure: skip, never invent
            log.debug("tag-mapping call failed for %s: %s", fact["concept"], exc)
            continue
        result = result if isinstance(result, dict) else {}
        target = result.get("target_metric")
        if not target:
            continue  # the model declined — leave the fact unmapped
        canonical = metric_schema.resolve_alias(str(target)) or str(target)
        confidence = result.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) else None

        if canonical not in wanted:
            reason = f"{canonical} is not among the missing metrics requested"
        elif canonical in accepted_tag and accepted_tag[canonical] != fact["concept"]:
            reason = f"a different tag already maps to {canonical} for this entity"
        else:
            # First period of a mapping checks the genuine pre-existing conflict;
            # a FURTHER period of the SAME accepted tag skips it (it is the same
            # mapping, so its full history should land, like a deterministic one).
            conflict_set = set() if canonical in accepted_tag else pre_existing
            ok, reason = validate_mapping(canonical, fact, conflict_set)
            if ok:
                stores.financial.set_mapping(
                    fact["id"], "accepted_local", canonical, confidence, reason, MAPPING_VERSION)
                stores.financial.add_observation(
                    entity_id, canonical, fact["period_end"], fact["period_type"], fact["value"],
                    unit=fact.get("unit"), is_calculated=False,
                    lineage={"source": "ai_mapping", "tag": fact["concept"],
                             "mapping_version": MAPPING_VERSION, "confidence": confidence})
                accepted_tag[canonical] = fact["concept"]
                accepted += 1
                continue
        stores.financial.set_mapping(
            fact["id"], "rejected", None, confidence, reason, MAPPING_VERSION)
        rejected += 1
    return {"accepted": accepted, "rejected": rejected, "considered": len(facts)}
