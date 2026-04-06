"""Validation Layer -- validates Intent JSON and generates deterministic Python scoring code.

Two main functions:
1. validate_intent() -- checks all fields resolve, operators valid, values in range
2. generate_code_from_intent() -- deterministic code generation (NO LLM)

This replaces the LLM-generates-Python approach. The LLM only produces Intent JSON
(structured data), and this module deterministically converts it to sandbox-safe code.
"""

import difflib
from typing import List, Optional, Tuple

from backend.core.intent_schema import ScoringIntent, ScoringRule
from backend.core.metric_schema import (
    METRIC_SCHEMA,
    all_metric_names,
    get_metric,
    resolve_alias,
)


# ---------------------------------------------------------------------------
# Field name correction
# ---------------------------------------------------------------------------

def correction_message(field: str) -> str:
    """Given a bad field name, suggest closest matches from metric_schema.

    Returns a human-readable message with suggestions.
    """
    all_names = all_metric_names()

    # Also include all aliases for better matching
    all_searchable = list(all_names)
    for mdef in METRIC_SCHEMA.values():
        all_searchable.extend(mdef.aliases)

    matches = difflib.get_close_matches(field, all_searchable, n=5, cutoff=0.4)

    # Resolve matches back to canonical names and deduplicate
    canonical_matches = []
    seen = set()
    for m in matches:
        canonical = resolve_alias(m) or m
        if canonical not in seen:
            seen.add(canonical)
            canonical_matches.append(canonical)

    if canonical_matches:
        suggestions = ", ".join(f"'{c}'" for c in canonical_matches[:5])
        return f"Field '{field}' not found. Did you mean {suggestions}?"
    else:
        return f"Field '{field}' not found. No similar metrics found in schema."


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_intent(
    intent: ScoringIntent,
    metric_schema: Optional[dict] = None,
) -> Tuple[bool, List[str]]:
    """Validate a ScoringIntent against the metric schema.

    Checks:
    - All rule fields resolve via resolve_alias()
    - Operators are valid for the metric
    - Values are within typical_range (warning, not hard error)
    - Weights are within 0.5-5.0
    - Logic is "all" or "any"
    - sort_by field resolves (if present)
    - "between" operator has [low, high] value

    Returns:
        (is_valid, errors) -- is_valid is True if no hard errors.
        Warnings are prefixed with "WARNING:" and don't set is_valid to False.
    """
    schema = metric_schema or METRIC_SCHEMA
    errors: List[str] = []
    has_hard_error = False

    # Validate logic
    if intent.logic not in ("all", "any"):
        errors.append(f"Invalid logic '{intent.logic}'. Must be 'all' or 'any'.")
        has_hard_error = True

    # Validate rules
    if not intent.rules:
        errors.append("Intent must have at least one rule.")
        has_hard_error = True

    # Normalize operators (LLMs sometimes return unicode or shorthand)
    _OP_NORMALIZE = {
        "≤": "<=", "≥": ">=", "≠": "!=", "=": "==",
        "le": "<=", "ge": ">=", "lt": "<", "gt": ">",
        "eq": "==", "ne": "!=",
    }
    for rule in intent.rules:
        rule.operator = _OP_NORMALIZE.get(rule.operator, rule.operator)
        # If operator is empty/None, infer from context:
        # - For metrics where higher is better (margins, growth, ROIC), default ">"
        # - For metrics where lower is better (valuation ratios, debt), default "<"
        if not rule.operator or rule.operator.strip() == "":
            _LOWER_IS_BETTER = {"pe", "ps", "pb", "ev_ebitda", "ev_sales", "ev_gp",
                                "debt_equity", "debt_ebitda", "price_earnings",
                                "price_sales", "price_book", "peg"}
            canonical = resolve_alias(rule.field)
            if canonical and canonical in _LOWER_IS_BETTER:
                rule.operator = "<"
            else:
                rule.operator = ">"

    for i, rule in enumerate(intent.rules):
        prefix = f"Rule {i + 1} (field='{rule.field}')"

        # --- Field resolution ---
        canonical = resolve_alias(rule.field)
        if canonical is None:
            suggestion = correction_message(rule.field)
            errors.append(f"{prefix}: {suggestion}")
            has_hard_error = True
            continue  # Can't check operator/range without a valid field

        mdef = schema.get(canonical)
        if mdef is None:
            errors.append(f"{prefix}: Resolved to '{canonical}' but metric definition not found.")
            has_hard_error = True
            continue

        # --- Operator validation ---
        if rule.operator not in mdef.valid_operators:
            valid = ", ".join(mdef.valid_operators)
            errors.append(
                f"{prefix}: Operator '{rule.operator}' not valid for '{canonical}'. "
                f"Valid operators: [{valid}]."
            )
            has_hard_error = True

        # --- Value validation ---
        if rule.operator == "between":
            if not isinstance(rule.value, (list, tuple)) or len(rule.value) != 2:
                errors.append(
                    f"{prefix}: 'between' operator requires value as [low, high], "
                    f"got {rule.value!r}."
                )
                has_hard_error = True
            else:
                low, high = rule.value
                if low > high:
                    errors.append(
                        f"{prefix}: 'between' range is inverted: [{low}, {high}]. "
                        f"Low must be <= high."
                    )
                    has_hard_error = True
                # Range warning for between
                if mdef.typical_range and mdef.data_type not in ("string",):
                    typ_lo, typ_hi = mdef.typical_range
                    if isinstance(typ_lo, (int, float)) and isinstance(typ_hi, (int, float)):
                        if high < typ_lo or low > typ_hi:
                            errors.append(
                                f"WARNING: {prefix}: between [{low}, {high}] is outside "
                                f"typical range ({typ_lo}, {typ_hi}) for '{canonical}'."
                            )
        else:
            if isinstance(rule.value, (list, tuple)):
                errors.append(
                    f"{prefix}: Operator '{rule.operator}' expects a single value, "
                    f"got list {rule.value!r}."
                )
                has_hard_error = True
            elif isinstance(rule.value, (int, float)):
                # Range warning for single value
                if mdef.typical_range and mdef.data_type not in ("string",):
                    typ_lo, typ_hi = mdef.typical_range
                    if isinstance(typ_lo, (int, float)) and isinstance(typ_hi, (int, float)):
                        if rule.value < typ_lo or rule.value > typ_hi:
                            errors.append(
                                f"WARNING: {prefix}: value {rule.value} is outside "
                                f"typical range ({typ_lo}, {typ_hi}) for '{canonical}'."
                            )

        # --- Label-field coherence check ---
        # Catch bugs where the LLM uses the wrong field for a label
        # e.g., field=debt_equity but label="Net income margin floor"
        if rule.label and canonical:
            _LABEL_FIELD_HINTS = {
                "margin": {"gross_margin", "operating_margin", "net_margin", "ebitda_margin", "fcf_margin"},
                "net margin": {"net_margin"},
                "net income margin": {"net_margin"},
                "gross margin": {"gross_margin"},
                "operating margin": {"operating_margin"},
                "fcf yield": {"fcf_yield"},
                "free cash": {"fcf_yield", "fcf_margin"},
                "roic": {"roic"},
                "roe": {"roe"},
                "debt": {"debt_equity", "debt_ebitda"},
                "leverage": {"debt_equity", "debt_ebitda"},
                "revenue growth": {"revenue_growth", "revenue_growth_3y"},
                "earnings growth": {"earnings_growth"},
            }
            label_lower = rule.label.lower()
            for hint_phrase, valid_fields in _LABEL_FIELD_HINTS.items():
                if hint_phrase in label_lower and canonical not in valid_fields:
                    errors.append(
                        f"{prefix}: Label mentions '{hint_phrase}' but field is '{canonical}'. "
                        f"Expected one of: {valid_fields}. Fix the field to match the label."
                    )
                    has_hard_error = True
                    break

        # --- Operator sanity: '==' is almost never correct for a floor/ceiling ---
        if rule.operator == "==" and isinstance(rule.value, (int, float)):
            if rule.label and any(w in rule.label.lower() for w in ("floor", "min", "max", "limit", "cap")):
                errors.append(
                    f"{prefix}: Operator '==' with label '{rule.label}' looks wrong. "
                    f"Floor/min should use '>=', ceiling/max should use '<='."
                )
                has_hard_error = True

        # --- Weight validation ---
        if not (0.5 <= rule.weight <= 5.0):
            errors.append(
                f"{prefix}: Weight {rule.weight} out of range. Must be 0.5-5.0."
            )
            has_hard_error = True

    # Validate sort_by
    if intent.sort_by is not None:
        sort_field = intent.sort_by.get("field")
        if sort_field:
            canonical = resolve_alias(sort_field)
            if canonical is None:
                suggestion = correction_message(sort_field)
                errors.append(f"sort_by: {suggestion}")
                has_hard_error = True
        sort_dir = intent.sort_by.get("direction", "desc")
        if sort_dir not in ("asc", "desc"):
            errors.append(f"sort_by: Invalid direction '{sort_dir}'. Must be 'asc' or 'desc'.")
            has_hard_error = True

    return (not has_hard_error, errors)


