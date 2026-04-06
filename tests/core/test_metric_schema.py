"""Tests for backend.core.metric_schema — centralized metric registry."""

import pytest

from backend.core.metric_schema import (
    METRIC_SCHEMA,
    MetricDef,
    resolve_alias,
    get_metric,
    metrics_for_source,
    metrics_for_sector,
    all_metric_names,
)


# ---------------------------------------------------------------------------
# resolve_alias
# ---------------------------------------------------------------------------

class TestResolveAlias:
    def test_resolve_alias_camel_case(self):
        assert resolve_alias("returnOnInvestedCapital") == "roic"

    def test_resolve_alias_display_name(self):
        assert resolve_alias("Return on Invested Capital") == "roic"

    def test_resolve_alias_unknown(self):
        assert resolve_alias("nonexistent_metric") is None

    def test_resolve_alias_canonical_name(self):
        """Canonical name itself should resolve."""
        assert resolve_alias("roic") == "roic"

    def test_resolve_alias_case_insensitive(self):
        assert resolve_alias("ReturnOnInvestedCapital") == "roic"
        assert resolve_alias("ROIC") == "roic"

    def test_resolve_alias_fmp_ttm_suffix(self):
        assert resolve_alias("roicTTM") == "roic"

    def test_resolve_alias_empty_string(self):
        assert resolve_alias("") is None

    def test_resolve_alias_snake_case(self):
        assert resolve_alias("return_on_invested_capital") == "roic"

    def test_resolve_alias_gross_margin_variants(self):
        assert resolve_alias("grossProfitMargin") == "gross_margin"
        assert resolve_alias("gross_profit_margin") == "gross_margin"
        assert resolve_alias("Gross Margin") == "gross_margin"

    def test_resolve_alias_debt_equity_variants(self):
        assert resolve_alias("debtEquity") == "debt_equity"
        assert resolve_alias("debtToEquity") == "debt_equity"
        assert resolve_alias("debt_to_equity") == "debt_equity"
        assert resolve_alias("debtToEquityRatio") == "debt_equity"

    def test_resolve_alias_pe_variants(self):
        assert resolve_alias("pe_ratio") == "pe"
        assert resolve_alias("priceEarningsRatio") == "pe"

    def test_resolve_alias_momentum(self):
        assert resolve_alias("rs_3m_percentile") == "rs_3m"
        assert resolve_alias("relativeStrength3m") == "rs_3m"
        assert resolve_alias("momentum_3m") == "rs_3m"

    def test_resolve_alias_piotroski_variants(self):
        assert resolve_alias("piotroski_score") == "piotroski"
        assert resolve_alias("f_score") == "piotroski"
        assert resolve_alias("fScore") == "piotroski"


# ---------------------------------------------------------------------------
# get_metric
# ---------------------------------------------------------------------------

class TestGetMetric:
    def test_get_metric_by_canonical(self):
        m = get_metric("roic")
        assert m is not None
        assert isinstance(m, MetricDef)
        assert m.canonical_name == "roic"
        assert m.display_name == "Return on Invested Capital"
        assert m.source == "sec_xbrl"
        assert "returnOnInvestedCapital" in m.aliases

    def test_get_metric_by_alias(self):
        m1 = get_metric("roicTTM")
        m2 = get_metric("roic")
        assert m1 is not None
        assert m2 is not None
        assert m1.canonical_name == m2.canonical_name

    def test_get_metric_unknown(self):
        assert get_metric("fake_metric") is None

    def test_get_metric_typical_range(self):
        m = get_metric("gross_margin")
        assert m is not None
        assert m.typical_range == (0.0, 1.0)

    def test_get_metric_data_type(self):
        m = get_metric("piotroski")
        assert m is not None
        assert m.data_type == "int"

    def test_get_metric_sector_specific(self):
        m = get_metric("nim")
        assert m is not None
        assert m.sector_specific is True
        assert "banking" in m.sectors


