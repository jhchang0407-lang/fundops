"""Comprehensive screener filter definitions.

Every filter the screener supports, with metadata for the Settings UI.
The SEC data layer computes all fundamentals from raw XBRL.
yfinance provides prices only. FMP adds estimates (optional paid).

Filters are organized by category. Each filter has:
  - key: config key name
  - label: human-readable name
  - description: what it measures
  - type: "range" (min/max), "bool", "select", "multi_select"
  - default_min / default_max: default filter bounds (None = no filter)
  - unit: "pct", "ratio", "usd", "years", "days", "score", None
  - source: "sec" | "yfinance" | "computed" | "fmp_optional"
  - tier: 1 (core) | 2 (advanced) | 3 (pro)
  - sector_specific: list of sectors where this filter applies, or None for all
"""

from __future__ import annotations

FILTER_CATEGORIES = [
    {
        "id": "size",
        "label": "Size & Classification",
        "filters": [
            {"key": "min_market_cap", "label": "Min Market Cap", "type": "range", "default_min": 500_000_000, "default_max": None, "unit": "usd", "source": "yfinance", "tier": 1, "presets": {"nano": 0, "micro": 50_000_000, "small": 300_000_000, "mid": 2_000_000_000, "large": 10_000_000_000, "mega": 200_000_000_000}},
            {"key": "max_market_cap", "label": "Max Market Cap", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "yfinance", "tier": 1},
            {"key": "min_revenue", "label": "Min Revenue", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "sec", "tier": 1, "description": "Annual revenue (TTM)"},
            {"key": "max_revenue", "label": "Max Revenue", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "sec", "tier": 2},
            {"key": "min_enterprise_value", "label": "Min Enterprise Value", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "computed", "tier": 2, "description": "Market cap + debt - cash"},
            {"key": "excluded_sectors", "label": "Exclude Sectors", "type": "multi_select", "default_min": None, "default_max": None, "unit": None, "source": "sec", "tier": 1, "options": ["Technology", "Healthcare", "Financial Services", "Consumer Cyclical", "Consumer Defensive", "Industrials", "Energy", "Utilities", "Real Estate", "Basic Materials", "Communication Services"]},
            # included_industries: populated dynamically from SEC SIC codes at runtime (not a static list)
            {"key": "min_price", "label": "Min Price", "type": "range", "default_min": 1.0, "default_max": None, "unit": "usd", "source": "yfinance", "tier": 1},
            {"key": "max_price", "label": "Max Price", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "yfinance", "tier": 2},
        ],
    },
    {
        "id": "valuation",
        "label": "Valuation",
        "filters": [
            {"key": "max_pe", "label": "Max P/E (TTM)", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "sec", "tier": 1, "description": "Price / trailing 12-month EPS"},
            {"key": "min_pe", "label": "Min P/E", "type": "range", "default_min": 0, "default_max": None, "unit": "ratio", "source": "sec", "tier": 2},
            {"key": "max_pb", "label": "Max P/B", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 1, "description": "Price / book value per share"},
            {"key": "max_ps", "label": "Max P/S", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 1, "description": "Market cap / revenue"},
            {"key": "max_ev_ebitda", "label": "Max EV/EBITDA", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 1, "description": "Enterprise value / EBITDA"},
            {"key": "max_ev_revenue", "label": "Max EV/Revenue", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 2},
            {"key": "max_ev_fcf", "label": "Max EV/FCF", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 2},
            {"key": "max_pfcf", "label": "Max P/FCF", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 1, "description": "Price / free cash flow per share"},
            {"key": "min_fcf_yield", "label": "Min FCF Yield", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 1, "description": "FCF / market cap. >5% attractive, >8% deep value"},
            {"key": "min_earnings_yield", "label": "Min Earnings Yield", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 1, "description": "EBIT / EV. >8% attractive"},
            {"key": "max_peg", "label": "Max PEG Ratio", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 2, "description": "P/E / growth rate. <1 = cheap, >2 = expensive"},
            {"key": "max_ptangible_book", "label": "Max P/Tangible Book", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 3},
        ],
    },
    {
        "id": "backward_dcf",
        "label": "Backward DCF (Implied Growth)",
        "description": "What growth rate is the market pricing in? Compare to actual growth to find mispricing.",
        "filters": [
            {"key": "max_implied_growth", "label": "Max Implied Growth", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 1, "description": "Growth rate priced into current stock price. Low implied + high actual = potentially cheap"},
            {"key": "min_growth_gap", "label": "Min Growth Gap (Actual - Implied)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 1, "description": "Actual revenue growth minus implied growth. Positive = market underestimates growth"},
            {"key": "backward_dcf_discount_rate", "label": "Discount Rate for Backward DCF", "type": "range", "default_min": 10, "default_max": 10, "unit": "pct", "source": "config", "tier": 2, "description": "Cost of equity used in backward DCF calculation (CAPM-based)"},
        ],
    },
    {
        "id": "profitability",
        "label": "Profitability",
        "filters": [
            {"key": "min_gross_margin", "label": "Min Gross Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1, "description": "(Revenue - COGS) / Revenue"},
            {"key": "min_operating_margin", "label": "Min Operating Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1},
            {"key": "min_net_margin", "label": "Min Net Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1},
            {"key": "min_ebitda_margin", "label": "Min EBITDA Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2},
            {"key": "min_fcf_margin", "label": "Min FCF Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "Free cash flow / revenue"},
            {"key": "min_roe", "label": "Min ROE", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1, "description": "Net income / shareholder equity. >15% strong"},
            {"key": "min_roa", "label": "Min ROA", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "Net income / total assets. >5% solid"},
            {"key": "min_roic", "label": "Min ROIC", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1, "description": "NOPAT / invested capital. >15% excellent, >20% exceptional"},
            {"key": "min_roce", "label": "Min ROCE", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3},
            {"key": "allow_negative_earnings", "label": "Allow Unprofitable Companies", "type": "bool", "default_min": False, "default_max": None, "unit": None, "source": "config", "tier": 1},
        ],
    },
    {
        "id": "growth",
        "label": "Growth",
        "filters": [
            {"key": "min_revenue_growth_1y", "label": "Min Revenue Growth (1Y)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1},
            {"key": "min_revenue_growth_3y", "label": "Min Revenue Growth (3Y CAGR)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1},
            {"key": "min_revenue_growth_5y", "label": "Min Revenue Growth (5Y CAGR)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2},
            {"key": "min_eps_growth_1y", "label": "Min EPS Growth (1Y)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1},
            {"key": "min_eps_growth_3y", "label": "Min EPS Growth (3Y CAGR)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2},
            {"key": "min_fcf_growth_1y", "label": "Min FCF Growth (1Y)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2},
            {"key": "min_ebitda_growth_1y", "label": "Min EBITDA Growth (1Y)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3},
            {"key": "min_growth_consistency", "label": "Min Growth Consistency", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2, "description": "% of years with positive revenue growth over 5yr period. 100% = grew every year"},
            {"key": "max_revenue_growth", "label": "Max Revenue Growth (1Y)", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3, "description": "Filter out hypergrowth (often unsustainable)"},
        ],
    },
    {
        "id": "cash_flow",
        "label": "Cash Flow Quality",
        "filters": [
            {"key": "min_fcf_yield_pct", "label": "Min FCF Yield", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 1},
            {"key": "min_fcf_conversion", "label": "Min FCF Conversion", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 1, "description": "FCF / net income. >80% healthy, >100% excellent"},
            {"key": "min_income_quality", "label": "Min Income Quality", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "sec", "tier": 2, "description": "Operating cash flow / net income. >1.0 = earnings backed by cash"},
            {"key": "max_capex_to_revenue", "label": "Max CapEx/Revenue", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "<5% asset-light, >15% capital-intensive"},
            {"key": "min_owner_earnings_ps", "label": "Min Owner Earnings/Share", "type": "range", "default_min": None, "default_max": None, "unit": "usd", "source": "sec", "tier": 2, "description": "Buffett-style: NI + D&A - maintenance capex"},
            {"key": "positive_fcf_required", "label": "Require Positive FCF", "type": "bool", "default_min": True, "default_max": None, "unit": None, "source": "config", "tier": 1},
        ],
    },
    {
        "id": "balance_sheet",
        "label": "Balance Sheet & Leverage",
        "filters": [
            {"key": "max_debt_equity", "label": "Max Debt/Equity", "type": "range", "default_min": None, "default_max": 3.0, "unit": "ratio", "source": "sec", "tier": 1, "description": "<0.5 conservative, <1.0 moderate, >2.0 leveraged"},
            {"key": "max_net_debt_ebitda", "label": "Max Net Debt/EBITDA", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "sec", "tier": 1, "description": "<2x healthy, <3x acceptable, >4x risky"},
            {"key": "min_interest_coverage", "label": "Min Interest Coverage", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "sec", "tier": 1, "description": "EBIT / interest expense. >3x safe, >5x strong"},
            {"key": "min_current_ratio", "label": "Min Current Ratio", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "sec", "tier": 2, "description": "Current assets / current liabilities. >1.5 healthy"},
            {"key": "max_goodwill_pct", "label": "Max Goodwill % of Assets", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3, "description": "High goodwill = acquisition risk"},
        ],
    },
    {
        "id": "quality_scores",
        "label": "Quality & Composite Scores",
        "filters": [
            {"key": "min_piotroski", "label": "Min Piotroski F-Score", "type": "range", "default_min": None, "default_max": None, "unit": "score", "source": "computed", "tier": 1, "description": "0-9 financial strength score. >7 strong, <3 weak"},
            {"key": "min_altman_z", "label": "Min Altman Z-Score", "type": "range", "default_min": None, "default_max": None, "unit": "score", "source": "computed", "tier": 2, "description": ">2.99 safe, 1.81-2.99 grey zone, <1.81 distress risk"},
            {"key": "max_beneish_m", "label": "Max Beneish M-Score", "type": "range", "default_min": None, "default_max": None, "unit": "score", "source": "computed", "tier": 3, "description": "<-2.22 unlikely manipulation, >-2.22 possible"},
            {"key": "min_quality_score", "label": "Min Quality Score (composite)", "type": "range", "default_min": None, "default_max": None, "unit": "score", "source": "computed", "tier": 1, "description": "0-10 composite: margins, returns, cash quality, leverage"},
        ],
    },
    {
        "id": "dividends",
        "label": "Dividends",
        "filters": [
            {"key": "min_dividend_yield", "label": "Min Dividend Yield", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2},
            {"key": "max_payout_ratio", "label": "Max Payout Ratio", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "<60% sustainable, >80% risky"},
            {"key": "requires_dividend", "label": "Require Dividend", "type": "bool", "default_min": False, "default_max": None, "unit": None, "source": "config", "tier": 2},
        ],
    },
    {
        "id": "technical",
        "label": "Price & Technical",
        "filters": [
            {"key": "max_range_position", "label": "Max 52-Week Range Position", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "yfinance", "tier": 2, "description": "0% = at 52w low, 100% = at 52w high. <30% = near lows"},
            {"key": "min_pct_from_high", "label": "Min % Below 52-Week High", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "yfinance", "tier": 2, "description": "Negative values (e.g., -20% means 20% below high)"},
            {"key": "max_beta", "label": "Max Beta", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "yfinance", "tier": 2, "description": "<1 less volatile than market, >1 more volatile"},
            {"key": "min_beta", "label": "Min Beta", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "yfinance", "tier": 3},
        ],
    },
    {
        "id": "sector_banking",
        "label": "Banking Sector",
        "sector_specific": ["Financial Services"],
        "description": "Bank-specific metrics from SEC XBRL (NIM, efficiency, credit quality)",
        "filters": [
            {"key": "min_nim", "label": "Min Net Interest Margin", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "Net interest income / earning assets"},
            {"key": "max_efficiency_ratio", "label": "Max Efficiency Ratio", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "Non-interest expense / revenue. Lower = more efficient. <55% excellent"},
            {"key": "max_npl_ratio", "label": "Max NPL Ratio", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3, "description": "Non-performing loans / total loans"},
            {"key": "min_reserve_coverage", "label": "Min Reserve Coverage", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3, "description": "Loan loss reserves / NPLs. >100% = well-reserved"},
        ],
    },
    {
        "id": "sector_tech",
        "label": "Technology / SaaS",
        "sector_specific": ["Technology"],
        "description": "Tech-specific metrics computed from SEC filings",
        "filters": [
            {"key": "min_rule_of_40", "label": "Min Rule of 40", "type": "range", "default_min": None, "default_max": None, "unit": "score", "source": "computed", "tier": 2, "description": "Revenue growth % + operating margin %. >40 = healthy SaaS"},
            {"key": "max_rd_intensity", "label": "Max R&D Intensity", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "R&D spend / revenue"},
            {"key": "max_sbc_to_revenue", "label": "Max SBC/Revenue", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 2, "description": "Stock-based compensation dilution. <10% acceptable, >20% concerning"},
            {"key": "min_deferred_revenue_growth", "label": "Min Deferred Revenue Growth", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "sec", "tier": 3, "description": "Leading indicator of future revenue"},
        ],
    },
    {
        "id": "sector_reits",
        "label": "REITs",
        "sector_specific": ["Real Estate"],
        "description": "REIT-specific metrics",
        "filters": [
            {"key": "min_ffo_yield", "label": "Min FFO Yield", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2, "description": "Funds from operations / price. REIT equivalent of earnings yield"},
            {"key": "max_p_ffo", "label": "Max P/FFO", "type": "range", "default_min": None, "default_max": None, "unit": "ratio", "source": "computed", "tier": 2, "description": "Price / FFO per share. REIT equivalent of P/E"},
            {"key": "min_nav_discount", "label": "Min NAV Discount", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2, "description": "% below net asset value. Positive = trading below NAV"},
        ],
    },
    {
        "id": "relative",
        "label": "Relative to Sector",
        "description": "Compare metrics to sector medians. Positive = above median.",
        "filters": [
            {"key": "min_gm_vs_sector", "label": "Min Gross Margin vs Sector Median", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2},
            {"key": "min_roic_vs_sector", "label": "Min ROIC vs Sector Median", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2},
            {"key": "min_ey_vs_sector", "label": "Min Earnings Yield vs Sector Median", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2, "description": "Higher earnings yield than sector = relatively cheap"},
            {"key": "min_growth_vs_sector", "label": "Min Revenue Growth vs Sector Median", "type": "range", "default_min": None, "default_max": None, "unit": "pct", "source": "computed", "tier": 2},
        ],
    },
]


def get_all_filters() -> list[dict]:
    """Return flat list of all filter definitions (non-mutating copy)."""
    filters = []
    for cat in FILTER_CATEGORIES:
        for f in cat["filters"]:
            copy = {**f, "category": cat["id"], "category_label": cat["label"]}
            filters.append(copy)
    return filters


def get_filter_categories() -> list[dict]:
    """Return filter categories with their filters for Settings UI."""
    return FILTER_CATEGORIES


def get_active_filters(config: dict) -> dict[str, dict]:
    """Extract active filters from a screener config dict.

    Returns {filter_key: {"min": value, "max": value}} for filters
    that have non-None values set in the config.
    """
    active = {}
    all_filters = get_all_filters()
    filter_keys = {f["key"] for f in all_filters}

    for key, value in config.items():
        if key in filter_keys and value is not None:
            if isinstance(value, dict):
                active[key] = value
            else:
                active[key] = {"min": value, "max": None}

    return active


# Default screener presets
SCREENER_PRESETS = {
    "value": {
        "label": "Value Investor",
        "description": "Cheap stocks with strong balance sheets. Graham/Buffett style.",
        "filters": {
            "min_market_cap": 500_000_000,
            "min_pe": 0,
            "max_pe": 20,
            "min_gross_margin": 30,
            "min_roe": 10,
            "max_debt_equity": 1.5,
            "min_fcf_conversion": 70,
            "min_earnings_yield": 5,
            "min_piotroski": 6,
            "positive_fcf_required": True,
            "allow_negative_earnings": False,
        },
    },
    "quality_compounder": {
        "label": "Quality Compounder",
        "description": "High-quality businesses growing consistently. Thomas's style.",
        "filters": {
            "min_market_cap": 2_000_000_000,
            "min_gross_margin": 40,
            "min_roic": 15,
            "min_revenue_growth_3y": 8,
            "min_growth_consistency": 80,
            "min_fcf_conversion": 80,
            "max_debt_equity": 2.0,
            "max_sbc_to_revenue": 15,
            "positive_fcf_required": True,
        },
    },
    "deep_value": {
        "label": "Deep Value",
        "description": "Significantly undervalued by backward DCF. Contrarian.",
        "filters": {
            "min_market_cap": 300_000_000,
            "max_implied_growth": 3,
            "min_growth_gap": 5,
            "min_fcf_yield_pct": 6,
            "min_earnings_yield": 8,
            "max_debt_equity": 2.0,
            "min_piotroski": 5,
            "positive_fcf_required": True,
        },
    },
    "dividend_growth": {
        "label": "Dividend Growth",
        "description": "Growing dividends with sustainable payouts.",
        "filters": {
            "min_market_cap": 2_000_000_000,
            "min_dividend_yield": 1.5,
            "max_payout_ratio": 70,
            "min_revenue_growth_3y": 3,
            "min_fcf_conversion": 70,
            "max_debt_equity": 2.0,
            "requires_dividend": True,
        },
    },
    "growth_at_reasonable_price": {
        "label": "GARP",
        "description": "Growth at a Reasonable Price. PEG + quality filters.",
        "filters": {
            "min_market_cap": 1_000_000_000,
            "min_revenue_growth_1y": 10,
            "min_revenue_growth_3y": 10,
            "max_peg": 1.5,
            "min_gross_margin": 35,
            "min_roic": 12,
            "positive_fcf_required": True,
        },
    },
    "sector_dislocation": {
        "label": "Sector Dislocation",
        "description": "Cheap vs sector peers. Thomas's dislocation lens.",
        "filters": {
            "min_market_cap": 500_000_000,
            "min_ey_vs_sector": 2,
            "min_gm_vs_sector": -5,
            "min_roic": 8,
            "max_debt_equity": 3.0,
            "positive_fcf_required": True,
        },
    },
}
