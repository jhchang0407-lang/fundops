"""Tests for backend.core.web_grounding — Web Research Grounding Layer.

All tests are deterministic (no LLM calls, no network).
"""

import sys
import os
from datetime import date, timedelta

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.web_grounding import (
    build_fact_anchor,
    verify_entity,
    check_recency,
    extract_numerical_claims,
    cross_reference_claims,
    detect_contradictions,
    ground_web_research,
    DateReference,
    NumericalClaim,
    ClaimVerification,
    EntityCheck,
    GroundedResearch,
    _TODAY,
)
import backend.core.web_grounding as wg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_today(d: date):
    """Override today's date for deterministic tests."""
    wg._TODAY = d


def _reset_today():
    wg._TODAY = None


@pytest.fixture(autouse=True)
def reset_today_after_test():
    """Reset _TODAY after every test."""
    yield
    _reset_today()


# Sample financial data dict (mimics what thesis agent's _fetch_data returns)
SAMPLE_DATA = {
    "ticker": "PAYC",
    "company_name": "Paycom Software",
    "sector": "Technology",
    "industry": "Software - Application",
    "price": 198.50,
    "market_cap": 11200000000,
    "revenue": 1830000000,
    "revenue_growth": 0.112,
    "gross_margin": 0.834,
    "operating_margin": 0.245,
    "roic": 0.281,
    "roe": 0.35,
    "debt_equity": 0.15,
    "fcf_yield": 0.042,
    "dividend_yield": 0.008,
    "pe": 22.5,
    "eps": 8.82,
}


# ---------------------------------------------------------------------------
# build_fact_anchor tests
# ---------------------------------------------------------------------------

class TestBuildFactAnchor:

    def test_build_fact_anchor_complete(self):
        """financial_data with all fields -> anchor contains ticker, revenue, margins."""
        anchor = build_fact_anchor(SAMPLE_DATA, "PAYC", "Paycom Software")

        assert "PAYC" in anchor
        assert "Paycom Software" in anchor
        assert "Revenue" in anchor
        assert "Gross margin" in anchor
        assert "ROIC" in anchor
        assert "D/E" in anchor
        assert "Price" in anchor
        assert "CONTEXT" in anchor
        # Should contain actual values
        assert "83.4%" in anchor  # gross_margin 0.834 -> 83.4%
        assert "28.1%" in anchor  # roic 0.281 -> 28.1%
        assert "$198.50" in anchor

    def test_build_fact_anchor_missing_fields(self):
        """financial_data with missing keys -> no 'None' in output."""
        sparse_data = {
            "price": 50.0,
            "revenue_growth": 0.08,
        }
        anchor = build_fact_anchor(sparse_data, "XYZ", "XYZ Corp")

        assert "None" not in anchor
        assert "XYZ" in anchor
        assert "XYZ Corp" in anchor
        # Should have revenue growth but not ROIC (missing)
        assert "Revenue growth" in anchor
        assert "8.0%" in anchor
        # Fields with no data should be omitted entirely
        assert "ROIC" not in anchor
        assert "D/E" not in anchor


# ---------------------------------------------------------------------------
# verify_entity tests
# ---------------------------------------------------------------------------

class TestVerifyEntity:

    def test_verify_entity_correct(self):
        """Text with 'Paycom (PAYC)' -> confidence >= 0.9."""
        text = (
            "Paycom Software (PAYC) reported strong Q3 2024 earnings, "
            "beating analyst expectations. PAYC shares rose 5% on the news."
        )
        result = verify_entity(text, "PAYC", "Paycom Software")

        assert result.ticker_found is True
        assert result.company_name_found is True
        assert result.confidence >= 0.9
        assert len(result.wrong_entity_signals) == 0

    def test_verify_entity_wrong(self):
        """Text about 'PayPal (PYPL)' when ticker is PAYC -> confidence < 0.5."""
        text = (
            "PayPal (PYPL) continues to dominate digital payments. "
            "PayPal (PYPL) reported revenue growth of 8%. "
            "PayPal's (PYPL) market share expanded in Q3 2024. "
            "PYPL stock rallied after earnings beat."
        )
        result = verify_entity(text, "PAYC", "Paycom Software")

        assert result.confidence < 0.5
        assert len(result.wrong_entity_signals) > 0

    def test_verify_entity_missing(self):
        """Text with no ticker or company name -> confidence ~0.3."""
        text = (
            "The software industry saw strong growth in 2024, "
            "with cloud adoption accelerating across enterprise customers."
        )
        result = verify_entity(text, "PAYC", "Paycom Software")

        assert result.ticker_found is False
        assert result.company_name_found is False
        assert result.confidence == pytest.approx(0.3, abs=0.05)