# ---------------------------------------------------------------------------
# Normalize intent (resolve aliases to canonical names)
# ---------------------------------------------------------------------------

def normalize_intent(intent: ScoringIntent) -> ScoringIntent:
    """Resolve all aliases to canonical names. Returns a new ScoringIntent."""
    new_rules = []
    for rule in intent.rules:
        canonical = resolve_alias(rule.field)
        new_rules.append(ScoringRule(
            field=canonical if canonical else rule.field,
            operator=rule.operator,
            value=rule.value,
            weight=rule.weight,
            required=rule.required,
            label=rule.label,
        ))

    new_sort_by = None
    if intent.sort_by is not None:
        sort_field = intent.sort_by.get("field", "")
        canonical_sort = resolve_alias(sort_field)
        new_sort_by = {
            "field": canonical_sort if canonical_sort else sort_field,
            "direction": intent.sort_by.get("direction", "desc"),
        }

    return ScoringIntent(
        rules=new_rules,
        logic=intent.logic,
        sort_by=new_sort_by,
        version=intent.version,
    )


# ---------------------------------------------------------------------------
# Deterministic code generation
# ---------------------------------------------------------------------------

def _get_stock_key(canonical_name: str) -> str:
    """Return the key to use in safe_get() for a canonical metric name.

    For most metrics the canonical name IS the stock dict key.
    But some metrics use camelCase keys in the actual stock dict (e.g.
    grossProfitMargin for gross_margin). We return the canonical name
    since safe_get will look up whatever key is in the dict, and the
    screener normalizes to canonical names.
    """
    return canonical_name


