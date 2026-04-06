"""Centralized metric schema registry.

Single source of truth for every valid financial metric across all FundOps
agents. Maps canonical names, display names, aliases (camelCase from FMP,
snake_case from SEC, display names from UI), data types, typical ranges,
valid operators, and data sources.

Used by:
- Scoring codegen (to tell LLM what metrics exist)
- Screener (key normalization)
- Thesis / IC Review (return sources, quality metrics)
- Dashboard / UI (display names, formatting)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class MetricDef:
    canonical_name: str          # "roic"
    display_name: str            # "Return on Invested Capital"
    aliases: List[str]           # ["return_on_invested_capital", "returnOnInvestedCapital", "roicTTM"]
    data_type: str               # float | int | string | bool | percent
    typical_range: Tuple         # (min, max) as stored value
    valid_operators: List[str]   # [">", "<", ">=", "<=", "==", "between"]
    source: str                  # sec_xbrl | fmp_key_metrics | computed | yfinance
    sector_specific: bool = False
    sectors: List[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Standard operator sets
# ---------------------------------------------------------------------------
_COMPARE_OPS = [">", "<", ">=", "<=", "==", "between"]
_EQ_ONLY = ["=="]

# ---------------------------------------------------------------------------
# METRIC_SCHEMA — the canonical registry
# ---------------------------------------------------------------------------

METRIC_SCHEMA: dict[str, MetricDef] = {}


def _m(canonical_name: str, display_name: str, aliases: List[str],
       data_type: str, typical_range: Tuple, source: str,
       valid_operators: List[str] | None = None,
       sector_specific: bool = False, sectors: List[str] | None = None,
       notes: str = "") -> None:
    """Helper to register a metric."""
    METRIC_SCHEMA[canonical_name] = MetricDef(
        canonical_name=canonical_name,
        display_name=display_name,
        aliases=aliases,
        data_type=data_type,
        typical_range=typical_range,
        valid_operators=valid_operators or _COMPARE_OPS,
        source=source,
        sector_specific=sector_specific,
        sectors=sectors or [],
        notes=notes,
    )


# ═══════════════════════════════════════════════════════════════════════════
# IDENTIFICATION
# ═══════════════════════════════════════════════════════════════════════════

_m("symbol", "Ticker Symbol", ["ticker"], "string", ("", ""), "computed", _EQ_ONLY)
_m("company_name", "Company Name", ["companyName", "name"], "string", ("", ""), "computed", _EQ_ONLY)
_m("sector", "Sector", ["sector_classification"], "string", ("", ""), "computed", _EQ_ONLY)
_m("subsector", "Subsector", ["industry", "sub_sector"], "string", ("", ""), "computed", _EQ_ONLY)
_m("price", "Price", ["stock_price", "currentPrice"], "float", (0.0, 100000.0), "yfinance")
_m("market_cap", "Market Capitalization", ["marketCap", "mktCap", "market_capitalization"], "float", (0.0, 5e12), "yfinance")

# ═══════════════════════════════════════════════════════════════════════════
# VALUATION
# ═══════════════════════════════════════════════════════════════════════════

_m("pe", "Price / Earnings", ["pe_ratio", "priceEarningsRatio", "peRatio", "price_earnings"], "float", (0.0, 200.0), "computed",
    notes="TTM. None if unprofitable.")
_m("pb", "Price / Book", ["pb_ratio", "priceToBookRatio", "price_book"], "float", (0.0, 50.0), "computed")
_m("ps", "Price / Sales", ["ps_ratio", "priceToSalesRatio", "price_sales"], "float", (0.0, 50.0), "computed")
_m("ev_ebitda", "EV / EBITDA", ["evEbitda", "ev_to_ebitda", "enterpriseValueOverEBITDA"], "float", (0.0, 100.0), "computed")
_m("ev_fcf", "EV / Free Cash Flow", ["evFcf", "ev_to_fcf"], "float", (0.0, 100.0), "computed")
_m("pfcf", "Price / Free Cash Flow", ["priceFcf", "price_to_fcf", "priceToFreeCashFlow"], "float", (0.0, 100.0), "computed")
_m("fcf_yield", "FCF Yield", ["fcfYield", "freeCashFlowYield", "fcfYieldDecimal", "freeCashFlowYieldTTM"], "float", (0.0, 0.30), "computed",
    notes="FCF / Market Cap as decimal. 0.05 = 5%.")
_m("earnings_yield", "Earnings Yield", ["earningsYield", "earningsYieldDecimal", "earnings_yield_decimal"], "float", (0.0, 0.30), "computed",
    notes="EBIT / EV as decimal. 0.08 = 8%.")
_m("peg", "PEG Ratio", ["pegRatio", "peg_ratio", "priceEarningsToGrowthRatio"], "float", (0.0, 10.0), "computed",
    notes="P/E / growth rate. <1 cheap, >2 expensive.")
_m("ptangible_book", "Price / Tangible Book", ["priceTangibleBook", "price_to_tangible_book", "ptangibleBook"], "float", (0.0, 50.0), "computed")

# ═══════════════════════════════════════════════════════════════════════════
# BACKWARD DCF
# ═══════════════════════════════════════════════════════════════════════════

_m("implied_growth", "Implied Growth Rate", ["impliedGrowth", "implied_growth_rate"], "float", (-0.10, 0.50), "computed",
    notes="Growth rate market prices in. As decimal (0.05 = 5%).")
_m("growth_gap", "Growth Gap", ["growthGap", "growth_gap_pct"], "float", (-0.30, 0.30), "computed",
    notes="Actual growth minus implied growth. Positive = underpriced.")

# ═══════════════════════════════════════════════════════════════════════════
# PROFITABILITY (as decimals, e.g., 0.83 = 83%)
# ═══════════════════════════════════════════════════════════════════════════

_m("gross_margin", "Gross Margin", ["grossProfitMargin", "gross_profit_margin", "grossMargin", "grossProfitMarginTTM"], "percent", (0.0, 1.0), "sec_xbrl",
    notes="As decimal. 0.60 = 60%.")
_m("operating_margin", "Operating Margin", ["operatingMargin", "operatingProfitMargin", "operating_profit_margin", "operatingMarginTTM"], "percent", (-0.50, 0.70), "sec_xbrl")
_m("net_margin", "Net Margin", ["netProfitMargin", "net_profit_margin", "netMargin", "netProfitMarginTTM"], "percent", (-1.0, 0.50), "sec_xbrl")
_m("ebitda_margin", "EBITDA Margin", ["ebitdaMargin", "ebitda_margin_pct"], "percent", (-0.20, 0.70), "sec_xbrl")
_m("fcf_margin", "FCF Margin", ["fcfMargin", "freeCashFlowMargin", "free_cash_flow_margin"], "percent", (-0.30, 0.50), "sec_xbrl",
    notes="FCF / Revenue.")

# ═══════════════════════════════════════════════════════════════════════════
# RETURN METRICS (as decimals)
# ═══════════════════════════════════════════════════════════════════════════

_m("roe", "Return on Equity", ["returnOnEquity", "return_on_equity", "roeTTM", "returnOnEquityTTM"], "percent", (-0.50, 1.0), "sec_xbrl",
    notes=">0.15 strong.")
_m("roa", "Return on Assets", ["returnOnAssets", "return_on_assets", "roaTTM", "returnOnAssetsTTM"], "percent", (-0.20, 0.30), "sec_xbrl",
    notes=">0.05 solid.")
_m("roic", "Return on Invested Capital", ["returnOnInvestedCapital", "return_on_invested_capital", "roicTTM", "returnOnInvestedCapitalTTM"], "percent", (-0.20, 0.50), "sec_xbrl",
    notes=">0.15 excellent.")
_m("roce", "Return on Capital Employed", ["returnOnCapitalEmployed", "return_on_capital_employed", "roceTTM"], "percent", (-0.20, 0.50), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# GROWTH (as decimals, e.g., 0.12 = 12%)
# ═══════════════════════════════════════════════════════════════════════════

_m("revenue_growth", "Revenue Growth (1Y)", ["revenueGrowth", "revenueGrowth1y", "revenue_growth_1y", "revenueGrowthTTM"], "percent", (-0.50, 1.0), "sec_xbrl",
    notes="1-year revenue growth.")
_m("revenue_growth_3y", "Revenue Growth (3Y CAGR)", ["revenueGrowth3Y", "revenueGrowth3y", "revenueGrowth3yr", "revenue_growth_3yr"], "percent", (-0.20, 0.50), "sec_xbrl")
_m("revenue_growth_5y", "Revenue Growth (5Y CAGR)", ["revenueGrowth5Y", "revenueGrowth5y"], "percent", (-0.20, 0.40), "sec_xbrl")
_m("eps_growth", "EPS Growth", ["epsGrowth", "epsDilutedGrowth", "epsdilutedGrowth", "eps_diluted_growth"], "percent", (-1.0, 2.0), "sec_xbrl")
_m("fcf_growth", "FCF Growth", ["fcfGrowth", "freeCashFlowGrowth", "free_cash_flow_growth"], "percent", (-1.0, 2.0), "sec_xbrl")
_m("growth_consistency", "Growth Consistency", ["growthConsistency", "revenueGrowthConsistency", "revenue_growth_consistency"], "percent", (0.0, 1.0), "sec_xbrl",
    notes="% of years with positive revenue growth (0-1).")
_m("gross_profit_growth", "Gross Profit Growth", ["grossProfitGrowth", "gross_profit_growth_yoy"], "percent", (-1.0, 2.0), "sec_xbrl")
_m("operating_income_growth", "Operating Income Growth", ["operatingIncomeGrowth", "op_income_growth"], "percent", (-1.0, 5.0), "sec_xbrl")
_m("net_income_growth", "Net Income Growth", ["netIncomeGrowth", "net_income_growth_yoy"], "percent", (-1.0, 5.0), "sec_xbrl")
_m("operating_cash_flow_growth", "Operating Cash Flow Growth", ["operatingCashFlowGrowth", "ocf_growth"], "percent", (-1.0, 5.0), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# CASH FLOW (as decimals)
# ═══════════════════════════════════════════════════════════════════════════

_m("fcf_conversion", "FCF Conversion", ["fcfConversion", "freeCashFlowConversion", "free_cash_flow_conversion"], "float", (0.0, 3.0), "sec_xbrl",
    notes="FCF / Net Income. >0.8 good, >1.0 excellent.")
_m("income_quality", "Income Quality", ["incomeQuality", "income_quality_ratio"], "float", (0.0, 3.0), "sec_xbrl",
    notes="Operating CF / Net Income. >1.0 means cash > accruals.")
_m("capex_to_revenue", "Capex / Revenue", ["capexToRevenue", "capitalExpenditureToRevenue", "capex_to_rev"], "float", (0.0, 0.30), "sec_xbrl",
    notes="Lower = more asset-light.")
_m("ocf_margin", "Operating Cash Flow Margin", ["operatingCashFlowMargin", "ocfMargin", "ocf_to_revenue"], "percent", (-0.20, 0.50), "sec_xbrl")
_m("sbc_to_revenue", "SBC / Revenue", ["stockBasedCompensationToRevenue", "sbc_to_rev", "sbcToRevenue"], "percent", (0.0, 0.30), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# BALANCE SHEET / LEVERAGE
# ═══════════════════════════════════════════════════════════════════════════

_m("debt_equity", "Debt / Equity", ["debtEquity", "debtToEquity", "debtToEquityRatio", "debt_to_equity", "debtToEquityTTM"], "float", (0.0, 10.0), "sec_xbrl",
    notes="<1.0 conservative, >3.0 leveraged.")
_m("net_debt_ebitda", "Net Debt / EBITDA", ["netDebtEbitda", "netDebtToEBITDA", "net_debt_to_ebitda"], "float", (-5.0, 10.0), "sec_xbrl",
    notes="<2.0 healthy.")
_m("interest_coverage", "Interest Coverage", ["interestCoverage", "interestCoverageRatio", "interest_coverage_ratio"], "float", (0.0, 100.0), "sec_xbrl",
    notes=">5x safe.")
_m("current_ratio", "Current Ratio", ["currentRatio", "current_ratio_val"], "float", (0.0, 10.0), "sec_xbrl",
    notes=">1.5 healthy.")
_m("net_debt", "Net Debt", ["netDebt", "net_debt_val"], "float", (-1e11, 1e12), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# QUALITY SCORES
# ═══════════════════════════════════════════════════════════════════════════

_m("piotroski", "Piotroski F-Score", ["piotroski_score", "f_score", "piotroskiScore", "fScore"], "int", (0, 9), "sec_xbrl",
    notes=">7 strong, <3 weak.")
_m("altman_z", "Altman Z-Score", ["altmanZ", "altman_z_score", "altmanZScore"], "float", (0.0, 10.0), "computed",
    notes=">2.99 safe, <1.81 distress.")
_m("quality_score", "Quality Score", ["qualityScore", "quality_composite"], "float", (0.0, 10.0), "computed",
    notes="Composite quality 0-10.")

# ═══════════════════════════════════════════════════════════════════════════
# DIVIDENDS
# ═══════════════════════════════════════════════════════════════════════════

_m("dividend_yield", "Dividend Yield", ["dividendYield", "dividendYieldTTM", "div_yield"], "percent", (0.0, 0.15), "computed",
    notes="Annual dividend / price, as decimal.")
_m("payout_ratio", "Payout Ratio", ["payoutRatio", "dividendPayoutRatio", "dividend_payout_ratio"], "percent", (0.0, 1.5), "sec_xbrl",
    notes="Dividends / Net Income.")

# ═══════════════════════════════════════════════════════════════════════════
# EFFICIENCY / WORKING CAPITAL
# ═══════════════════════════════════════════════════════════════════════════

_m("dso", "Days Sales Outstanding", ["daysOfSalesOutstanding", "days_sales_outstanding"], "float", (0.0, 200.0), "sec_xbrl")
_m("dpo", "Days Payables Outstanding", ["daysOfPayablesOutstanding", "days_payables_outstanding"], "float", (0.0, 200.0), "sec_xbrl")
_m("dio", "Days Inventory Outstanding", ["daysOfInventoryOutstanding", "days_inventory_outstanding"], "float", (0.0, 300.0), "sec_xbrl")
_m("ccc", "Cash Conversion Cycle", ["cashConversionCycle", "cash_conversion_cycle"], "float", (-100.0, 300.0), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# SECTOR COMPARISON (vs sector median)
# ═══════════════════════════════════════════════════════════════════════════

_m("gm_vs_sector", "Gross Margin vs Sector", ["gm_vs_sector_median", "grossMarginVsSector"], "float", (0.0, 5.0), "computed",
    notes="Ratio to sector median. >1.0 = above median.")
_m("roic_vs_sector", "ROIC vs Sector", ["roic_vs_sector_median", "roicVsSector"], "float", (0.0, 5.0), "computed")
_m("growth_vs_sector", "Growth vs Sector", ["growth_vs_sector_median", "growthVsSector"], "float", (0.0, 5.0), "computed")
_m("ey_vs_sector", "Earnings Yield vs Sector", ["ey_vs_sector_median", "earningsYieldVsSector"], "float", (0.0, 5.0), "computed")

# ═══════════════════════════════════════════════════════════════════════════
# MOMENTUM / RELATIVE STRENGTH (from yfinance)
# ═══════════════════════════════════════════════════════════════════════════

_m("rs_3m", "3-Month Relative Strength", ["rs_3m_percentile", "relativeStrength3m", "rs3m", "momentum_3m"], "float", (0.0, 100.0), "yfinance",
    notes="Percentile vs universe. 0 = worst, 100 = best.")
_m("rs_6m", "6-Month Relative Strength", ["rs_6m_percentile", "relativeStrength6m", "rs6m", "momentum_6m"], "float", (0.0, 100.0), "yfinance",
    notes="Percentile vs universe. 0 = worst, 100 = best.")

# ═══════════════════════════════════════════════════════════════════════════
# COMPUTED BY SCREENER
# ═══════════════════════════════════════════════════════════════════════════

_m("expected_return", "Expected Total Return", ["expectedReturn", "expected_total_return"], "float", (-50.0, 200.0), "computed",
    notes="Estimated total return as decimal or percent.")
_m("return_sources", "Return Sources", ["returnSources", "return_decomposition"], "string", ("", ""), "computed", _EQ_ONLY,
    notes='Dict: {"discount": float, "growth": float, "margin": float, "dividends": float}.')
_m("dislocation_score", "Dislocation Score", ["dislocationScore", "dislocation"], "float", (0.0, 10.0), "computed",
    notes="0-10 score from dislocation lens.")
_m("compounder_score", "Compounder Score", ["compounderScore", "compounder"], "float", (0.0, 10.0), "computed",
    notes="0-10 score from compounder lens.")

# ═══════════════════════════════════════════════════════════════════════════
# PER-SHARE METRICS (from SEC ratios)
# ═══════════════════════════════════════════════════════════════════════════

_m("revenue_per_share", "Revenue Per Share", ["revenuePerShare", "rev_per_share"], "float", (0.0, 10000.0), "sec_xbrl")
_m("fcf_per_share", "FCF Per Share", ["freeCashFlowPerShare", "fcfPerShare"], "float", (-100.0, 1000.0), "sec_xbrl")
_m("book_value_per_share", "Book Value Per Share", ["bookValuePerShare", "bvPerShare", "bv_per_share"], "float", (-100.0, 5000.0), "sec_xbrl")
_m("tangible_book_per_share", "Tangible Book Per Share", ["tangibleBookValuePerShare", "tbvPerShare", "tbv_per_share"], "float", (-500.0, 5000.0), "sec_xbrl")
_m("owner_earnings_per_share", "Owner Earnings Per Share", ["ownersEarningsPerShare", "oe_per_share"], "float", (-50.0, 500.0), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# OWNER EARNINGS (Buffett-style)
# ═══════════════════════════════════════════════════════════════════════════

_m("owner_earnings", "Owner Earnings", ["ownerEarnings", "ownersEarnings", "owners_earnings"], "float", (-1e10, 1e11), "sec_xbrl")
_m("maintenance_capex", "Maintenance Capex", ["maintenanceCapex", "maintenance_capex_val"], "float", (0.0, 1e11), "sec_xbrl")
_m("growth_capex", "Growth Capex", ["growthCapex", "growth_capex_val"], "float", (0.0, 1e11), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# ADDITIONAL EFFICIENCY RATIOS (from SEC ratios)
# ═══════════════════════════════════════════════════════════════════════════

_m("goodwill_to_assets", "Goodwill / Assets", ["goodwillToAssets", "goodwill_pct"], "percent", (0.0, 0.60), "sec_xbrl")
_m("rd_to_revenue", "R&D / Revenue", ["researchAndDevelopementToRevenue", "rnd_to_revenue", "rd_intensity", "rnd_intensity"], "percent", (0.0, 0.50), "sec_xbrl")
_m("sga_to_revenue", "SGA / Revenue", ["salesGeneralAndAdministrativeToRevenue", "sgaToRevenue"], "percent", (0.0, 0.50), "sec_xbrl")
_m("effective_tax_rate", "Effective Tax Rate", ["effectiveTaxRate", "eff_tax_rate"], "percent", (0.0, 0.50), "sec_xbrl")
_m("receivables_growth", "Receivables Growth", ["receivablesGrowth", "recv_growth"], "percent", (-0.50, 2.0), "sec_xbrl")
_m("capex_to_ocf", "Capex / Operating Cash Flow", ["capexToOperatingCashFlow", "capex_to_ocf_ratio"], "float", (0.0, 2.0), "sec_xbrl")

# ═══════════════════════════════════════════════════════════════════════════
# THESIS AGENT METRICS
# ═══════════════════════════════════════════════════════════════════════════

_m("fair_value", "Fair Value", ["fairValue", "fair_value_base", "intrinsic_value"], "float", (0.0, 100000.0), "computed",
    notes="Independent fair value estimate from thesis.")
_m("discount_pct", "Discount to Fair Value (%)", ["discountPct", "discount_percent", "discount_to_fv"], "float", (-100.0, 90.0), "computed",
    notes="Positive = cheap.")
_m("conviction", "Conviction Level", ["conviction_level"], "string", ("", ""), "computed", _EQ_ONLY,
    notes="LOW / MEDIUM / HIGH.")

# ═══════════════════════════════════════════════════════════════════════════
# IC REVIEW METRICS
# ═══════════════════════════════════════════════════════════════════════════

_m("base_return", "Base Case Return", ["baseReturn", "base_case_return", "hurdle_base"], "float", (-50.0, 200.0), "computed",
    notes="Expected return under base scenario.")
_m("bear_return", "Bear Case Return", ["bearReturn", "bear_case_return", "hurdle_bear"], "float", (-50.0, 200.0), "computed",
    notes="Stress-tested return (70% haircut on growth/margin).")
_m("discount_floor", "Discount Floor", ["discountFloor", "min_discount", "growth_aware_discount_floor"], "float", (0.0, 50.0), "computed",
    notes="Growth-aware minimum discount requirement.")
_m("ic_verdict", "IC Verdict", ["verdict", "ic_pass"], "string", ("", ""), "computed", _EQ_ONLY,
    notes="PASS or NO_PASS.")
_m("ic_conviction", "IC Conviction", ["ic_conviction_score"], "int", (1, 5), "computed",
    notes="1-5 conviction score from IC review.")

# ═══════════════════════════════════════════════════════════════════════════
# PORTFOLIO METRICS (Pulse / Vanguard)
# ═══════════════════════════════════════════════════════════════════════════

_m("weight", "Portfolio Weight", ["portfolio_weight", "position_weight", "alloc_pct"], "percent", (0.0, 1.0), "computed",
    notes="As decimal. 0.05 = 5%.")
_m("pnl_pct", "P&L (%)", ["pnlPct", "profit_loss_pct", "return_pct"], "percent", (-1.0, 10.0), "computed",
    notes="Unrealized gain/loss as decimal.")
_m("cost_basis", "Cost Basis", ["costBasis", "avg_cost", "entry_price"], "float", (0.0, 100000.0), "computed")
_m("market_value", "Market Value", ["marketValue", "position_value", "current_value"], "float", (0.0, 1e12), "computed")
_m("position_type", "Position Type", ["positionType", "pos_type"], "string", ("", ""), "computed", _EQ_ONLY,
    notes="tactical / core / balanced.")

# ═══════════════════════════════════════════════════════════════════════════
# SECTOR-SPECIFIC: BANKING
# ═══════════════════════════════════════════════════════════════════════════

_m("nim", "Net Interest Margin", ["netInterestMargin", "net_interest_margin"], "percent", (0.0, 0.10), "sec_xbrl",
    sector_specific=True, sectors=["banking", "Financial Services", "Banks"],
    notes="Net interest income / avg earning assets.")
_m("efficiency_ratio", "Efficiency Ratio", ["efficiencyRatio", "bank_efficiency"], "percent", (0.30, 1.0), "sec_xbrl",
    sector_specific=True, sectors=["banking", "Financial Services", "Banks"],
    notes="Non-interest expense / revenue. Lower is better.")
_m("npl_ratio", "NPL Ratio", ["nplRatio", "non_performing_loan_ratio"], "percent", (0.0, 0.10), "sec_xbrl",
    sector_specific=True, sectors=["banking", "Financial Services", "Banks"])
_m("reserve_coverage", "Reserve Coverage", ["reserveCoverage", "loan_loss_reserve_coverage"], "float", (0.0, 5.0), "sec_xbrl",
    sector_specific=True, sectors=["banking", "Financial Services", "Banks"])

# ═══════════════════════════════════════════════════════════════════════════
# SECTOR-SPECIFIC: INSURANCE
# ═══════════════════════════════════════════════════════════════════════════

_m("combined_ratio", "Combined Ratio", ["combinedRatio", "combined_ratio_pct"], "percent", (0.60, 1.20), "sec_xbrl",
    sector_specific=True, sectors=["insurance", "Insurance"],
    notes="<1.0 = underwriting profit.")
_m("loss_ratio", "Loss Ratio", ["lossRatio", "loss_ratio_pct"], "percent", (0.40, 1.0), "sec_xbrl",
    sector_specific=True, sectors=["insurance", "Insurance"])

# ═══════════════════════════════════════════════════════════════════════════
# SECTOR-SPECIFIC: REITS
# ═══════════════════════════════════════════════════════════════════════════

_m("ffo_yield", "FFO Yield", ["ffoYield", "ffo_yield_pct"], "percent", (0.0, 0.20), "sec_xbrl",
    sector_specific=True, sectors=["reits", "REITs", "Real Estate"])
_m("pffo", "Price / FFO", ["priceFfo", "price_to_ffo"], "float", (0.0, 50.0), "sec_xbrl",
    sector_specific=True, sectors=["reits", "REITs", "Real Estate"])
_m("nav_discount", "NAV Discount", ["navDiscount", "nav_discount_pct", "discount_to_nav"], "float", (-0.50, 0.50), "sec_xbrl",
    sector_specific=True, sectors=["reits", "REITs", "Real Estate"],
    notes="Positive = trading below NAV.")
_m("ffo_per_share", "FFO Per Share", ["ffoPerShare", "ffo_ps"], "float", (0.0, 100.0), "sec_xbrl",
    sector_specific=True, sectors=["reits", "REITs", "Real Estate"])

# ═══════════════════════════════════════════════════════════════════════════
# SECTOR-SPECIFIC: TECHNOLOGY
# ═══════════════════════════════════════════════════════════════════════════

_m("rule_of_40", "Rule of 40", ["ruleOf40", "rule_of_forty"], "float", (0.0, 100.0), "computed",
    sector_specific=True, sectors=["tech", "Technology", "Information Technology"],
    notes="Revenue growth % + profit margin %. >40 is good.")
_m("sbc_to_revenue_tech", "SBC / Revenue (Tech)", ["sbc_to_revenue_pct", "sbcToRevenueTech"], "percent", (0.0, 0.40), "sec_xbrl",
    sector_specific=True, sectors=["tech", "Technology", "Information Technology"])
_m("deferred_rev_growth", "Deferred Revenue Growth", ["deferredRevenueGrowth", "deferred_revenue_growth"], "percent", (-0.50, 2.0), "sec_xbrl",
    sector_specific=True, sectors=["tech", "Technology", "Information Technology"],
    notes="Leading indicator of future revenue.")

# ═══════════════════════════════════════════════════════════════════════════
# RAW STATEMENT LINE ITEMS (for reference / power users)
# ═══════════════════════════════════════════════════════════════════════════

_m("revenue", "Revenue", ["totalRevenue", "total_revenue", "sales"], "float", (0.0, 1e12), "sec_xbrl")
_m("gross_profit", "Gross Profit", ["grossProfit", "gross_profit_val"], "float", (-1e10, 1e12), "sec_xbrl")
_m("operating_income", "Operating Income", ["operatingIncome", "op_income", "ebit"], "float", (-1e11, 1e11), "sec_xbrl")
_m("net_income", "Net Income", ["netIncome", "net_income_val"], "float", (-1e11, 1e11), "sec_xbrl")
_m("ebitda", "EBITDA", ["ebitda_val", "EBITDA"], "float", (-1e10, 1e11), "sec_xbrl")
_m("eps", "Earnings Per Share", ["epsDiluted", "eps_diluted", "earningsPerShare"], "float", (-100.0, 500.0), "sec_xbrl")
_m("free_cash_flow", "Free Cash Flow", ["freeCashFlow", "fcf", "free_cf"], "float", (-1e11, 1e11), "sec_xbrl")
_m("operating_cash_flow", "Operating Cash Flow", ["operatingCashFlow", "ocf", "op_cash_flow"], "float", (-1e11, 1e11), "sec_xbrl")
_m("total_debt", "Total Debt", ["totalDebt", "total_debt_val"], "float", (0.0, 1e12), "sec_xbrl")
_m("total_equity", "Total Stockholders Equity", ["totalStockholdersEquity", "stockholders_equity", "total_equity_val"], "float", (-1e11, 1e12), "sec_xbrl")
_m("total_assets", "Total Assets", ["totalAssets", "total_assets_val"], "float", (0.0, 5e12), "sec_xbrl")
_m("cash_and_equivalents", "Cash & Equivalents", ["cashAndCashEquivalents", "cash", "cash_and_cash_equivalents"], "float", (0.0, 5e11), "sec_xbrl")
_m("depreciation_amortization", "Depreciation & Amortization", ["depreciationAndAmortization", "da", "d_and_a"], "float", (0.0, 1e11), "sec_xbrl")
_m("sbc", "Stock-Based Compensation", ["stockBasedCompensation", "stock_based_comp"], "float", (0.0, 1e10), "sec_xbrl")
_m("capex", "Capital Expenditure", ["capitalExpenditure", "capital_expenditure"], "float", (-1e11, 0.0), "sec_xbrl",
    notes="Usually negative in cash flow statement.")
_m("dividends_paid", "Dividends Paid", ["dividendsPaid", "div_paid"], "float", (-1e10, 0.0), "sec_xbrl")
_m("shares_outstanding", "Shares Outstanding (Diluted)", ["weightedAverageShsOutDil", "weightedAverageSharesDiluted", "shares_diluted"], "float", (0.0, 1e11), "sec_xbrl")
_m("rd_expenses", "R&D Expenses", ["researchAndDevelopmentExpenses", "rnd_expenses", "rd_expense"], "float", (0.0, 1e11), "sec_xbrl")
_m("sga_expenses", "SGA Expenses", ["sellingGeneralAndAdministrativeExpenses", "sga_expense"], "float", (0.0, 1e11), "sec_xbrl")


# ---------------------------------------------------------------------------
# Alias index (built once at import time)
# ---------------------------------------------------------------------------

_ALIAS_INDEX: dict[str, str] = {}

def _build_alias_index() -> None:
    """Build a reverse lookup: alias -> canonical_name (case-insensitive)."""
    _ALIAS_INDEX.clear()
    for canonical, mdef in METRIC_SCHEMA.items():
        key = canonical.lower()
        _ALIAS_INDEX[key] = canonical
        _ALIAS_INDEX[mdef.display_name.lower()] = canonical
        for alias in mdef.aliases:
            _ALIAS_INDEX[alias.lower()] = canonical

_build_alias_index()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_alias(name: str) -> Optional[str]:
    """Given any alias (camelCase, snake_case, display name), return the
    canonical metric name, or None if not found."""
    if not name:
        return None
    return _ALIAS_INDEX.get(name.lower())


def get_metric(name: str) -> Optional[MetricDef]:
    """Get MetricDef by canonical name or any alias."""
    canonical = resolve_alias(name)
    if canonical is None:
        return None
    return METRIC_SCHEMA.get(canonical)


def metrics_for_source(source: str) -> List[str]:
    """Return all canonical metric names from a given data source."""
    return [k for k, v in METRIC_SCHEMA.items() if v.source == source]


def metrics_for_sector(sector: str) -> List[str]:
    """Return all metrics available for a sector.

    Includes all general (non-sector-specific) metrics plus sector-specific
    metrics whose sectors list includes the given sector.
    """
    result = []
    sector_lower = sector.lower()
    for k, v in METRIC_SCHEMA.items():
        if not v.sector_specific:
            result.append(k)
        else:
            if any(s.lower() == sector_lower for s in v.sectors):
                result.append(k)
    return result


def all_metric_names() -> List[str]:
    """Return all canonical metric names."""
    return list(METRIC_SCHEMA.keys())
