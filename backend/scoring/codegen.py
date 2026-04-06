"""AI scoring code generator.

Takes a Strategy Profile and generates a Python scoring function using an LLM.

B1 upgrade: Uses a 2-step intent-based approach:
  1. LLM produces Intent JSON (structured output conforming to INTENT_JSON_SCHEMA)
  2. validate_intent() checks fields, operators, ranges against metric_schema
  3. On failure: correction_message() + retry (up to max_retries)
  4. generate_code_from_intent() produces deterministic Python
  5. validate_ast() safety check on generated code

The metric schema is delegated to backend.core.metric_schema (the canonical registry).
"""

import json
import logging
import uuid
from typing import Optional

from backend.core.intent_schema import ScoringIntent, ScoringRule, INTENT_JSON_SCHEMA, INTENT_RESPONSE_FORMAT
from backend.core.metric_schema import METRIC_SCHEMA, all_metric_names, get_metric
from backend.core.validation import (
    validate_intent,
    generate_code_from_intent,
    correction_message,
    normalize_intent,
)
from backend.scoring.sandbox import validate_ast, compile_scoring_function, ScoringCodeError

log = logging.getLogger("fundops.scoring.codegen")


# --- Metric Schema Generation (delegates to metric_schema.py) ---

def build_metric_schema() -> str:
    """Build a human-readable metric schema for the LLM prompt.

    Delegates to the canonical METRIC_SCHEMA registry so the LLM prompt
    always reflects the actual available metrics.
    """
    lines = [
        "AVAILABLE METRICS:",
        "Each metric shows: canonical_name (type) — description. Typical range. Aliases.",
        "",
    ]

    # Group by source for readability
    by_category = {}
    for name, mdef in METRIC_SCHEMA.items():
        # Use data_type as rough category grouping
        cat = mdef.source
        by_category.setdefault(cat, []).append(mdef)

    for source, metrics in by_category.items():
        lines.append(f"--- Source: {source} ---")
        for m in metrics:
            alias_str = ", ".join(m.aliases[:3]) if m.aliases else ""
            range_str = f"Range: {m.typical_range[0]}-{m.typical_range[1]}" if m.typical_range != ("", "") else ""
            sector_str = f" [Sectors: {', '.join(m.sectors)}]" if m.sector_specific else ""
            notes_str = f" {m.notes}" if m.notes else ""
            lines.append(
                f"  {m.canonical_name} ({m.data_type}): {m.display_name}."
                f" {range_str}{sector_str}{notes_str}"
                f" Aliases: [{alias_str}]"
            )
        lines.append("")

    return "\n".join(lines)


# --- Few-Shot Intent Example ---

EXAMPLE_INTENT_JSON = '''{
  "rules": [
    {"field": "roic", "operator": ">", "value": 0.15, "weight": 2.0, "required": false, "label": "High ROIC"},
    {"field": "gross_margin", "operator": ">", "value": 0.40, "weight": 1.5, "required": false, "label": "Strong Gross Margin"},
    {"field": "debt_equity", "operator": "<", "value": 2.0, "weight": 1.0, "required": false, "label": "Low Leverage"},
    {"field": "revenue_growth_3y", "operator": ">", "value": 0.08, "weight": 1.5, "required": false, "label": "Consistent Growth"},
    {"field": "fcf_yield", "operator": ">", "value": 0.03, "weight": 1.0, "required": false, "label": "Decent FCF Yield"},
    {"field": "pe", "operator": "<", "value": 40, "weight": 1.0, "required": true, "label": "Valuation Cap"}
  ],
  "logic": "all",
  "sort_by": {"field": "roic", "direction": "desc"},
  "version": "1.0"
}'''


# --- Legacy Examples (kept for label_map/explanation prompts) ---

