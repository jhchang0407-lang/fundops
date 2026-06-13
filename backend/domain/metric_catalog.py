"""Financial Metric Catalog (ADR-0016, ADR-0045).

Wraps the registry in backend.core.metric_schema with governance fields:
catalog version, decision authority for hard gates, missing-data behavior,
and the Supported Thesis Health Field Catalog (metric x cadence x lookback
combinations FundOps can actually compute from retained evidence, ADR-0014).

Every Calculated Financial Observation records CATALOG_VERSION so historical
observations stay replayable after formulas improve (ADR-0045).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.metric_schema import METRIC_SCHEMA, MetricDef, resolve_alias

CATALOG_VERSION = "2026.06-1"
MAPPING_VERSION = "2026.06-1"

# Period-scaled metrics: flows (and flow-over-stock returns) whose magnitude
# depends on the reporting-period length. In the latest-financials projection
# a quarterly observation must never displace the annual/TTM basis — valuation
# anchors multiply EPS by an ANNUAL justified PE, and constitution thresholds
# are written against full-period bases. Scale-invariant ratios (margins,
# multiples, yields) and point-in-time levels (price, market_cap,
# balance-sheet stocks) are excluded: newest-of-any-period stays correct.
PERIOD_SCALED_METRICS = {
    "revenue", "cost_of_revenue", "gross_profit", "operating_income",
    "pretax_income", "income_tax", "net_income", "ebitda", "eps",
    "operating_cash_flow", "capex", "free_cash_flow", "owner_earnings",
    "maintenance_capex", "growth_capex", "sbc",
    # Flow over a balance-sheet stock: a single quarter understates ~4x.
    "roe", "roa", "roic",
}

# Metrics that may decide hard Screening Requirements / IC Hurdles.
# Criteria on other metrics degrade to research-review or ranking influence.
HARD_GATE_METRICS = {
    "price", "market_cap", "pe", "pb", "ps", "ev_ebitda", "fcf_yield",
    "earnings_yield", "gross_margin", "operating_margin", "net_margin",
    "fcf_margin", "roe", "roa", "roic", "revenue_growth", "revenue_growth_3y",
    "revenue_growth_5y", "eps_growth", "fcf_growth", "debt_equity",
    "net_debt_ebitda", "interest_coverage", "current_ratio", "dividend_yield",
    "payout_ratio", "sbc_to_revenue", "capex_to_revenue", "fcf_conversion",
    "sector", "rule_of_40",
    # Market technicals: computed locally from stored daily bars on every
    # price sync, so they are as gateable as any reported fundamental.
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m",
    "pct_below_52w_high", "volatility_90d", "avg_dollar_volume_3m",
    "avg_volume_3m",
    # Thesis-level return fields: valid IC-hurdle targets (e.g. minimum
    # expected return before Memo spend), evaluated against thesis output.
    "expected_return", "discount_pct", "base_return", "bear_return",
}

# ---------------------------------------------------------------------------
# Statement-section classification (ADR-0042/0043).
#
# The Company Page financial statements are standardized Income / Balance /
# Cash Flow surfaces, not an undifferentiated metric matrix. Each section lists
# its canonical line items in display order; conventional ratios derived from a
# statement (margins on income, leverage on balance, FCF ratios on cash flow)
# ride with their statement. Market technicals are point-in-time price data, not
# statement facts (ADR-0043) — they are excluded from every statement section.
# Anything uncatalogued here is a derived ratio ("ratio") shown in the snapshot
# and peers, never as a statement line.
# ---------------------------------------------------------------------------

INCOME_STATEMENT = (
    "revenue", "cost_of_revenue", "gross_profit", "rd_expenses", "sga_expenses",
    "operating_income", "ebitda", "pretax_income", "income_tax", "net_income",
    "eps", "gross_margin", "operating_margin", "ebitda_margin", "net_margin",
)
BALANCE_SHEET = (
    "total_assets", "cash_and_equivalents", "total_debt", "net_debt",
    "total_equity", "shares_outstanding", "book_value_per_share",
    "tangible_book_per_share", "current_ratio", "debt_equity",
)
CASH_FLOW_STATEMENT = (
    "operating_cash_flow", "depreciation_amortization", "sbc", "capex",
    "free_cash_flow", "maintenance_capex", "growth_capex", "owner_earnings",
    "dividends_paid", "fcf_margin", "fcf_conversion", "capex_to_revenue",
)
STATEMENT_SECTIONS = ("income", "balance", "cashflow")

# Point-in-time price/market metrics. Computed locally from daily bars (or the
# quote path), they ride the screener via latest_financials but must never
# render as a financial-statement period column.
MARKET_METRICS = frozenset({
    "price", "market_cap",
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m",
    "pct_below_52w_high", "volatility_90d", "avg_dollar_volume_3m", "avg_volume_3m",
})

_SECTION_INDEX: dict[str, tuple[str, int]] = {}
for _sec, _members in (("income", INCOME_STATEMENT), ("balance", BALANCE_SHEET),
                       ("cashflow", CASH_FLOW_STATEMENT)):
    for _i, _m in enumerate(_members):
        _SECTION_INDEX[_m] = (_sec, _i)


def _canon(metric_id: str) -> str:
    return resolve_alias(metric_id) or metric_id


def is_market_metric(metric_id: str) -> bool:
    """True for point-in-time price/market metrics (excluded from statements)."""
    return _canon(metric_id) in MARKET_METRICS


def statement_section(metric_id: str) -> str:
    """Statement bucket for the Company Page: income | balance | cashflow for
    statement facts and their conventional ratios, 'market' for price
    technicals, 'ratio' for every other derived metric."""
    canonical = _canon(metric_id)
    if canonical in MARKET_METRICS:
        return "market"
    found = _SECTION_INDEX.get(canonical)
    return found[0] if found else "ratio"


def statement_order(metric_id: str) -> int:
    """Canonical row order within a statement section (lower renders first).
    Uncatalogued metrics sort last, then alphabetically by the caller."""
    found = _SECTION_INDEX.get(_canon(metric_id))
    return found[1] if found else 999


# Thesis-health-supported flow/level metrics with allowed cadences and
# lookback bases. Quarterly support requires retained quarterly history.
_TH_CADENCES = ("quarterly", "annual", "ttm")
_TH_LOOKBACKS = ("latest", "yoy", "ttm", "annual", "multi_period_avg")

THESIS_HEALTH_FIELDS: dict[str, dict] = {
    m: {"cadences": _TH_CADENCES, "lookbacks": _TH_LOOKBACKS}
    for m in (
        "revenue", "revenue_growth", "gross_margin", "operating_margin",
        "net_margin", "fcf_margin", "free_cash_flow", "operating_cash_flow",
        "net_income", "eps", "roic", "roe", "debt_equity", "net_debt_ebitda",
        "interest_coverage", "sbc_to_revenue", "capex_to_revenue",
        "fcf_conversion", "gross_profit", "operating_income", "ebitda",
        "shares_outstanding", "rule_of_40", "nim", "efficiency_ratio",
        "combined_ratio", "ffo_per_share",
    )
}


@dataclass
class CatalogMetric:
    id: str
    label: str
    unit: str
    source: str
    operators: list[str]
    typical_range: tuple
    hard_gate_capable: bool
    thesis_health: dict | None
    sector_specific: bool
    sectors: list[str] = field(default_factory=list)
    missing_data_behavior: str = "treat_as_unevaluable"


def _unit_for(d: MetricDef) -> str:
    if d.data_type == "percent":
        return "ratio"
    if d.data_type in ("float", "int"):
        return "number"
    return d.data_type


def get_metric(metric_id: str) -> CatalogMetric | None:
    d = METRIC_SCHEMA.get(metric_id)
    if d is None:
        # Resolve aliases
        for key, md in METRIC_SCHEMA.items():
            if metric_id in md.aliases:
                d, metric_id = md, key
                break
        else:
            return None
    return CatalogMetric(
        id=d.canonical_name,
        label=d.display_name,
        unit=_unit_for(d),
        source=d.source,
        operators=d.valid_operators,
        typical_range=d.typical_range,
        hard_gate_capable=d.canonical_name in HARD_GATE_METRICS,
        thesis_health=THESIS_HEALTH_FIELDS.get(d.canonical_name),
        sector_specific=d.sector_specific,
        sectors=d.sectors,
    )


def is_supported(metric_id: str) -> bool:
    return get_metric(metric_id) is not None


def supports_hard_gate(metric_id: str) -> bool:
    m = get_metric(metric_id)
    return bool(m and m.hard_gate_capable)


def thesis_health_combo_allowed(metric_id: str, cadence: str, lookback: str) -> bool:
    """Supported Thesis Health Field Catalog check (ADR-0014)."""
    m = get_metric(metric_id)
    if m is None or m.thesis_health is None:
        return False
    return cadence in m.thesis_health["cadences"] and lookback in m.thesis_health["lookbacks"]


def thesis_health_catalog() -> list[dict]:
    """Compact catalog handed to Memo generation for monitoring-plan drafting."""
    out = []
    for mid, combo in THESIS_HEALTH_FIELDS.items():
        m = get_metric(mid)
        if m is None:
            continue
        out.append({
            "metric": mid,
            "label": m.label,
            "unit": m.unit,
            "cadences": list(combo["cadences"]),
            "lookbacks": list(combo["lookbacks"]),
        })
    return out


def all_metric_ids() -> list[str]:
    return sorted(METRIC_SCHEMA.keys())