# ---------------------------------------------------------------------------
# check_recency tests
# ---------------------------------------------------------------------------

class TestCheckRecency:

    def test_check_recency_fresh(self):
        """Text with dates from last 3 months -> recency >= 0.8."""
        _set_today(date(2026, 3, 31))
        text = (
            "In Q1 2026, the company reported record earnings. "
            "February 2026 saw strong demand across all segments. "
            "Management's March 2026 guidance was upbeat."
        )
        refs, score = check_recency(text)

        assert len(refs) > 0
        assert score >= 0.8

    def test_check_recency_stale(self):
        """Text with dates from 18+ months ago -> recency < 0.3."""
        _set_today(date(2026, 3, 31))
        text = (
            "During FY2023, the company struggled with integration. "
            "Q2 2024 earnings were disappointing. "
            "In 2023, revenue declined sharply."
        )
        refs, score = check_recency(text)

        assert len(refs) > 0
        assert score < 0.3

    def test_check_recency_no_dates(self):
        """Text with no dates -> recency = 0.5, warning generated."""
        text = (
            "The company has a strong competitive position in the market. "
            "Its products are widely used by enterprise customers."
        )
        refs, score = check_recency(text)

        assert len(refs) == 0
        assert score == 0.5


# ---------------------------------------------------------------------------
# extract_numerical_claims tests
# ---------------------------------------------------------------------------

class TestExtractNumericalClaims:

    def test_extract_numerical_claims_percentages(self):
        """'revenue grew 15%' -> value=15.0, unit='percent'."""
        text = "Revenue grew 15% year-over-year, driven by strong demand."
        claims = extract_numerical_claims(text)

        pct_claims = [c for c in claims if c.unit == "percent"]
        assert len(pct_claims) >= 1
        match = next((c for c in pct_claims if c.value == 15.0), None)
        assert match is not None
        assert match.unit == "percent"

    def test_extract_numerical_claims_dollars(self):
        """'$1.8 billion revenue' -> value=1.8, unit='billions'."""
        text = "The company generated $1.8 billion in revenue last year."
        claims = extract_numerical_claims(text)

        dollar_claims = [c for c in claims if c.unit == "billions"]
        assert len(dollar_claims) >= 1
        match = next((c for c in dollar_claims if c.value == pytest.approx(1.8)), None)
        assert match is not None
        assert match.unit == "billions"

    def test_extract_numerical_claims_multiples(self):
        """'trading at 12x earnings' -> value=12.0, unit='multiple'."""
        text = "The stock is currently trading at 12x earnings, below its historical average."
        claims = extract_numerical_claims(text)

        mult_claims = [c for c in claims if c.unit == "multiple"]
        assert len(mult_claims) >= 1
        match = next((c for c in mult_claims if c.value == 12.0), None)
        assert match is not None
        assert match.unit == "multiple"
        assert match.metric_hint == "pe"


# ---------------------------------------------------------------------------
# cross_reference_claims tests
# ---------------------------------------------------------------------------