EXAMPLE_SCORING_FUNCTION = '''
def score(stock):
    """Score a stock based on cheapness, quality, and growth durability."""
    sector = stock.get('sector', '')
    gap = safe_get(stock, 'growth_gap', 0)
    ey = safe_get(stock, 'earnings_yield', 0)
    cheapness = clamp(gap * 50 + ey * 50, 0, 10)
    roic = safe_get(stock, 'roic', 0)
    gm = safe_get(stock, 'grossProfitMargin', 0)
    quality = clamp(normalize(roic, 0.05, 0.35) * 0.5 + normalize(gm, 0.20, 0.80) * 0.5, 0, 10)
    growth_3y = safe_get(stock, 'revenueGrowth3Y', 0)
    growth = clamp(normalize(growth_3y, 0, 0.20), 0, 10)
    total = cheapness * 0.40 + quality * 0.35 + growth * 0.25
    return {'score': round(total, 1), 'cheapness': round(cheapness, 1),
            'quality': round(quality, 1), 'growth': round(growth, 1),
            'reason': f"{sector}: ROIC {roic*100:.0f}%, GM {gm*100:.0f}%"}
'''


# --- Intent-Based Code Generation Prompt ---

def build_intent_prompt(strategy: dict, memory_context: str = "") -> str:
    """Build the LLM prompt that asks for Intent JSON (not Python code).

    The LLM receives the strategy profile, the available metrics, and the
    INTENT_JSON_SCHEMA. It must return valid JSON conforming to the schema.

    Args:
        strategy: Strategy profile dict.
        memory_context: Persistent memory block (from MemoryStore.format_for_injection).
    """
    metric_schema = build_metric_schema()

    north_star = strategy.get("north_star", "Find good investment opportunities")
    dimensions = strategy.get("dimensions", {})
    sector_routing = strategy.get("sector_routing", {})
    must_have = strategy.get("must_have_signals", [])
    anti_signals = strategy.get("anti_signals", [])
    disqualifiers = strategy.get("disqualifiers", [])
    agent_profiles = strategy.get("agent_profiles", {})
    screener = agent_profiles.get("screener", {})
    screener_weights = screener.get("weights", {})
    # Hard filters: must_have_signals is the primary source.
    # Fall back to screener.filters only if must_have_signals is empty (backward compat).
    screener_filters = screener.get("filters", {}) if not must_have else {}

    dims_text = "\n".join(f"  - {k}: {v}" for k, v in dimensions.items()) if dimensions else "  (no dimensions specified)"
    routing_text = "\n".join(f"  - {k}: {v}" for k, v in sector_routing.items()) if sector_routing else "  (use default logic for all sectors)"
    must_have_text = "\n".join(f"  - {s}" for s in must_have) if must_have else "  (none)"
    anti_text = "\n".join(f"  - {s}" for s in anti_signals) if anti_signals else "  (none)"
    disqualifier_text = "\n".join(f"  - {d}" for d in disqualifiers) if disqualifiers else "  (none)"
    weights_text = "\n".join(f"  - {k}: {v}%" for k, v in screener_weights.items()) if screener_weights else "  (default equal weights)"
    filters_text = "\n".join(f"  - {k}: {v}" for k, v in screener_filters.items()) if screener_filters else "  (no hard filters)"

    schema_json = json.dumps(INTENT_JSON_SCHEMA, indent=2)

    return f"""You are generating a scoring INTENT (structured JSON) for a stock screener.

STRATEGY PROFILE:
  North Star: {north_star}

  Dimensions:
{dims_text}

  Must-Have Signals (hard requirements — create required rules for each):
{must_have_text}

  Anti-Signals (avoid stocks with these — create inverted rules):
{anti_text}

  Disqualifiers (hard exclusions — score=0):
{disqualifier_text}

  Scoring Dimensions & Weights (how much each factor matters — create soft rules):
{weights_text}

  Legacy Hard Filters (only used if Must-Have Signals is empty):
{filters_text}

  Sector Routing:
{routing_text}

{metric_schema}

YOUR TASK:
Translate the strategy above into a JSON object conforming to this schema:

{schema_json}

RULES FOR BUILDING INTENT:
1. Use ONLY metric field names from the AVAILABLE METRICS list above (canonical names or aliases).
2. Each rule tests one metric against a threshold.
3. Use "required": true for hard filters (stock gets score=0 if it fails).
   - ALWAYS create required rules for each Must-Have Signal (e.g. "Gross margin >= 50%" → required rule).
   - ALWAYS create required rules for Disqualifiers (e.g. commodity/cyclical → exclude).
   - If Must-Have Signals is empty, use Legacy Hard Filters instead.
4. Use "required": false for soft scoring rules that contribute to the weighted score.
5. Weights range from 0.5 (minor) to 5.0 (dominant). Scale weights proportionally to the Scoring Dimensions & Weights percentages above.
   - Example: if quality=40%, growth=25%, momentum=20% → quality rules get weight ~4.0, growth ~2.5, momentum ~2.0.
6. Provide a human-readable "label" for each rule.
7. logic should be "all" (weighted sum of all rules) in most cases.
8. CRITICAL: The "field" must match the metric being tested. Do NOT use "pe" for FCF yield — use "fcf_yield". Do NOT use "debt_equity" for ROIC — use "roic". Each rule's field must be the canonical metric name that the rule actually measures.
8. sort_by is optional — set it to the most important metric for ranking.
9. Aim for 5-10 rules total covering the strategy's key dimensions, must-have signals, and anti-signals.
10. Anti-signals should become rules with inverted logic (e.g. "avoid high leverage" → debt_equity < 3.0).

EXAMPLE (quality compounder strategy):
{EXAMPLE_INTENT_JSON}

{"" if not memory_context else f'''
USER CONTEXT (persistent memory — use to inform scoring priorities):
{memory_context}
'''}Return ONLY valid JSON. No markdown fences. No explanation. Just the JSON object.
"""