# ---------------------------------------------------------------------------
# metrics_for_source
# ---------------------------------------------------------------------------

class TestMetricsForSource:
    def test_metrics_for_source_sec(self):
        sec_metrics = metrics_for_source("sec_xbrl")
        assert "roic" in sec_metrics
        assert "gross_margin" in sec_metrics
        assert "debt_equity" in sec_metrics
        assert "roe" in sec_metrics
        assert "fcf_conversion" in sec_metrics

    def test_metrics_for_source_computed(self):
        computed = metrics_for_source("computed")
        assert "expected_return" in computed
        assert "dislocation_score" in computed
        assert "fair_value" in computed
        assert "base_return" in computed

    def test_metrics_for_source_yfinance(self):
        yf_metrics = metrics_for_source("yfinance")
        assert "rs_3m" in yf_metrics
        assert "rs_6m" in yf_metrics
        assert "price" in yf_metrics

    def test_metrics_for_source_nonexistent(self):
        assert metrics_for_source("bloomberg") == []


# ---------------------------------------------------------------------------
# metrics_for_sector
# ---------------------------------------------------------------------------

class TestMetricsForSector:
    def test_metrics_for_sector_banking(self):
        banking = metrics_for_sector("banking")
        assert "nim" in banking
        assert "efficiency_ratio" in banking
        assert "npl_ratio" in banking
        assert "rule_of_40" not in banking
        assert "combined_ratio" not in banking

    def test_metrics_for_sector_tech(self):
        tech = metrics_for_sector("tech")
        assert "rule_of_40" in tech
        assert "deferred_rev_growth" in tech
        assert "nim" not in tech
        assert "combined_ratio" not in tech

    def test_metrics_for_sector_includes_general(self):
        banking = metrics_for_sector("banking")
        # General metrics should always be included
        assert "roic" in banking
        assert "gross_margin" in banking
        assert "pe" in banking
        assert "revenue_growth" in banking

    def test_metrics_for_sector_insurance(self):
        ins = metrics_for_sector("insurance")
        assert "combined_ratio" in ins
        assert "loss_ratio" in ins
        assert "nim" not in ins

    def test_metrics_for_sector_reits(self):
        reits = metrics_for_sector("reits")
        assert "ffo_yield" in reits
        assert "pffo" in reits
        assert "nav_discount" in reits
        assert "ffo_per_share" in reits


# ---------------------------------------------------------------------------
# all_metric_names
# ---------------------------------------------------------------------------

class TestAllMetricNames:
    def test_all_metric_names_comprehensive(self):
        names = all_metric_names()
        assert len(names) >= 50, f"Expected 50+ metrics, got {len(names)}"

    def test_all_metric_names_includes_key_metrics(self):
        names = all_metric_names()
        expected = [
            "roic", "gross_margin", "pe", "revenue_growth", "debt_equity",
            "fcf_yield", "piotroski", "expected_return", "fair_value",
            "base_return", "bear_return", "weight", "nim", "rule_of_40",
        ]
        for m in expected:
            assert m in names, f"Expected '{m}' in all_metric_names()"

    def test_all_metric_names_returns_list(self):
        names = all_metric_names()
        assert isinstance(names, list)


