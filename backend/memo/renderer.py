"""JSON-to-markdown renderer for structured research report sections.

Converts the structured JSON dicts returned by the LLM (using schemas.py)
into formatted markdown suitable for the final report.

Usage:
    from backend.memo.renderer import render_section_to_markdown
    md = render_section_to_markdown(
        section_title="Company Overview",
        structured=llm_json_output,
        fields=schema["fields"],
    )
"""

from __future__ import annotations

import re

from backend.memo.schemas import HIDDEN_FIELDS


def humanize(field_name: str) -> str:
    """Convert snake_case field names to Title Case.

    Examples:
        revenue_growth        → Revenue Growth
        rd_and_technology     → Rd And Technology
        opening_paragraph     → Opening Paragraph
        tam_and_penetration   → Tam And Penetration
    """
    return field_name.replace("_", " ").title()


# Fields whose content should be rendered without a ### header (they flow as plain prose)
_HEADERLESS_FIELDS = {
    "opening_paragraph",
    "closing_paragraph",
    "synthesis",
    "overall_assessment",
}

# Map field names to nicer display labels
_FIELD_LABELS: dict[str, str] = {
    "core_products_services": "Core Products & Services",
    "industry_ecosystem": "Industry Ecosystem",
    "value_chain": "Value Chain Position",
    "defensibility": "Competitive Defensibility",
    "early_history": "Early History",
    "phase_blocks": "Strategic Phases",
    "price_action": "Price Action",
    "earnings_and_guidance": "Earnings & Guidance",
    "macro_and_sector": "Macro & Sector Context",
    "product_portfolio": "Product Portfolio",
    "rd_and_technology": "R&D & Technology",
    "technology_initiatives": "Technology Initiatives",
    "competitive_tech_position": "Competitive Technology Position",
    "lending_portfolio": "Lending Portfolio",
    "deposit_and_funding": "Deposit & Funding",
    "fee_based_services": "Fee-Based Services",
    "digital_and_technology": "Digital & Technology",
    "product_lines": "Product Lines",
    "underwriting_and_pricing": "Underwriting & Pricing",
    "investment_portfolio": "Investment Portfolio",
    "distribution_and_technology": "Distribution & Technology",
    "property_portfolio": "Property Portfolio",
    "development_pipeline": "Development Pipeline",
    "acquisition_strategy": "Acquisition Strategy",
    "property_technology": "Property Technology",
    "upstream_operations": "Upstream Operations",
    "downstream_and_midstream": "Downstream & Midstream",
    "commodity_and_hedging": "Commodity & Hedging",
    "energy_transition": "Energy Transition",
    "generation_portfolio": "Generation Portfolio",
    "transmission_and_distribution": "Transmission & Distribution",
    "regulatory_rate_base": "Regulatory Rate Base",
    "clean_energy_transition": "Clean Energy Transition",
    "moat_blocks": "Competitive Moats",
    "broad_market": "Broad Market",
    "key_segment": "Key Segment",
    "competitive_landscape_intro": "Competitive Landscape",
    "competitive_landscape_analysis": "Competitive Analysis",
    "competition": "Competition Dynamics",
    "barriers": "Entry Barriers",
    "industry_forces": "Key Industry Forces",
    "tailwinds": "Tailwinds",
    "headwinds": "Headwinds",
    "customer_composition": "Customer Composition",
    "stickiness_and_retention": "Stickiness & Retention",
    "unit_economics": "Unit Economics",
    "working_capital": "Working Capital",
    "deposit_franchise": "Deposit Franchise",
    "loan_book_composition": "Loan Book Composition",
    "interest_rate_sensitivity": "Interest Rate Sensitivity",
    "fee_income_analysis": "Fee Income Analysis",
    "policyholder_base": "Policyholder Base",
    "underwriting_cycle": "Underwriting Cycle",
    "claims_and_reserves": "Claims & Reserves",
    "distribution_economics": "Distribution Economics",
    "tenant_mix_and_quality": "Tenant Mix & Quality",
    "lease_structure": "Lease Structure",
    "occupancy_and_retention": "Occupancy & Retention",
    "rent_dynamics": "Rent Dynamics",
    "offtake_and_contracts": "Offtake & Contracts",
    "commodity_customer_mix": "Commodity Customer Mix",
    "production_economics": "Production Economics",
    "hedging_and_risk_management": "Hedging & Risk Management",
    "ratepayer_base": "Ratepayer Base",
    "regulatory_relationships": "Regulatory Relationships",
    "rate_case_dynamics": "Rate Case Dynamics",
    "demand_and_load_patterns": "Demand & Load Patterns",
    "leadership_team": "Leadership Team",
    "guidance_accuracy": "Guidance Accuracy",
    "strategic_execution": "Strategic Execution",
    "capital_allocation": "Capital Allocation",
    "board_governance": "Board & Governance",
    "tam_and_penetration": "TAM & Penetration",
    "demand_drivers": "Demand Drivers",
    "near_term_catalysts": "Near-Term Catalysts",
    "medium_term_drivers": "Medium-Term Drivers",
    "runway": "Long-Term Runway",
    "at_scale": "At Scale",
    "margin_evolution": "Margin Evolution",
    "revenue_growth": "Revenue Growth",
    "margins": "Margin Structure",
    "cash_flow": "Cash Flow",
    "returns_capital_efficiency": "Returns & Capital Efficiency",
    "leverage_balance_sheet": "Leverage & Balance Sheet",
    "sector_specific_analysis": "Sector-Specific Analysis",
    "financial_quality_flags": "Financial Quality Flags",
    "profitability_comparison": "Profitability Comparison",
    "growth_comparison": "Growth Comparison",
    "leverage_comparison": "Leverage Comparison",
    "efficiency_comparison": "Efficiency Comparison",
    "returns_comparison": "Returns Comparison",
    "regulatory_structural": "Regulatory & Structural Risks",
    "key_risks": "Key Risks",
    "bear_case_triggers": "Bear Case Triggers",
    "sensitivity_assumptions": "Sensitivity Assumptions",
    "litigation": "Litigation & Legal Risks",
}