def build_label_map_prompt(scoring_code: str) -> str:
    """Build prompt to generate human-readable labels for scoring output keys."""
    return f"""Given this Python scoring function, generate a JSON label map.

For each key returned by score() (except 'reason'), provide:
- label: Human-readable name (e.g. "Cheapness", "Quality")
- unit: "score" for 0-10 scores, "pct" for percentages, "x" for ratios
- format: "0.0" for one decimal, "0" for integer

The scoring function:
{scoring_code}

Return ONLY valid JSON. No markdown. Format:
{{"cheapness": {{"label": "Cheapness", "unit": "score", "format": "0.0"}}, ...}}
"""


def build_explanation_prompt(scoring_code: str, strategy: dict) -> str:
    """Build prompt to generate plain English explanation of the scoring logic."""
    north_star = strategy.get("north_star", "")
    return f"""Explain this scoring function in plain English. The user's investment goal is: "{north_star}"

Write 3-5 short paragraphs. Each paragraph covers one scoring dimension.
Use simple language a finance person (not a programmer) would understand.
Do NOT reference code, variable names, or Python syntax.
Explain what each dimension measures and how it's weighted.

The scoring function:
{scoring_code}

Write the explanation now:
"""


# --- Helpers ---

def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (possibly with language tag)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_intent_json(raw_json: str) -> ScoringIntent:
    """Parse raw JSON string into a ScoringIntent dataclass."""
    data = json.loads(raw_json)
    rules = []
    for r in data.get("rules", []):
        rules.append(ScoringRule(
            field=r["field"],
            operator=r["operator"],
            value=r["value"],
            weight=r["weight"],
            required=r["required"],
            label=r.get("label", ""),
        ))
    return ScoringIntent(
        rules=rules,
        logic=data.get("logic", "all"),
        sort_by=data.get("sort_by"),
        version=data.get("version", "1.0"),
    )


def _build_label_map_from_intent(intent: ScoringIntent) -> dict:
    """Build a label map from the intent rules (no LLM needed)."""
    label_map = {
        "score": {"label": "Score", "unit": "score", "format": "0.0"},
    }
    for rule in intent.rules:
        if not rule.required:
            key = rule.field
            label = rule.label or rule.field
            label_map[key] = {"label": label, "unit": "score", "format": "0.0"}
    return label_map


# --- Code Generation (Intent-Based: B1 upgrade) ---