def generate_code_from_intent(intent: ScoringIntent) -> str:
    """Generate deterministic Python scoring code from a validated ScoringIntent.

    The generated code:
    - Defines a `def score(stock):` function
    - Uses only safe_get, clamp, normalize (available in sandbox)
    - Produces a dict with 'score' (float 0-10) and 'reason' (str)
    - For required rules: early return 0.0 if condition fails
    - For weighted rules: accumulates score as weighted sum

    The generated code is guaranteed to pass sandbox.validate_ast().
    """
    # Normalize first so we work with canonical names
    intent = normalize_intent(intent)

    lines = []
    lines.append("def score(stock):")
    lines.append('    """Auto-generated scoring function from intent schema."""')

    # Separate required (guard) rules from weighted rules
    guard_rules = [r for r in intent.rules if r.required]
    scored_rules = [r for r in intent.rules if not r.required]

    # --- Required rules: early return 0.0 on failure ---
    if guard_rules:
        lines.append("")
        lines.append("    # Required filters (hard gates)")
    for rule in guard_rules:
        key = _get_stock_key(rule.field)
        default = _default_for_operator(rule.operator, rule.value)
        condition = _build_condition(key, rule.operator, rule.value, default)
        label = rule.label or rule.field
        lines.append(f"    if not ({condition}):")
        lines.append(f"        return {{'score': 0.0, 'reason': 'Failed required filter: {label}'}}")

    # --- Scored rules ---
    use_any_logic = intent.logic == "any"

    if scored_rules:
        if use_any_logic:
            # OR mode: score = best single rule pass × 10.0
            lines.append("")
            lines.append("    # OR scoring: best single rule determines score")
            lines.append("    best_score = 0.0")
            lines.append("")

            for i, rule in enumerate(scored_rules):
                key = _get_stock_key(rule.field)
                default = _default_for_operator(rule.operator, rule.value)
                condition = _build_condition(key, rule.operator, rule.value, default)
                lines.append(f"    # Rule: {rule.label or rule.field} (weight={rule.weight})")
                lines.append(f"    if {condition}:")
                lines.append(f"        best_score = max(best_score, {rule.weight})")
                lines.append("")

            # Normalize: best_score is a weight (0.5-5.0), scale to 0-10
            max_weight = max(r.weight for r in scored_rules)
            lines.append(f"    score_sum = (best_score / {max_weight}) * 10.0 if best_score > 0 else 0.0")
            lines.append("    weight_sum = 1.0")
        else:
            # AND mode: weighted sum (existing behavior)
            lines.append("")
            lines.append("    # Weighted scoring rules")
            lines.append("    score_sum = 0.0")
            lines.append("    weight_sum = 0.0")
            lines.append("")

            for i, rule in enumerate(scored_rules):
                key = _get_stock_key(rule.field)
                default = _default_for_operator(rule.operator, rule.value)
                condition = _build_condition(key, rule.operator, rule.value, default)
                lines.append(f"    # Rule: {rule.label or rule.field} (weight={rule.weight})")
                lines.append(f"    if {condition}:")
                lines.append(f"        score_sum += {rule.weight}")
                lines.append(f"    weight_sum += {rule.weight}")
                lines.append("")
    else:
        # Only guard rules, no weighted scoring
        lines.append("")
        lines.append("    score_sum = 1.0")
        lines.append("    weight_sum = 1.0")

    # --- Final score computation ---
    lines.append("    # Compute final score (0-10 scale)")
    if use_any_logic:
        lines.append("    final = clamp(score_sum, 0.0, 10.0)")
    else:
        lines.append("    if weight_sum > 0:")
        lines.append("        final = (score_sum / weight_sum) * 10.0")
        lines.append("    else:")
        lines.append("        final = 0.0")
    lines.append("    final = clamp(final, 0.0, 10.0)")

    # --- Build reason string ---
    lines.append("")
    lines.append("    # Build reason string with actual values")
    reason_parts = []
    all_rules = guard_rules + scored_rules
    # Show up to 5 key metrics in the reason
    for rule in all_rules[:5]:
        key = _get_stock_key(rule.field)
        default = _default_for_operator(rule.operator, rule.value)
        label = rule.label or rule.field
        reason_parts.append(f"{label}={{safe_get(stock, '{key}', {default})}}")

    reason_template = ", ".join(reason_parts) if reason_parts else "no rules"
    lines.append(f'    reason = f"{reason_template}"')

    # --- Sort-by comment ---
    if intent.sort_by:
        sort_field = intent.sort_by.get("field", "score")
        sort_dir = intent.sort_by.get("direction", "desc")
        lines.append(f"    # sort_by: {sort_field} {sort_dir} (handled by caller)")

    lines.append("")
    lines.append("    return {'score': round(final, 1), 'reason': reason}")
    lines.append("")

    return "\n".join(lines)


def _default_for_operator(operator: str, value) -> str:
    """Return a safe default value string for safe_get based on the operator.

    The default should cause the condition to FAIL when data is missing,
    so missing data doesn't artificially inflate scores.
    """
    if operator in (">", ">="):
        # Default should be lower than threshold so condition fails
        return "0"
    elif operator in ("<", "<="):
        # Default should be higher than threshold so condition fails
        return "999999"
    elif operator == "==":
        return "0"
    elif operator == "between":
        # Default outside the range
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return str(value[0] - 1)
        return "0"
    return "0"


def _build_condition(key: str, operator: str, value, default: str) -> str:
    """Build a Python condition string for a single rule."""
    if operator == "between":
        low, high = value
        return f"{low} <= safe_get(stock, '{key}', {default}) <= {high}"
    elif operator == "==":
        if isinstance(value, str):
            return f'safe_get(stock, "{key}", "") == "{value}"'
        return f"safe_get(stock, '{key}', {default}) == {value}"
    else:
        return f"safe_get(stock, '{key}', {default}) {operator} {value}"
