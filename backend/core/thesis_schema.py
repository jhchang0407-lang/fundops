"""Thesis Distributor Meta-Schema.

Defines the section catalog for thesis generation. The strategy AI uses this
as a template to generate agent_profiles.thesis.section_schema, which controls
which sections the thesis agent writes and what data each section receives.

The meta-schema is a guide, not a constraint — the AI can customize titles,
emphasis, and enable/disable sections based on the investor's strategy.
"""

from __future__ import annotations

from backend.core.utils import safe_float

# Available data fields that sections can reference.
# Dot notation (e.g., "web_research.why_cheap") traverses nested dicts.
ALL_DATA_FIELDS = [
    # Identity
    "ticker", "company_name", "sector", "industry", "is_bank",
    # Price-dependent
    "price", "market_cap", "pe", "fcf_yield", "earnings_yield",
    # Valuation
    "fair_value", "valuation_method", "eps", "owner_eps", "fair_pe",
    "growth_rate", "earnings_growth", "discount_pct",
    # Quality (SEC fundamentals)
    "gross_margin", "operating_margin", "net_margin", "fcf_margin",
    "roic", "roe", "roa", "fcf_conversion",
    # Leverage
    "debt_equity", "current_ratio", "interest_coverage",
    # Growth
    "revenue_growth", "earnings_growth",
    # Absolute
    "revenue", "net_income", "fcf", "fcf_per_share", "dividend_yield",
    # Return decomposition
    "return_sources",
    # Web research
    "web_research.why_cheap", "web_research.bull_case", "web_research.summary",
]


THESIS_META_SCHEMA = {
    "description": "Controls how the thesis agent routes financial data to prose sections. "
                   "The strategy AI adapts this during the conversation: toggling sections, "
                   "changing emphasis, and mapping investor dimensions to sections.",
    "sections": [
        {
            "id": "opportunity",
            "title_default": "The Opportunity",
            "default_enabled": True,
            "purpose": "Why this stock is interesting now — the setup, the dislocation, the variant view",
            "available_data_fields": [
                "price", "discount_pct", "sector", "industry", "market_cap",
                "company_name", "web_research.why_cheap",
            ],
            "typical_dimensions": ["cheapness", "catalyst_type", "moat", "value_creation"],
        },
        {
            "id": "business_quality",
            "title_default": "Business Quality",
            "default_enabled": True,
            "purpose": "Quality of the business — margins, returns on capital, competitive position",
            "available_data_fields": [
                "roic", "roe", "roa", "gross_margin", "operating_margin",
                "net_margin", "fcf_margin", "fcf_conversion", "debt_equity",
                "current_ratio", "interest_coverage",
            ],
            "typical_dimensions": ["quality", "roic_quality", "margin_quality", "moat"],
        },
        {
            "id": "return_thesis",
            "title_default": "Return Thesis",
            "default_enabled": True,
            "purpose": "Where the return comes from — valuation, growth, margin expansion, dividends",
            "available_data_fields": [
                "fair_value", "valuation_method", "eps", "pe", "fair_pe",
                "growth_rate", "earnings_growth", "revenue_growth",
                "return_sources", "discount_pct", "dividend_yield",
            ],
            "typical_dimensions": ["cheapness_valuation", "growth", "margin_expansion"],
        },
        {
            "id": "risks",
            "title_default": "Key Risks",
            "default_enabled": True,
            "purpose": "What could break the thesis — specific, quantified downside scenarios",
            "available_data_fields": [
                "debt_equity", "interest_coverage", "fcf_conversion",
                "revenue_growth", "web_research.bull_case",
            ],
            "typical_dimensions": ["risk", "downside", "trap_risk", "leverage"],
        },
        {
            "id": "capital_allocation",
            "title_default": "Capital Allocation",
            "default_enabled": False,
            "purpose": "How management deploys capital — buybacks, dividends, M&A, reinvestment",
            "enable_when": "Investor emphasizes capital allocation, buybacks, dividend policy, or reinvestment quality",
            "available_data_fields": [
                "dividend_yield", "fcf", "fcf_per_share", "debt_equity",
                "roe", "roic",
            ],
            "typical_dimensions": ["capital_allocation", "reinvestment", "shareholder_return"],
        },
        {
            "id": "catalyst_timeline",
            "title_default": "Catalyst Timeline",
            "default_enabled": False,
            "purpose": "Specific events/catalysts that could unlock value within 6-18 months",
            "enable_when": "Investor is catalyst-driven or has shorter holding period (< 2 years)",
            "available_data_fields": [
                "web_research.why_cheap", "web_research.bull_case",
            ],
            "typical_dimensions": ["catalyst_type", "momentum_signal"],
        },
        {
            "id": "sector_dynamics",
            "title_default": "Sector Dynamics",
            "default_enabled": False,
            "purpose": "Industry structure, competitive position, secular tailwinds/headwinds",
            "enable_when": "Investor strategy is sector-focused or uses sector rotation",
            "available_data_fields": [
                "sector", "industry", "gross_margin", "roic", "revenue_growth",
            ],
            "typical_dimensions": ["moat", "growth", "value_creation", "innovation"],
        },
    ],
    "rules": {
        "min_sections": 3,
        "max_sections": 6,
        "always_include": ["opportunity", "return_thesis", "risks"],
    },
}