async def generate_scoring_code(llm, strategy: dict, max_retries: int = 3) -> dict:
    """Generate a scoring function from a strategy profile using intent-based approach.

    Flow:
      1. LLM -> Intent JSON (using INTENT_JSON_SCHEMA)
      2. validate_intent() checks fields, operators, ranges
      3. On failure: correction_message() + retry (up to max_retries)
      4. generate_code_from_intent() produces deterministic Python
      5. validate_ast() safety check

    Args:
        llm: LLMClient instance
        strategy: Strategy profile dict
        max_retries: Number of retries on validation failure (default 3)

    Returns:
        {
            "scoring_code": str,
            "label_map": dict,
            "explanation": str,
            "version_id": str,
        }
    """
    # Load persistent memory for user context
    try:
        from backend.api.deps import get_memory
        memory_block = get_memory().format_for_injection()
    except Exception:
        memory_block = ""

    prompt = build_intent_prompt(strategy, memory_context=memory_block)
    accumulated_errors = []
    intent = None

    # --- Step 1-3: LLM -> Intent JSON with validation + retries ---
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0 and accumulated_errors:
                # Build correction prompt with specific validation errors
                error_details = "\n".join(f"  - {e}" for e in accumulated_errors[-1])
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"PREVIOUS ATTEMPT {attempt} FAILED VALIDATION:\n"
                    f"{error_details}\n\n"
                    f"Fix the field names and values, then return corrected JSON."
                )
                result = await llm.generate(
                    retry_prompt, agent="scoring_codegen",
                    response_format=INTENT_RESPONSE_FORMAT,
                )
            else:
                result = await llm.generate(
                    prompt, agent="scoring_codegen",
                    response_format=INTENT_RESPONSE_FORMAT,
                )

            raw_json = _strip_markdown_fences(result.text)

            # Parse JSON into ScoringIntent
            try:
                intent = _parse_intent_json(raw_json)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                error_msg = f"Invalid JSON from LLM: {e}"
                log.warning(f"Intent parse failed (attempt {attempt + 1}): {error_msg}")
                accumulated_errors.append([error_msg])
                continue

            # Validate intent against metric schema
            is_valid, errors = validate_intent(intent)
            if not is_valid:
                hard_errors = [e for e in errors if not e.startswith("WARNING:")]
                log.warning(
                    f"Intent validation failed (attempt {attempt + 1}): "
                    f"{'; '.join(hard_errors)}"
                )
                accumulated_errors.append(hard_errors)
                intent = None
                continue

            # Validation passed (warnings are OK)
            warnings = [e for e in errors if e.startswith("WARNING:")]
            if warnings:
                log.info(f"Intent validation warnings: {'; '.join(warnings)}")
            break

        except Exception as e:
            log.error(f"LLM call failed (attempt {attempt + 1}): {e}")
            accumulated_errors.append([str(e)])

    if intent is None:
        all_errors = [err for batch in accumulated_errors for err in batch]
        raise ScoringCodeError(
            f"Failed to generate valid scoring intent after {max_retries + 1} attempts. "
            f"Errors: {'; '.join(all_errors)}"
        )

    # --- Step 4: Deterministic code generation ---
    scoring_code = generate_code_from_intent(intent)

    # --- Step 5: AST safety check (should always pass for deterministic code) ---
    ast_errors = validate_ast(scoring_code)
    if ast_errors:
        # This should never happen since generate_code_from_intent produces safe code,
        # but guard against it anyway.
        raise ScoringCodeError(
            f"Deterministic code generation produced unsafe code (bug in validation.py): "
            f"{'; '.join(ast_errors)}"
        )

    # Compile to verify it works
    compile_scoring_function(scoring_code)

    # --- Generate label map from intent (deterministic, no LLM needed) ---
    label_map = _build_label_map_from_intent(intent)

    # --- Generate explanation (still uses LLM for natural language) ---
    explanation = ""
    try:
        exp_result = await llm.generate(
            build_explanation_prompt(scoring_code, strategy), agent="scoring_codegen"
        )
        explanation = exp_result.text.strip()
    except Exception as e:
        log.warning(f"Explanation generation failed: {e}")
        explanation = "Scoring logic generated from your strategy profile."

    version_id = f"v-{uuid.uuid4().hex[:8]}"

    return {
        "scoring_code": scoring_code,
        "label_map": label_map,
        "explanation": explanation,
        "version_id": version_id,
    }