# ---------------------------------------------------------------------------
# Data integrity
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    def test_no_duplicate_aliases(self):
        """No alias should map to more than one canonical name."""
        seen: dict[str, str] = {}
        duplicates = []
        for canonical, mdef in METRIC_SCHEMA.items():
            all_names = [canonical, mdef.display_name] + mdef.aliases
            for name in all_names:
                key = name.lower()
                if key in seen and seen[key] != canonical:
                    duplicates.append(
                        f"Alias '{name}' maps to both '{seen[key]}' and '{canonical}'"
                    )
                seen[key] = canonical
        assert duplicates == [], f"Duplicate aliases found: {duplicates}"

    def test_typical_ranges_valid(self):
        """Every metric with a numeric typical_range should have min < max."""
        for name, mdef in METRIC_SCHEMA.items():
            low, high = mdef.typical_range
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                assert low < high, (
                    f"Metric '{name}' has invalid typical_range: {mdef.typical_range}"
                )

    def test_all_metrics_have_display_name(self):
        for name, mdef in METRIC_SCHEMA.items():
            assert mdef.display_name, f"Metric '{name}' has no display_name"

    def test_all_metrics_have_source(self):
        valid_sources = {"sec_xbrl", "fmp_key_metrics", "computed", "yfinance"}
        for name, mdef in METRIC_SCHEMA.items():
            assert mdef.source in valid_sources, (
                f"Metric '{name}' has invalid source: '{mdef.source}'"
            )

    def test_all_metrics_have_valid_data_type(self):
        valid_types = {"float", "int", "string", "bool", "percent"}
        for name, mdef in METRIC_SCHEMA.items():
            assert mdef.data_type in valid_types, (
                f"Metric '{name}' has invalid data_type: '{mdef.data_type}'"
            )

    def test_sector_specific_metrics_have_sectors(self):
        for name, mdef in METRIC_SCHEMA.items():
            if mdef.sector_specific:
                assert len(mdef.sectors) > 0, (
                    f"Sector-specific metric '{name}' has empty sectors list"
                )

    def test_codegen_metrics_all_migrated(self):
        """All key metrics from codegen.py build_metric_schema() should be present."""
        codegen_keys = [
            "pe", "pb", "ps", "ev_ebitda", "ev_fcf", "pfcf", "fcf_yield",
            "earnings_yield", "peg", "ptangible_book",
            "implied_growth", "growth_gap",
            "gross_margin", "operating_margin", "net_margin", "ebitda_margin", "fcf_margin",
            "roe", "roa", "roic", "roce",
            "revenue_growth", "revenue_growth_3y", "revenue_growth_5y",
            "eps_growth", "fcf_growth", "growth_consistency",
            "fcf_conversion", "income_quality", "capex_to_revenue",
            "debt_equity", "net_debt_ebitda", "interest_coverage", "current_ratio",
            "piotroski", "altman_z", "quality_score",
            "dividend_yield", "payout_ratio",
            "gm_vs_sector", "roic_vs_sector", "growth_vs_sector", "ey_vs_sector",
            "rs_3m", "rs_6m",
            "expected_return", "dislocation_score", "compounder_score",
        ]
        names = all_metric_names()
        missing = [k for k in codegen_keys if k not in names]
        assert missing == [], f"Codegen metrics not migrated: {missing}"

    def test_thesis_metrics_present(self):
        names = all_metric_names()
        for m in ["fair_value", "discount_pct", "expected_return", "conviction"]:
            assert m in names, f"Thesis metric '{m}' missing"

    def test_ic_metrics_present(self):
        names = all_metric_names()
        for m in ["base_return", "bear_return", "discount_floor"]:
            assert m in names, f"IC metric '{m}' missing"

    def test_portfolio_metrics_present(self):
        names = all_metric_names()
        for m in ["weight", "pnl_pct", "cost_basis", "market_value"]:
            assert m in names, f"Portfolio metric '{m}' missing"

    def test_sector_specific_banking(self):
        names = all_metric_names()
        for m in ["nim", "efficiency_ratio", "npl_ratio", "reserve_coverage"]:
            assert m in names, f"Banking metric '{m}' missing"

    def test_sector_specific_insurance(self):
        names = all_metric_names()
        for m in ["combined_ratio", "loss_ratio"]:
            assert m in names, f"Insurance metric '{m}' missing"

    def test_sector_specific_reits(self):
        names = all_metric_names()
        for m in ["ffo_per_share", "ffo_yield", "pffo", "nav_discount"]:
            assert m in names, f"REIT metric '{m}' missing"

    def test_sector_specific_tech(self):
        names = all_metric_names()
        for m in ["rule_of_40", "deferred_rev_growth"]:
            assert m in names, f"Tech metric '{m}' missing"