# Lookup by section ID for fast access
_SECTION_LOOKUP = {s["id"]: s for s in THESIS_META_SCHEMA["sections"]}


def get_default_section_schema() -> list[dict]:
    """Return the default section_schema (all default_enabled sections).

    Used when constitution has no custom section_schema.
    """
    return [
        {
            "id": s["id"],
            "title": s["title_default"],
            "enabled": s["default_enabled"],
            "emphasis": s["purpose"],
            "data_fields": s["available_data_fields"],
            "dimension_keys": s["typical_dimensions"],
        }
        for s in THESIS_META_SCHEMA["sections"]
    ]


def get_enabled_sections(section_schema: list[dict] | None) -> list[dict]:
    """Return only the enabled sections from a section_schema.

    Falls back to defaults if section_schema is None or empty.
    """
    schema = section_schema or get_default_section_schema()
    return [s for s in schema if s.get("enabled", True)]


def _resolve_dotpath(data: dict, path: str):
    """Resolve a dot-separated path like 'web_research.why_cheap' from a nested dict."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def get_section_data_package(
    section: dict,
    flat_metrics: dict,
    web_research: dict,
    valuation: dict,
) -> str:
    """Extract only the relevant data fields for a section and format as text.

    Returns a formatted string of key-value pairs for injection into the section prompt.
    """
    data_fields = section.get("data_fields", [])
    if not data_fields:
        return ""

    # Build a combined data source for field resolution
    combined = {**flat_metrics}
    combined["web_research"] = web_research or {}
    combined["return_sources"] = flat_metrics.get("return_sources") or valuation.get("return_sources", {})
    combined["fair_value"] = valuation.get("fair_value_base", flat_metrics.get("fair_value", 0))
    combined["valuation_method"] = valuation.get("method", "")
    combined["fair_pe"] = valuation.get("fair_pe", 0)
    combined["growth_rate"] = valuation.get("growth_rate", 0)
    combined["discount_pct"] = flat_metrics.get("discount_pct", 0)

    lines = []
    for field in data_fields:
        val = _resolve_dotpath(combined, field)
        if val is None or val == "" or val == 0:
            continue

        # Format based on type
        label = field.split(".")[-1].replace("_", " ").title()
        if isinstance(val, float):
            if any(k in field for k in ("margin", "roic", "roe", "roa", "growth", "yield", "conversion", "discount")):
                # These are decimals 0-1 from SEC, convert to percentage
                if abs(val) < 1:
                    lines.append(f"- {label}: {val * 100:.1f}%")
                else:
                    lines.append(f"- {label}: {val:.1f}%")
            elif "price" in field or "fair_value" in field or "eps" in field or "fcf_per_share" in field:
                lines.append(f"- {label}: ${val:.2f}")
            elif "revenue" in field or "net_income" in field or "fcf" == field or "market_cap" in field:
                if abs(val) >= 1e9:
                    lines.append(f"- {label}: ${val / 1e9:.1f}B")
                elif abs(val) >= 1e6:
                    lines.append(f"- {label}: ${val / 1e6:.0f}M")
                else:
                    lines.append(f"- {label}: ${val:,.0f}")
            elif "pe" in field.lower() or "fair_pe" in field:
                lines.append(f"- {label}: {val:.1f}x")
            elif "debt_equity" in field or "current_ratio" in field:
                lines.append(f"- {label}: {val:.2f}")
            else:
                lines.append(f"- {label}: {val:.1f}")
        elif isinstance(val, dict):
            # Return sources or similar nested dicts
            parts = [f"{k}: {v}" for k, v in val.items() if v]
            if parts:
                lines.append(f"- {label}: {', '.join(parts)}")
        elif isinstance(val, str) and len(val) > 10:
            # Prose content (web research) — truncate
            truncated = val[:500] + "..." if len(val) > 500 else val
            lines.append(f"\n{label}:\n{truncated}")
        elif isinstance(val, str):
            lines.append(f"- {label}: {val}")

    return "\n".join(lines) if lines else "No data available for this section."


def get_section_dimension_lens(
    section: dict,
    constitution: dict | None,
) -> str:
    """Build a dimension-specific emphasis directive for a section.

    Matches the section's dimension_keys against the constitution's dimensions
    to produce targeted guidance for the LLM.
    """
    if not constitution:
        return ""

    dims = constitution.get("dimensions", {})
    if not dims:
        return ""

    dimension_keys = section.get("dimension_keys", [])
    if not dimension_keys:
        return ""

    matched = []
    for key in dimension_keys:
        # Exact match
        if key in dims:
            matched.append((key, dims[key]))
            continue
        # Substring match (e.g., "roic_quality" matches "roic" dimension)
        for dim_key, dim_val in dims.items():
            if key in dim_key or dim_key in key:
                matched.append((dim_key, dim_val))
                break

    if not matched:
        return ""

    lines = ["INVESTOR FOCUS AREAS (emphasize these in this section):"]
    for key, description in matched:
        label = key.replace("_", " ").title()
        lines.append(f"  - {label}: {description}")

    return "\n".join(lines)


def build_thesis_data_constraints(data: dict) -> str:
    """Build a data constraints block for thesis generation.

    Tells the AI what data is available and what to NOT fabricate.
    Mirrors memo pipeline's _build_data_constraints().
    """
    available = []
    missing = []

    if data.get("price"):
        available.append(f"Live price (${data['price']:.2f})")
    else:
        missing.append("Live market price")

    if data.get("revenue"):
        rev = data["revenue"]
        available.append(f"Revenue (${rev / 1e9:.1f}B)" if rev >= 1e9 else f"Revenue (${rev / 1e6:.0f}M)")
    else:
        missing.append("Revenue figures")

    for label, key in [("Gross margin", "gross_margin"), ("ROIC", "roic"), ("ROE", "roe")]:
        val = safe_float(data.get(key, 0))
        if val:
            available.append(f"{label} ({val * 100:.1f}%)" if abs(val) < 1 else f"{label} ({val:.1f}%)")

    if data.get("eps") or data.get("owner_eps"):
        available.append("EPS from SEC filings")
    else:
        missing.append("EPS data")

    if data.get("web_research") or data.get("web_research.why_cheap"):
        available.append("Web research (why cheap + bull case)")
    else:
        missing.append("Web research context")

    if not available:
        missing.append("No SEC financial data")

    lines = ["## DATA AVAILABILITY (HARD CONSTRAINTS)"]
    if available:
        lines.append("Available: " + "; ".join(available))
    if missing:
        lines.append("NOT available (do NOT fabricate): " + "; ".join(missing))
    lines.append("")
    lines.append("RULES: Only use numbers from the data provided. If a metric is NOT "
                 "available, state that data was unavailable rather than estimating.")
    return "\n".join(lines)


def build_thesis_strategy_lens(constitution: dict | None) -> str:
    """Build a strategy lens directive from the constitution.

    Injected into the system prompt so ALL sections know the investor's philosophy.
    Mirrors memo pipeline's _build_strategy_lens().
    """
    if not constitution:
        return ""

    parts = ["--- STRATEGY LENS ---"]

    north_star = constitution.get("north_star") or constitution.get("north_star_summary")
    if north_star:
        parts.append(f"Investment philosophy: {north_star}")

    style = constitution.get("style_identity")
    if style:
        parts.append(f"Investor style: {style}")

    dims = constitution.get("dimensions", {})
    # Map common dimension types to labeled emphasis lines
    dim_labels = {
        "cheapness": "Valuation emphasis",
        "quality": "Quality emphasis",
        "growth": "Growth perspective",
        "risk": "Risk tolerance",
        "momentum_signal": "Momentum/technical emphasis",
        "catalyst_type": "Catalyst focus",
    }
    for key, label in dim_labels.items():
        if key in dims:
            parts.append(f"{label}: {dims[key]}")

    # Any remaining dimensions not in the standard labels
    extra = {k: v for k, v in dims.items() if k not in dim_labels}
    if extra:
        parts.append("Additional focus areas:")
        for k, v in extra.items():
            parts.append(f"  - {k.replace('_', ' ').title()}: {v}")

    time_horizon = constitution.get("time_horizon")
    if time_horizon:
        parts.append(f"Time horizon: {time_horizon}")

    parts.append("Adapt analysis emphasis to match this strategy.")
    parts.append("--- END STRATEGY LENS ---")
    return "\n".join(parts)
