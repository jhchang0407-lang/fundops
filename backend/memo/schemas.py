"""Section schemas for structured JSON output from the research report LLM pipeline.

Each schema describes the fields the LLM must return for a given section.
Field types:
  "str"            — plain string, rendered as a paragraph block
  "list"           — array of labeled blocks: [{"label": str, "content": str}]
  "table_section"  — subsection with intro + analysis text (table injected from financial data)
  "labeled_blocks" — same as list, but semantically distinct for rendering
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# Internal helpers (mirror old pipeline's _LABELED_BLOCK / _table_wrapper)
# ─────────────────────────────────────────────────────────────

# Fields that are internal/metadata and should NOT be rendered
HIDDEN_FIELDS = {"section_number", "section_thesis", "quality_score", "growth_score", "moat_score"}


def _lblock(description: str) -> dict:
    """Labeled block field descriptor — array of {label, content} items."""
    return {"type": "labeled_blocks", "description": description, "required": True}


def _table(intro_desc: str, analysis_desc: str) -> dict:
    """Table section field descriptor — intro + analysis prose around a data table."""
    return {
        "type": "table_section",
        "intro_description": intro_desc,
        "analysis_description": analysis_desc,
        "required": True,
    }


def _str(description: str, required: bool = True) -> dict:
    return {"type": "str", "description": description, "required": required}


# ─────────────────────────────────────────────────────────────
# S2: Company Overview
# ─────────────────────────────────────────────────────────────

_S2 = {
    "title": "Company Overview",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. The single argument this section makes about the company. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. What the company does, scale, life-cycle stage, capital structure summary. Include specific revenue figures, employee count, market position.")},
        {"name": "core_products_services", "type": "labeled_blocks", "required": True,
         "description": "One labeled block per major segment. Intro: 4-6 sentences introducing the segment structure, revenue model, and relative contribution of each segment."},
        {"name": "value_chain", **_str("4-6 sentences. Where the company sits in the value chain, upstream/downstream dependencies, and integration level.")},
        {"name": "defensibility", **_str("4-6 sentences. Structural reason the position is defensible, with specific evidence and competitive comparisons.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S3: Company History & Key Milestones
# ─────────────────────────────────────────────────────────────

_S3 = {
    "title": "Company History & Key Milestones",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. The defining narrative arc. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. The defining arc, origin story, and how it shaped today's company.")},
        {"name": "early_history", **_str("6-10 sentences (at least 100 words). Founding basics, early business model, and initial competitive positioning. Null if company is young.", required=False)},
        {"name": "phase_blocks", "type": "labeled_blocks", "required": True,
         "description": "4-6 phase blocks covering the company's major strategic eras. Each label should be a phase title with years (e.g. '2010-2015: The Pivot to Cloud'). Content: 5-8 sentences per phase with specific events, financial milestones, strategic decisions, and their impact."},
        {"name": "price_action", **_str("4-6 sentences. Recent stock performance context: YTD and 6-month price trajectory, where the stock sits within its 52-week range, any notable volume spikes or trend breaks. Frame the current pricing dynamic — is the stock at highs/lows/range-bound and why?")},
        {"name": "earnings_and_guidance", **_str("4-6 sentences. Most recent quarterly earnings: revenue/EPS vs consensus (beat/miss/inline), management guidance changes, forward estimate revisions. What did the market react to? Any guidance raises, cuts, or notable commentary?")},
        {"name": "macro_and_sector", **_str("4-6 sentences. Macro and sector backdrop: interest rate environment, sector rotation trends, regulatory developments, supply chain or geopolitical factors affecting the industry. How do these external forces shape the current investment setup?")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S4: Product & Technology Strategy (sector-aware)
# ─────────────────────────────────────────────────────────────

_S4_DEFAULT = {
    "title": "Product & Technology Strategy",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. The single argument about the company's products/services and their strategic positioning. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's product/service lineup, market positioning, and strategic direction.")},
        {"name": "product_portfolio", "type": "labeled_blocks", "required": True,
         "description": "One labeled block per major product. Intro: overview of portfolio breadth and positioning."},
        {"name": "rd_and_technology", **_str("4-6 sentences. R&D spending, efficiency, pipeline, and strategic priorities.")},
        {"name": "competitive_tech_position", **_str("4-6 sentences. Technology differentiation vs. competitors.")},
    ],
}

_S4_BANKING = {
    "title": "Banking Products & Services",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's product/service lineup, market positioning, and strategic direction.")},
        {"name": "lending_portfolio", **_str("5-8 sentences. Loan book composition by type (commercial, CRE, consumer, mortgage), credit quality metrics, underwriting standards, and growth strategy.")},
        {"name": "deposit_and_funding", **_str("5-8 sentences. Deposit mix (demand, savings, time), cost of deposits, core deposit ratio, funding strategy, and liquidity management.")},
        {"name": "fee_based_services", **_str("5-8 sentences. Wealth management, investment banking, trading, card services, treasury services — contribution and growth trajectory.")},
        {"name": "digital_and_technology", **_str("4-6 sentences. Digital banking adoption, mobile/online penetration, technology investments, and fintech competitive response.")},
    ],
}

_S4_INSURANCE = {
    "title": "Insurance Products & Strategy",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's product/service lineup, market positioning, and strategic direction.")},
        {"name": "product_lines", **_str("5-8 sentences. Insurance products by line (life, P&C, reinsurance, specialty), distribution channels, geographic mix, and product strategy.")},
        {"name": "underwriting_and_pricing", **_str("5-8 sentences. Underwriting approach, risk selection methodology, pricing discipline, loss ratio management, and cycle positioning.")},
        {"name": "investment_portfolio", **_str("5-8 sentences. Fixed income strategy, asset allocation, duration management, yield optimization, and credit quality.")},
        {"name": "distribution_and_technology", **_str("4-6 sentences. Agency vs. direct distribution, digital capabilities, InsurTech positioning, and claims technology.")},
    ],
}

_S4_REITS = {
    "title": "Property Portfolio & Strategy",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's product/service lineup, market positioning, and strategic direction.")},
        {"name": "property_portfolio", **_str("5-8 sentences. Property types, geographic locations, quality/age, concentration, and portfolio composition strategy.")},
        {"name": "development_pipeline", **_str("5-8 sentences. Active development projects, land bank, expected deliveries and yields, construction costs, and pre-leasing activity.")},
        {"name": "acquisition_strategy", **_str("5-8 sentences. Acquisition criteria, cap rate targets, recent deal activity, disposition strategy, and recycling of capital.")},
        {"name": "property_technology", **_str("4-6 sentences. PropTech adoption, smart building features, sustainability/ESG initiatives, and energy efficiency investments.")},
    ],
}

_S4_ENERGY = {
    "title": "Operations & Asset Base",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's operations, asset base, and strategic direction.")},
        {"name": "upstream_operations", **_str("5-8 sentences. Proved/probable reserves, production volumes (BOE/d), exploration activity, resource basin quality, and reserve life.")},
        {"name": "downstream_and_midstream", **_str("5-8 sentences. Refining capacity/utilization, midstream pipeline/gathering assets, chemicals and specialties businesses.")},
        {"name": "commodity_and_hedging", **_str("5-8 sentences. Commodity price exposure, hedging strategy and coverage, breakeven economics, and price sensitivity analysis.")},
        {"name": "energy_transition", **_str("4-6 sentences. Low-carbon investments, renewable portfolio, carbon capture, emissions reduction targets, and strategic positioning.")},
    ],
}

_S4_UTILITIES = {
    "title": "Generation & Regulatory Strategy",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the company's generation portfolio and regulatory framework.")},
        {"name": "generation_portfolio", **_str("5-8 sentences. Fuel mix (nuclear, gas, coal, wind, solar), total capacity (MW), dispatch economics, capacity factors, and fleet age.")},
        {"name": "transmission_and_distribution", **_str("5-8 sentences. T&D infrastructure scale, grid modernization investments, reliability metrics, storm hardening, and smart grid adoption.")},
        {"name": "regulatory_rate_base", **_str("5-8 sentences. Authorized rate base, pending/recent rate cases, capex recovery mechanism, regulatory lag, and authorized vs. earned ROE.")},
        {"name": "clean_energy_transition", **_str("4-6 sentences. Renewable buildout plan, battery storage, decarbonization timeline, IRA/tax incentive benefits, and state clean energy mandates.")},
    ],
}

_S4_SECTOR_MAP = {
    "banking": _S4_BANKING,
    "insurance": _S4_INSURANCE,
    "reits": _S4_REITS,
    "energy": _S4_ENERGY,
    "utilities": _S4_UTILITIES,
}

# ─────────────────────────────────────────────────────────────
# S5: Competitive Moats
# ─────────────────────────────────────────────────────────────

_S5 = {
    "title": "Competitive Moats",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Overview of the competitive moat landscape and overall moat assessment.")},
        {"name": "moat_blocks", "type": "labeled_blocks", "required": True,
         "description": "3-5 moat sources. Each block: label = moat type name. content = evidence (4-6 sentences of specific evidence with data and comparisons) followed by mechanism (4-6 sentences on how this moat creates durable competitive advantage and sustainability assessment)."},
        {"name": "overall_assessment", **_str("5-8 sentences. Synthesize all moat sources into a unified assessment. Include the moat classification (WIDE, NARROW, or NONE) with clear reasoning.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S6: Industry & Competitive Dynamics
# ─────────────────────────────────────────────────────────────

_S6 = {
    "title": "Industry & Competitive Dynamics",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Overview of the industry structure and the company's positioning.")},
        {"name": "broad_market", **_str("4-6 sentences. Market size, structure, key players, and concentration.")},
        {"name": "key_segment", **_str("4-6 sentences. The company's primary segment, positioning, and share.")},
        {"name": "competitive_landscape_intro", **_str("3-5 sentences introducing the competitive landscape with specific competitor names and positioning.", required=False)},
        {"name": "competitive_landscape_analysis", **_str("3-5 sentences analyzing competitive positioning, market share shifts, and strategic differentiation.", required=False)},
        {"name": "competition", **_str("4-6 sentences. How companies compete, pricing dynamics, differentiation strategies.")},
        {"name": "barriers", **_str("4-6 sentences. Entry barriers, regulatory moats, capital requirements, and switching costs.")},
        {"name": "industry_forces", "type": "labeled_blocks", "required": True,
         "description": "4-6 key industry forces. Each block: label = force name, content = 4-6 sentences of detailed analysis with data and examples."},
        {"name": "tailwinds", **_str("4-6 sentences. Secular and cyclical tailwinds with specific evidence and magnitude of impact.")},
        {"name": "headwinds", **_str("4-6 sentences. Secular and cyclical headwinds with specific evidence and magnitude of impact.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S7: Customer Analysis (sector-aware)
# ─────────────────────────────────────────────────────────────

_S7_DEFAULT = {
    "title": "Customer Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. The key insight about the company's customer/counterparty dynamics. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the customer/counterparty base, key dynamics, and their implications for the business.")},
        {"name": "customer_composition", **_str("4-6 sentences. Customer mix, concentration risk, key accounts, and segment breakdown.")},
        {"name": "stickiness_and_retention", **_str("4-6 sentences. Customer retention rates, switching costs, contract structures, and churn dynamics.")},
        {"name": "unit_economics", **_str("4-6 sentences. Revenue per customer, CAC, LTV, and unit economics trends.")},
        {"name": "working_capital", **_str("4-6 sentences. Working capital cycle, DSO/DPO/DIO trends, and cash conversion.")},
    ],
}

_S7_BANKING = {
    "title": "Deposit & Lending Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the customer/counterparty base, key dynamics, and their implications for the business.")},
        {"name": "deposit_franchise", **_str("5-8 sentences. Core deposit ratio, deposit cost vs. peers, mix by type (demand/savings/time), deposit stability, growth trajectory, and franchise stickiness.")},
        {"name": "loan_book_composition", **_str("5-8 sentences. Loan mix by type, credit quality (NPL/NPA ratios, NCO rates), concentration risk (CRE, C&I), underwriting trends, and reserve coverage.")},
        {"name": "interest_rate_sensitivity", **_str("5-8 sentences. NIM trajectory, asset-liability duration gap, rate cycle positioning, deposit beta, and earnings sensitivity to rate changes.")},
        {"name": "fee_income_analysis", **_str("4-6 sentences. Fee revenue composition, recurring vs. transactional mix, cross-sell penetration, and fee income as percentage of total revenue.")},
    ],
}

_S7_INSURANCE = {
    "title": "Policyholder & Claims Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the policyholder base and key underwriting dynamics.")},
        {"name": "policyholder_base", **_str("5-8 sentences. Policyholder demographics, retention/persistency rates, distribution of risk, lapse rates, and geographic/line diversification.")},
        {"name": "underwriting_cycle", **_str("5-8 sentences. Hard/soft market positioning, pricing power, competitive dynamics, premium growth trends, and cycle management.")},
        {"name": "claims_and_reserves", **_str("5-8 sentences. Loss development patterns, reserve adequacy, prior-year development, catastrophe exposure, and reinsurance protection.")},
        {"name": "distribution_economics", **_str("4-6 sentences. Channel costs (agency vs. direct vs. broker), agent retention, commission structures, and distribution efficiency.")},
    ],
}

_S7_REITS = {
    "title": "Tenant & Lease Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the tenant base and lease dynamics.")},
        {"name": "tenant_mix_and_quality", **_str("5-8 sentences. Tenant industry diversification, credit quality of top tenants, concentration (top 10 tenants as % of rent), weighted average lease term.")},
        {"name": "lease_structure", **_str("5-8 sentences. Lease types (NNN, gross, modified gross), built-in rent escalators, CPI linkages, TI/LC obligations, and lease renewal economics.")},
        {"name": "occupancy_and_retention", **_str("5-8 sentences. Historical occupancy rates, tenant retention/renewal rates, downtime between tenants, and absorption trends.")},
        {"name": "rent_dynamics", **_str("4-6 sentences. Mark-to-market rent opportunity, same-store NOI growth, rent spreads on renewals vs. new leases, and releasing spread trends.")},
    ],
}

_S7_ENERGY = {
    "title": "Production & Commodity Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of production economics and commodity exposure.")},
        {"name": "offtake_and_contracts", **_str("5-8 sentences. Off-take contract structure, take-or-pay agreements, contract duration and renewal profile, and counterparty credit quality.")},
        {"name": "commodity_customer_mix", **_str("5-8 sentences. End-market customer exposure, geographic concentration, domestic vs. export split, and customer industry diversification.")},
        {"name": "production_economics", **_str("5-8 sentences. Per-BOE or per-MCF cost structure, lifting/operating cost, breakeven price, cash margin sensitivity to commodity prices.")},
        {"name": "hedging_and_risk_management", **_str("4-6 sentences. Hedge book coverage and duration, hedging instruments used, basis risk, and financial risk management philosophy.")},
    ],
}

_S7_UTILITIES = {
    "title": "Regulatory & Demand Analysis",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("5-8 sentences. Overview of the ratepayer base and regulatory dynamics.")},
        {"name": "ratepayer_base", **_str("5-8 sentences. Customer counts and growth, residential/commercial/industrial mix, service territory demographics, and load characteristics.")},
        {"name": "regulatory_relationships", **_str("5-8 sentences. State commission dynamics, regulatory philosophy (constructive vs. adversarial), historical rate case outcomes, and political environment.")},
        {"name": "rate_case_dynamics", **_str("5-8 sentences. Pending and recent rate cases, authorized ROE vs. earned ROE, test year methodology, formula rate plans, and regulatory lag.")},
        {"name": "demand_and_load_patterns", **_str("4-6 sentences. Load growth trends, electrification impacts (EV, data centers), peak demand management, weather sensitivity, and energy efficiency effects.")},
    ],
}

_S7_SECTOR_MAP = {
    "banking": _S7_BANKING,
    "insurance": _S7_INSURANCE,
    "reits": _S7_REITS,
    "energy": _S7_ENERGY,
    "utilities": _S7_UTILITIES,
}

# ─────────────────────────────────────────────────────────────
# S8: Management & Capital Allocation
# ─────────────────────────────────────────────────────────────

_S8 = {
    "title": "Management & Capital Allocation",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Overview of leadership quality and capital allocation philosophy.")},
        {"name": "leadership_team", "type": "labeled_blocks", "required": True,
         "description": "One block per key executive. Label = name and title. Content = 4-6 sentences on background, tenure, and track record."},
        {"name": "guidance_accuracy", **_str("4-6 sentences. Track record of meeting/beating guidance, specific examples.")},
        {"name": "strategic_execution", **_str("4-6 sentences. Major strategic initiatives and their execution outcomes.")},
        {"name": "capital_allocation", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences introducing the 3-year capital allocation pattern with specific figures.",
         "analysis_description": "4-6 sentences. ROIC trend, R&D effectiveness, M&A track record, buyback quality, TSR decomposition."},
        {"name": "board_governance", **_str("4-6 sentences. Board composition, independence, expertise, and governance quality.")},
        {"name": "overall_assessment", **_str("4-6 sentences. Synthesize management quality with specific strengths and concerns.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S9: Growth Prospects & Catalysts
# ─────────────────────────────────────────────────────────────

_S9 = {
    "title": "Growth Prospects & Catalysts",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Overview of the growth opportunity and key catalysts.")},
        {"name": "tam_and_penetration", **_str("4-6 sentences. TAM size, current penetration rate, and expansion potential with specific figures.")},
        {"name": "demand_drivers", **_str("4-6 sentences. Key demand drivers, secular trends, and cyclical factors.")},
        {"name": "near_term_catalysts", "type": "labeled_blocks", "required": True,
         "description": "3-4 near-term catalysts. Each block: label = catalyst name, content = 4-6 sentences of detailed analysis on timing, magnitude, and probability."},
        {"name": "medium_term_drivers", "type": "labeled_blocks", "required": True,
         "description": "3-4 medium-term growth drivers. Each block: label = driver name, content = 4-6 sentences on how this drives growth and what could accelerate or derail it."},
        {"name": "runway", **_str("4-6 sentences. Long-term growth runway, end-market maturity, and optionality.")},
        {"name": "at_scale", **_str("4-6 sentences. What the business looks like at scale, margin structure, and competitive positioning.")},
        {"name": "margin_evolution", **_str("4-6 sentences. Expected margin trajectory, operating leverage, and mix shift impact.")},
        {"name": "growth_score", **_str("Growth score 0-100. An integer reflecting overall growth quality and durability.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S10: Financial Analysis (generic/default — sector overrides handled in get_section_schema)
# ─────────────────────────────────────────────────────────────

_S10_DEFAULT = {
    "title": "Financial Analysis",
    "word_target": 700,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Open with the single most investment-relevant financial insight. State 1-2 supporting dynamics with specific numbers. Frame what the subsections below will examine.")},
        {"name": "revenue_growth", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. 5yr CAGR, acceleration/deceleration, primary drivers, organic vs inorganic growth, and revenue mix evolution.",
         "analysis_description": "3-5 sentences. Key insight about revenue quality, sustainability of growth rate, comparison to peers and industry growth, and forward trajectory."},
        {"name": "margins", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Gross margin, operating margin, expansion/contraction trend, operating leverage, and mix effects.",
         "analysis_description": "3-5 sentences. Key margin trend, sustainability, peer comparison, and what drives margin variability."},
        {"name": "cash_flow", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. FCF level and margin, conversion quality, capex intensity, and working capital dynamics.",
         "analysis_description": "3-5 sentences. Earnings quality assessment, capex trend, FCF yield, and capital allocation implications."},
        {"name": "returns_capital_efficiency", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. ROIC level and trend, comparison to WACC, incremental returns, and peer benchmarking.",
         "analysis_description": "3-5 sentences. Value creation assessment, ROE decomposition, moat connection, and capital efficiency trajectory."},
        {"name": "financial_quality_flags", "type": "labeled_blocks", "required": True,
         "description": "3-7 labeled blocks. For each triggered financial quality flag (provided in the facts), diagnose: (1) cite the specific numbers that triggered it, (2) explain the cause from business context/filings, (3) compare to peers where relevant, (4) state what it signals for the investment case. If no flags triggered, write 1-2 blocks on the cleanest quality signals."},
        {"name": "synthesis", **_str("4-6 sentences. Synthesize the financial profile into a clear investment-relevant conclusion.")},
        {"name": "quality_score", **_str("Financial quality score 0-100. An integer reflecting overall earnings and balance sheet quality.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S11: Peer Financial Benchmarking
# ─────────────────────────────────────────────────────────────

_S11_DEFAULT = {
    "title": "Peer Financial Benchmarking",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Frame the peer comparison and key takeaways.")},
        {"name": "profitability_comparison", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Frame the profitability comparison with context on why these metrics matter for this industry.",
         "analysis_description": "4-6 sentences. Subject margin profile vs peers, specific gaps, what drives differences, and implications for competitive positioning."},
        {"name": "growth_comparison", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Frame the growth comparison with context on industry growth rates and cycle position.",
         "analysis_description": "4-6 sentences. Subject growth vs peers, market share trends, organic vs inorganic drivers, and sustainability assessment."},
        {"name": "leverage_comparison", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Frame the leverage comparison — D/E, net debt/EBITDA, interest coverage — and why balance-sheet strength matters for this industry.",
         "analysis_description": "4-6 sentences. Explain how leverage compares to peers, whether it constrains or enables growth, and implications for risk."},
        {"name": "efficiency_comparison", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Frame the efficiency comparison — asset turnover, capex efficiency, working capital, or operating efficiency — for this industry.",
         "analysis_description": "4-6 sentences. Explain how operational efficiency compares to peers and what drives the gaps."},
        {"name": "returns_comparison", "type": "table_section", "required": True,
         "intro_description": "3-5 sentences. Frame the returns comparison — ROIC, ROCE, FCF conversion, and capital allocation effectiveness — for this industry.",
         "analysis_description": "4-6 sentences. Explain how returns on invested capital compare to peers, whether capital allocation is disciplined, and what drives the gaps."},
        {"name": "synthesis", **_str("4-6 sentences. Overall peer positioning assessment and investment implications.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# S13: Risk Assessment
# ─────────────────────────────────────────────────────────────

_S13 = {
    "title": "Risk Assessment",
    "word_target": 600,
    "fields": [
        {"name": "section_thesis", **_str("1-2 sentences. HIDDEN.")},
        {"name": "opening_paragraph", **_str("4-6 sentences. Overview of the risk profile and most critical risks.")},
        {"name": "regulatory_structural", **_str("4-6 sentences. Regulatory environment and structural risks specific to this company.", required=False)},
        {"name": "key_risks", "type": "labeled_blocks", "required": True,
         "description": "4-6 key risks. Each block: label = risk name. Content = transmission (4-6 sentences on how this risk transmits to financials with specific scenario analysis and magnitude) followed by probability assessment and key metrics to monitor."},
        {"name": "bear_case_triggers", "type": "labeled_blocks", "required": True,
         "description": "3-5 bear case triggers. Each block: label = trigger name. Content = description of the trigger, estimated probability, and the monitoring metric to watch."},
        {"name": "sensitivity_assumptions", "type": "labeled_blocks", "required": True,
         "description": "3-5 key sensitivity assumptions. Each block: label = assumption name. Content = the downside scenario if the assumption is wrong and the monitoring metric."},
        {"name": "litigation", **_str("3-5 sentences on any notable litigation, regulatory investigations, or legal risks.", required=False)},
        {"name": "closing_paragraph", **_str("4-6 sentences. Risk-adjusted conclusion on whether the risk profile is appropriate for the expected return.")},
    ],
}

# ─────────────────────────────────────────────────────────────
# Master registry
# ─────────────────────────────────────────────────────────────

RESEARCH_SCHEMAS: dict[int, dict] = {
    2: _S2,
    3: _S3,
    4: _S4_DEFAULT,
    5: _S5,
    6: _S6,
    7: _S7_DEFAULT,
    8: _S8,
    9: _S9,
    10: _S10_DEFAULT,
    11: _S11_DEFAULT,
    13: _S13,
}


def _detect_sector_key(sector: str, industry: str) -> str:
    """Map sector/industry strings to the canonical sector key for schema dispatch."""
    s = (sector or "").lower().strip()
    ind = (industry or "").lower().strip()

    if "bank" in ind or "bank" in s or "thrift" in ind or "credit union" in ind:
        return "banking"
    if "insurance" in ind or "reinsur" in ind:
        return "insurance"
    if "reit" in ind or "real estate investment trust" in ind or s == "real estate":
        return "reits"
    if s == "energy" or "oil" in ind or "gas" in ind or "mining" in ind:
        return "energy"
    if s == "utilities" or "utility" in ind or "electric" in ind or "water" in ind:
        return "utilities"
    return "default"


def get_section_schema(section_num: int, sector: str = "", industry: str = "") -> dict:
    """Return the appropriate schema for a section, applying sector overrides for S4/S7.

    Args:
        section_num: Section number (2-13, excluding 12).
        sector: Company sector string (from data.profile.sector).
        industry: Company industry string (from data.profile.industry).

    Returns:
        Schema dict with keys: title, word_target, fields.
    """
    sector_key = _detect_sector_key(sector, industry)

    if section_num == 4:
        return _S4_SECTOR_MAP.get(sector_key, _S4_DEFAULT)
    if section_num == 7:
        return _S7_SECTOR_MAP.get(sector_key, _S7_DEFAULT)

    return RESEARCH_SCHEMAS.get(section_num, {})


# ─────────────────────────────────────────────────────────────
# Investment Memo Extraction Schemas
# ─────────────────────────────────────────────────────────────
# These define structured data to extract from each investment memo section.
# Unlike research schemas (which control generation), these extract key
# structured findings from already-generated prose.

INVESTMENT_EXTRACTION_SCHEMAS: dict[str, dict] = {
    "opportunity": {
        "type": "object",
        "properties": {
            "variant_view": {"type": "string", "description": "What the market is missing, 1-2 sentences"},
            "dislocation_type": {"type": "string", "enum": ["earnings_miss", "sector_rotation", "management_change", "macro_fear", "misunderstood_model", "other"]},
            "key_strengths": {"type": "array", "items": {"type": "string"}, "description": "3-4 durable competitive advantages"},
            "catalyst": {"type": "string", "description": "Primary catalyst for re-rating"},
            "catalyst_timeline": {"type": "string", "description": "Expected timeline for catalyst (e.g. '6-12 months')"},
        },
        "required": ["variant_view", "key_strengths"],
    },
    "valuation": {
        "type": "object",
        "properties": {
            "base_fair_value": {"type": "number", "description": "Base case fair value ($)"},
            "bull_fair_value": {"type": "number", "description": "Bull case fair value ($)"},
            "bear_fair_value": {"type": "number", "description": "Bear case fair value ($)"},
            "base_upside_pct": {"type": "number", "description": "Base case upside (%)"},
            "bear_downside_pct": {"type": "number", "description": "Bear case downside (%)"},
            "primary_method": {"type": "string", "description": "Primary valuation method used"},
            "key_assumption": {"type": "string", "description": "Most important valuation assumption"},
        },
        "required": ["base_fair_value", "bear_fair_value", "primary_method"],
    },
    "financial_quality": {
        "type": "object",
        "properties": {
            "quality_score": {"type": "integer", "description": "Overall financial quality 0-100"},
            "revenue_quality": {"type": "string", "enum": ["high", "moderate", "low"], "description": "Recurring, predictable, growing?"},
            "margin_trend": {"type": "string", "enum": ["expanding", "stable", "contracting"]},
            "capital_efficiency": {"type": "string", "enum": ["excellent", "good", "fair", "poor"], "description": "ROIC vs WACC"},
            "balance_sheet": {"type": "string", "enum": ["fortress", "healthy", "adequate", "stretched", "weak"]},
            "key_financial_concern": {"type": "string", "description": "Single biggest financial concern, or 'none'"},
        },
        "required": ["quality_score", "margin_trend", "capital_efficiency"],
    },
    "risks": {
        "type": "object",
        "properties": {
            "bear_case_fair_value": {"type": "number", "description": "Bear case fair value ($)"},
            "top_risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "risk": {"type": "string"},
                        "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                },
                "description": "Top 3-5 risks with probability and impact",
            },
            "thesis_breakers": {"type": "array", "items": {"type": "string"}, "description": "2-3 conditions that would invalidate the thesis"},
        },
        "required": ["top_risks", "thesis_breakers"],
    },
}

# Map section titles (normalized) to extraction schema keys
_INVESTMENT_SECTION_MAP = {
    "opportunity": "opportunity",
    "opportunity brief": "opportunity",
    "valuation": "valuation",
    "valuation analysis": "valuation",
    "financial": "financial_quality",
    "financial quality": "financial_quality",
    "financial analysis": "financial_quality",
    "risk": "risks",
    "risks": "risks",
    "risks & bear case": "risks",
    "risk assessment": "risks",
}


def get_investment_extraction_schema(section_title: str) -> dict | None:
    """Return the extraction schema for an investment memo section title.

    Returns None if no schema matches (section will keep prose-only output).
    """
    normalized = section_title.lower().strip()
    for key, schema_key in _INVESTMENT_SECTION_MAP.items():
        if key in normalized:
            return INVESTMENT_EXTRACTION_SCHEMAS.get(schema_key)
    return None


def build_json_schema_prompt(schema: dict) -> str:
    """Build the JSON schema block to embed in the LLM prompt.

    Returns a compact instruction block describing each required field so the
    LLM knows exactly what JSON object to return.
    """
    lines = ["You must return a valid JSON object with EXACTLY the following fields:"]
    lines.append("{")

    fields = schema.get("fields", [])
    for i, field in enumerate(fields):
        name = field["name"]
        ftype = field.get("type", "str")
        desc = field.get("description", "")
        comma = "," if i < len(fields) - 1 else ""

        if name in HIDDEN_FIELDS:
            # Still include in prompt so LLM fills it, but mark as internal
            lines.append(f'  "{name}": "<string — {desc}>"' + comma)
        elif ftype == "str":
            lines.append(f'  "{name}": "<string — {desc}>"' + comma)
        elif ftype in ("list", "labeled_blocks"):
            lines.append(f'  "{name}": [' + comma)
            lines.append(f'    {{"label": "<short topic name, 2-6 words>", "content": "<detailed paragraph>"}}')
            lines.append(f'  ]  // {desc}')
        elif ftype == "table_section":
            intro_d = field.get("intro_description", "3-5 sentences of intro.")
            analysis_d = field.get("analysis_description", "3-5 sentences of analysis.")
            lines.append(f'  "{name}": {{')
            lines.append(f'    "intro": "<{intro_d}>",')
            lines.append(f'    "analysis": "<{analysis_d}>"')
            lines.append(f'  }}' + comma)

    lines.append("}")
    lines.append("")
    lines.append(
        "IMPORTANT: Return ONLY the JSON object. No markdown fences, no preamble, no trailing text. "
        "All string values must be complete analytical prose — not placeholders."
    )
    return "\n".join(lines)