def _label_for(field_name: str) -> str:
    """Return a display label for a field name."""
    return _FIELD_LABELS.get(field_name, humanize(field_name))


def _render_labeled_blocks(items: list) -> str:
    """Render a list of {label, content} blocks as bold-label paragraphs."""
    if not items or not isinstance(items, list):
        return ""
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = (item.get("label") or item.get("name") or "").strip()
        content = (item.get("content") or item.get("paragraph") or "").strip()
        if not content:
            continue
        if label:
            parts.append(f"**{label}** — {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def _render_table_section(field_name: str, value: dict) -> str:
    """Render a table_section field: intro text + [table placeholder] + analysis text."""
    if not isinstance(value, dict):
        if isinstance(value, str):
            return value
        return ""
    intro = (value.get("intro") or "").strip()
    analysis = (value.get("analysis") or "").strip()
    parts = []
    if intro:
        parts.append(intro)
    if analysis:
        parts.append(analysis)
    return "\n\n".join(parts)


def render_section_to_markdown(
    section_title: str,
    structured: dict,
    fields: list,
) -> str:
    """Convert a structured JSON section dict to formatted markdown.

    Args:
        section_title: The section title (used for the top-level ## header).
        structured: Dict of field_name → value from LLM JSON output.
        fields: List of field descriptors from the schema (schema["fields"]).

    Returns:
        Formatted markdown string for the section body (without the ## header —
        the caller adds that).
    """
    if not structured or not isinstance(structured, dict):
        return ""

    parts: list[str] = []

    for field in fields:
        name = field["name"]
        ftype = field.get("type", "str")

        # Skip internal/hidden fields
        if name in HIDDEN_FIELDS:
            continue

        value = structured.get(name)
        if value is None:
            # Skip missing optional fields silently
            if not field.get("required", True):
                continue
            # Required but missing — skip with no output (fallback caller handles)
            continue

        # Empty string / empty list
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue

        label = _label_for(name)
        is_headerless = name in _HEADERLESS_FIELDS

        if ftype == "str":
            if is_headerless:
                parts.append(value.strip())
            else:
                parts.append(f"### {label}\n\n{value.strip()}")

        elif ftype in ("list", "labeled_blocks"):
            rendered = _render_labeled_blocks(value)
            if rendered:
                if is_headerless:
                    parts.append(rendered)
                else:
                    parts.append(f"### {label}\n\n{rendered}")

        elif ftype == "table_section":
            rendered = _render_table_section(name, value)
            if rendered:
                if is_headerless:
                    parts.append(rendered)
                else:
                    parts.append(f"### {label}\n\n{rendered}")

    return "\n\n".join(p for p in parts if p)