class TestCrossReferenceClaims:

    def test_cross_reference_confirmed(self):
        """claim 'gross margin of 45%' vs data {gross_margin: 0.452} -> 'confirmed'."""
        claim = NumericalClaim(
            raw_text="45%",
            value=45.0,
            unit="percent",
            metric_hint="gross_margin",
            context="gross margin of 45%",
        )
        data = {"gross_margin": 0.452}
        results = cross_reference_claims([claim], data)

        assert len(results) == 1
        assert results[0].status == "confirmed"
        # 45 vs 45.2 -> deviation ~0.4%, well within 10%
        assert results[0].deviation_pct is not None
        assert results[0].deviation_pct < 10.0

    def test_cross_reference_contradicted(self):
        """claim 'revenue growth 15%' vs data {revenue_growth: 0.082} -> 'contradicted'."""
        claim = NumericalClaim(
            raw_text="15%",
            value=15.0,
            unit="percent",
            metric_hint="revenue_growth",
            context="revenue growth of 15%",
        )
        data = {"revenue_growth": 0.082}
        results = cross_reference_claims([claim], data)

        assert len(results) == 1
        assert results[0].status == "contradicted"
        # 15 vs 8.2 -> ~83% deviation
        assert results[0].deviation_pct is not None
        assert results[0].deviation_pct > 10.0

    def test_cross_reference_unit_normalization(self):
        """'45%' correctly compared against 0.45 (decimal stored as ratio)."""
        claim = NumericalClaim(
            raw_text="45%",
            value=45.0,
            unit="percent",
            metric_hint="gross_margin",
            context="margin is 45%",
        )
        data = {"gross_margin": 0.45}
        results = cross_reference_claims([claim], data)

        assert len(results) == 1
        assert results[0].status == "confirmed"
        # After normalization: 45 vs 45.0 -> 0% deviation
        assert results[0].deviation_pct is not None
        assert results[0].deviation_pct < 1.0

    def test_cross_reference_no_match(self):
        """Claim about unknown metric -> 'unmatched'."""
        claim = NumericalClaim(
            raw_text="72%",
            value=72.0,
            unit="percent",
            metric_hint="customer_retention",
            context="customer retention rate of 72%",
        )
        data = {"revenue_growth": 0.10}
        results = cross_reference_claims([claim], data)

        assert len(results) == 1
        assert results[0].status == "unmatched"


# ---------------------------------------------------------------------------
# detect_contradictions tests
# ---------------------------------------------------------------------------

class TestDetectContradictions:

    def test_detect_contradictions_readable(self):
        """Contradicted claims produce human-readable warning strings."""
        claim = NumericalClaim(
            raw_text="15%",
            value=15.0,
            unit="percent",
            metric_hint="revenue_growth",
            context="revenue growth of 15%",
        )
        verification = ClaimVerification(
            claim=claim,
            matched_metric="revenue_growth",
            actual_value=0.082,
            deviation_pct=83.0,
            status="contradicted",
        )
        warnings = detect_contradictions([verification], SAMPLE_DATA)

        assert len(warnings) == 1
        assert "revenue growth" in warnings[0].lower()
        assert "15%" in warnings[0]
        assert "83%" in warnings[0] or "83" in warnings[0]
        assert "deviation" in warnings[0].lower()


# ---------------------------------------------------------------------------
# ground_web_research (orchestrator) tests
# ---------------------------------------------------------------------------

class TestGroundWebResearch:

    def test_ground_high_confidence(self):
        """Correct entity + recent dates + confirmed claims -> confidence >= 0.7, grounded=True."""
        _set_today(date(2026, 3, 31))
        text = (
            "Paycom Software (PAYC) reported strong Q1 2026 results. "
            "In March 2026, PAYC announced revenue growth of 11%, "
            "with gross margins holding at 83%. "
            "The company's ROIC remains above 28%."
        )
        result = ground_web_research(text, SAMPLE_DATA, "PAYC", "Paycom Software")

        assert result.confidence >= 0.7
        assert result.grounded is True
        assert result.entity_check.confidence >= 0.9
        assert result.recency_score >= 0.8

    def test_ground_low_confidence(self):
        """Wrong entity + stale dates -> confidence < 0.4, grounded=False."""
        _set_today(date(2026, 3, 31))
        text = (
            "PayPal (PYPL) reported Q2 2023 results. "
            "PayPal (PYPL) saw declining transaction volumes in 2023. "
            "PayPal's (PYPL) revenue was $7.3 billion in FY2022."
        )
        result = ground_web_research(text, SAMPLE_DATA, "PAYC", "Paycom Software")

        assert result.confidence < 0.4
        assert result.grounded is False
        assert len(result.warnings) > 0

    def test_ground_empty_text(self):
        """Empty string -> grounded=False, appropriate warnings."""
        result = ground_web_research("", SAMPLE_DATA, "PAYC", "Paycom Software")

        assert result.grounded is False
        assert result.confidence == 0.0
        assert len(result.warnings) > 0
        assert any("empty" in w.lower() for w in result.warnings)

    def test_ground_empty_text_none_handled(self):
        """None-like empty text handled gracefully."""
        result = ground_web_research("   ", SAMPLE_DATA, "PAYC", "Paycom Software")

        assert result.grounded is False
        assert result.confidence == 0.0
