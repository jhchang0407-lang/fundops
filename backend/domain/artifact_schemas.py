"""Structured Workflow Artifact contracts (ADR-0020, ADR-0037).

Every completed artifact carries the same Artifact Kernel; each artifact kind
adds a typed body. Stored payloads are canonical; rendered markdown/PDF are
derivatives. Validation here decides whether a generated output may become a
Completed Workflow Artifact — invalid outputs are retained as rejected
provenance instead (ADR-0034).
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSIONS = {
    "screener_snapshot": "1.0",
    "thesis": "1.0",
    "ic_verdict": "1.0",
    "investment_memo": "1.0",
    "thesis_health_check": "1.0",
    "portfolio_review": "1.0",
    "learning_card": "1.0",
    "filing_note": "1.0",
    "industry_note": "1.0",
}

# Fixed Investment Memo Outline: reading order (ADR-0013 / CONTEXT).
MEMO_OUTLINE = [
    ("current_setup", "Current Setup & Variant View",
     ["why_now", "recent_events", "market_view", "variant_view", "evidence_quality"]),
    ("business_quality", "Business Quality",
     ["business_model", "products_and_value_chain", "moat_and_defensibility",
      "management_and_capital_allocation", "quality_watch_items"]),
    ("industry_growth", "Industry and Growth",
     ["industry_structure", "customer_and_demand_dynamics", "growth_drivers",
      "competitive_position", "growth_watch_items"]),
    ("financial_quality", "Financial Quality",
     ["revenue_and_margin_quality", "cash_flow_and_balance_sheet", "returns_on_capital",
      "peer_benchmarking", "financial_watch_items"]),
    ("valuation", "Valuation",
     ["valuation_method", "base_case", "upside_and_downside_cases",
      "memo_return_drivers", "key_assumptions"]),
    ("risks", "Risks, Bear Case & Kill Criteria",
     ["key_risks", "bear_case", "sensitivity_factors", "kill_criteria", "risk_watch_items"]),
    ("decision_summary", "Decision Summary",
     ["investment_case_summary", "decision", "open_questions", "evidence_gaps"]),
]
# Generation order differs: risks before valuation; synthesis sections last.
MEMO_GENERATION_ORDER = [
    "business_quality", "industry_growth", "financial_quality",
    "risks", "valuation", "current_setup", "decision_summary",
]
MEMO_DECISIONS = ("attractive", "watchlist", "avoid", "needs_more_evidence")

THESIS_RETURN_COMPONENTS = (
    "valuation_gap", "growth", "margin_expansion", "capital_returns", "multiple_rerating",
)

# Fixed Thesis Research Scope questions (CONTEXT).
THESIS_SCOPE_FIELDS = (
    "why_opportunity_exists", "why_mispriced", "return_sources",
    "constitution_fit", "path_or_catalyst", "key_risk", "evidence_freshness",
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def make_kernel(
    kind: str,
    ticker: str | None,
    entity_id: str | None,
    constitution_version_id: str | None,
    evidence_bundle_id: str | None,
    generated_at: str,
) -> dict:
    return {
        "kind": kind,
        "schema_version": SCHEMA_VERSIONS[kind],
        "ticker": ticker,
        "entity_id": entity_id,
        "constitution_version_id": constitution_version_id,
        "evidence_bundle_id": evidence_bundle_id,
        "generated_at": generated_at,
        "validation": {"ok": True, "errors": [], "warnings": []},
        "citations": [],
    }


def _require(payload: dict, keys: list[str], errors: list[str], where: str) -> None:
    for k in keys:
        v = payload.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"{where}: missing required field {k!r}")


def validate_kernel(payload: dict) -> list[str]:
    errors: list[str] = []
    _require(payload, ["kind", "schema_version", "generated_at"], errors, "kernel")
    kind = payload.get("kind")
    if kind not in SCHEMA_VERSIONS:
        errors.append(f"kernel: unknown artifact kind {kind!r}")
    return errors


def validate_thesis(payload: dict) -> ValidationResult:
    errors = validate_kernel(payload)
    body = payload.get("body") or {}
    _require(body, ["summary"], errors, "thesis")
    scope = body.get("scope") or {}
    for f in THESIS_SCOPE_FIELDS:
        if not str(scope.get(f, "")).strip():
            errors.append(f"thesis: research scope question {f!r} unanswered")
    rp = body.get("return_potential") or {}
    if not isinstance(rp.get("expected_return_pct"), (int, float)):
        errors.append("thesis: return_potential.expected_return_pct must be numeric")
    comps = rp.get("components") or {}
    unknown = [k for k in comps if k not in THESIS_RETURN_COMPONENTS]
    if unknown:
        errors.append(f"thesis: unknown return components {unknown}")
    warnings = []
    if comps and isinstance(rp.get("expected_return_pct"), (int, float)):
        total = sum(v for v in comps.values() if isinstance(v, (int, float)))
        if abs(total - rp["expected_return_pct"]) > max(5.0, 0.25 * abs(rp["expected_return_pct"])):
            warnings.append(
                f"thesis: return components sum to {total:.1f}% vs stated "
                f"{rp['expected_return_pct']:.1f}% — return-source support is weak"
            )
    return ValidationResult(not errors, errors, warnings)


def validate_memo(payload: dict) -> ValidationResult:
    errors = validate_kernel(payload)
    body = payload.get("body") or {}
    sections = body.get("sections") or {}
    for sec_id, _title, subsections in MEMO_OUTLINE:
        sec = sections.get(sec_id)
        if not isinstance(sec, dict):
            errors.append(f"memo: missing section {sec_id!r}")
            continue
        if not str(sec.get("section_thesis", "")).strip():
            errors.append(f"memo: section {sec_id!r} missing internal section thesis")
        subs = sec.get("subsections") or {}
        for sub_id in subsections:
            if not str(subs.get(sub_id, "")).strip():
                errors.append(f"memo: section {sec_id!r} missing subsection {sub_id!r}")
    decision = ((sections.get("decision_summary") or {}).get("fields") or {}).get("decision")
    if decision not in MEMO_DECISIONS:
        errors.append(f"memo: decision must be one of {MEMO_DECISIONS}, got {decision!r}")
    valuation = body.get("valuation") or {}
    warnings: list[str] = []
    if not isinstance(valuation.get("fair_value_base"), (int, float)):
        warnings.append("memo: no deterministic base fair value attached to valuation section")
    if not body.get("monitoring_plan_items"):
        warnings.append("memo: monitoring plan has no items; thesis health will be empty")
    return ValidationResult(not errors, errors, warnings)


def validate_ic_verdict(payload: dict) -> ValidationResult:
    errors = validate_kernel(payload)
    body = payload.get("body") or {}
    if body.get("verdict") not in ("pass", "fail"):
        errors.append("ic_verdict: verdict must be pass or fail")
    for k in ("conviction", "constitution_fit", "data_quality", "gate_score"):
        v = body.get(k)
        if not isinstance(v, (int, float)) or not (0 <= v <= 100):
            errors.append(f"ic_verdict: {k} must be 0-100")
    if not str(body.get("rationale", "")).strip():
        errors.append("ic_verdict: missing verdict rationale")
    return ValidationResult(not errors, errors, [])


def validate_screener_snapshot(payload: dict) -> ValidationResult:
    errors = validate_kernel(payload)
    body = payload.get("body") or {}
    _require(body, ["rank"], errors, "screener_snapshot")
    if not isinstance(body.get("pass_evidence"), list):
        errors.append("screener_snapshot: pass_evidence must be a list")
    return ValidationResult(not errors, errors, [])


VALIDATORS = {
    "thesis": validate_thesis,
    "investment_memo": validate_memo,
    "ic_verdict": validate_ic_verdict,
    "screener_snapshot": validate_screener_snapshot,
}


def validate_artifact(payload: dict) -> ValidationResult:
    kind = payload.get("kind")
    validator = VALIDATORS.get(kind)
    if validator is None:
        errors = validate_kernel(payload)
        return ValidationResult(not errors, errors, [])
    return validator(payload)
