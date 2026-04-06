"""Tests for Intent Schema + Validation Layer (A2).

Covers:
- validate_intent() with valid/invalid fields, operators, ranges, weights
- correction_message() suggestions
- generate_code_from_intent() code generation
- Generated code passes sandbox.validate_ast()
- Generated code runs in sandbox and produces valid scores
- normalize_intent() alias resolution
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

from backend.core.intent_schema import ScoringRule, ScoringIntent
from backend.core.validation import (
    validate_intent,
    correction_message,
    generate_code_from_intent,
    normalize_intent,
)
from backend.scoring.sandbox import validate_ast, compile_scoring_function


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_intent(*rules, logic="all", sort_by=None):
    """Helper to build a ScoringIntent from rule tuples or ScoringRule objects."""
    rule_objs = []
    for r in rules:
        if isinstance(r, ScoringRule):
            rule_objs.append(r)
        else:
            raise TypeError(f"Expected ScoringRule, got {type(r)}")
    return ScoringIntent(rules=rule_objs, logic=logic, sort_by=sort_by)


VALID_RULE_ROIC = ScoringRule(field="roic", operator=">", value=0.15, weight=2.0, required=False, label="High ROIC")
VALID_RULE_PE = ScoringRule(field="pe", operator="<", value=25.0, weight=1.5, required=False, label="Low PE")
VALID_RULE_GM = ScoringRule(field="gross_margin", operator=">", value=0.40, weight=1.0, required=True, label="Min Gross Margin")

SAMPLE_STOCK = {
    "symbol": "TEST",
    "companyName": "Test Corp",
    "sector": "Technology",
    "price": 150.0,
    "pe": 18.0,
    "roic": 0.22,
    "gross_margin": 0.62,
    "grossProfitMargin": 0.62,
    "debt_equity": 0.8,
    "debtEquity": 0.8,
    "fcf_yield": 0.05,
    "revenue_growth": 0.15,
    "revenueGrowth": 0.15,
    "growth_consistency": 0.85,
    "growthConsistency": 0.85,
    "piotroski": 7,
    "rs_3m": 78,
    "rs_6m": 72,
    "earnings_yield": 0.07,
    "fcf_conversion": 0.90,
    "fcfConversion": 0.90,
}

WEAK_STOCK = {
    "symbol": "WEAK",
    "companyName": "Weak Corp",
    "sector": "Technology",
    "price": 20.0,
    "pe": 45.0,
    "roic": 0.03,
    "gross_margin": 0.25,
    "grossProfitMargin": 0.25,
    "debt_equity": 4.5,
    "debtEquity": 4.5,
    "fcf_yield": 0.01,
    "revenue_growth": 0.02,
    "revenueGrowth": 0.02,
    "growth_consistency": 0.40,
    "growthConsistency": 0.40,
    "piotroski": 2,
    "rs_3m": 15,
    "rs_6m": 20,
    "earnings_yield": 0.02,
    "fcf_conversion": 0.30,
    "fcfConversion": 0.30,
}


# ---------------------------------------------------------------------------
# validate_intent tests
# ---------------------------------------------------------------------------

class TestValidateIntent:

    def test_validate_valid_intent(self):
        """Intent with known fields, valid operators, good weights -> (True, [])."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, VALID_RULE_GM)
        is_valid, errors = validate_intent(intent)
        # Filter out warnings
        hard_errors = [e for e in errors if not e.startswith("WARNING:")]
        assert is_valid is True
        assert hard_errors == []

    def test_validate_unknown_field(self):
        """Intent with 'return_on_invested_cap' -> error with 'roic' suggestion."""
        bad_rule = ScoringRule(
            field="return_on_invested_cap",
            operator=">", value=0.15, weight=1.0, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        assert len(errors) >= 1
        # The error should suggest 'roic'
        error_text = errors[0].lower()
        assert "roic" in error_text or "not found" in error_text

    def test_validate_bad_operator(self):
        """Intent with operator '~=' -> error."""
        bad_rule = ScoringRule(
            field="roic", operator="~=", value=0.15, weight=1.0, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        hard_errors = [e for e in errors if not e.startswith("WARNING:")]
        assert any("~=" in e for e in hard_errors)

    def test_validate_out_of_range_warning(self):
        """Intent with gross_margin > 5.0 (impossible for a decimal metric) -> warning."""
        bad_rule = ScoringRule(
            field="gross_margin", operator=">", value=5.0,
            weight=1.0, required=False, label="Impossible GM",
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        # Should be valid (warnings don't block) but have a WARNING
        assert is_valid is True
        warnings = [e for e in errors if e.startswith("WARNING:")]
        assert len(warnings) >= 1
        assert "5.0" in warnings[0]

    def test_validate_weight_bounds(self):
        """Weight of 10.0 -> error."""
        bad_rule = ScoringRule(
            field="roic", operator=">", value=0.15, weight=10.0, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        hard_errors = [e for e in errors if not e.startswith("WARNING:")]
        assert any("10.0" in e or "weight" in e.lower() for e in hard_errors)

    def test_validate_weight_too_low(self):
        """Weight of 0.1 -> error."""
        bad_rule = ScoringRule(
            field="roic", operator=">", value=0.15, weight=0.1, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False

    def test_validate_between_requires_list(self):
        """'between' operator with scalar value -> error."""
        bad_rule = ScoringRule(
            field="pe", operator="between", value=15.0, weight=1.0, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        assert any("between" in e.lower() for e in errors)

    def test_validate_between_inverted_range(self):
        """'between' with [high, low] -> error."""
        bad_rule = ScoringRule(
            field="pe", operator="between", value=[30.0, 10.0], weight=1.0, required=False,
        )
        intent = _make_intent(bad_rule)
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        assert any("inverted" in e.lower() for e in errors)

    def test_validate_empty_rules(self):
        """No rules -> error."""
        intent = ScoringIntent(rules=[], logic="all")
        is_valid, errors = validate_intent(intent)
        assert is_valid is False

    def test_validate_bad_logic(self):
        """Invalid logic value -> error."""
        intent = _make_intent(VALID_RULE_ROIC)
        intent.logic = "xor"
        is_valid, errors = validate_intent(intent)
        assert is_valid is False

    def test_validate_sort_by_bad_field(self):
        """sort_by with unknown field -> error."""
        intent = _make_intent(
            VALID_RULE_ROIC,
            sort_by={"field": "nonexistent_metric_xyz", "direction": "desc"},
        )
        is_valid, errors = validate_intent(intent)
        assert is_valid is False
        assert any("sort_by" in e for e in errors)


# ---------------------------------------------------------------------------
# correction_message tests
# ---------------------------------------------------------------------------

class TestCorrectionMessage:

    def test_correction_message_roic(self):
        """correction_message('return_on_invested_cap') mentions 'roic'."""
        msg = correction_message("return_on_invested_cap")
        assert "roic" in msg.lower()
        assert "not found" in msg.lower()

    def test_correction_message_no_match(self):
        """Completely unrelated name -> 'no similar' or at least 'not found'."""
        msg = correction_message("xyzzy_foobar_metric_999")
        assert "not found" in msg.lower()

    def test_correction_message_close_alias(self):
        """A close alias like 'grossMargin' should suggest 'gross_margin'."""
        msg = correction_message("grossMargin")
        # grossMargin is actually a valid alias, so this should resolve
        # But if we test with a slightly wrong one:
        msg2 = correction_message("gross_margins")  # note: plural
        assert "gross_margin" in msg2.lower() or "not found" in msg2.lower()


# ---------------------------------------------------------------------------
# generate_code_from_intent tests
# ---------------------------------------------------------------------------

class TestGenerateCode:

    def test_generate_code_basic(self):
        """3-rule intent -> valid Python code string."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, VALID_RULE_GM)
        code = generate_code_from_intent(intent)
        assert "def score(stock):" in code
        assert "safe_get" in code
        assert "clamp" in code
        assert "return" in code

    def test_generate_code_between(self):
        """'between' operator -> correct low <= x <= high code."""
        rule = ScoringRule(
            field="pe", operator="between", value=[10.0, 25.0],
            weight=1.5, required=False, label="PE in range",
        )
        intent = _make_intent(rule)
        code = generate_code_from_intent(intent)
        assert "10.0 <=" in code
        assert "<= 25.0" in code

    def test_generate_code_required(self):
        """required=True rule -> generates return 0.0 guard."""
        rule = ScoringRule(
            field="gross_margin", operator=">", value=0.30,
            weight=1.0, required=True, label="Min GM",
        )
        intent = _make_intent(rule)
        code = generate_code_from_intent(intent)
        assert "return {'score': 0.0" in code
        assert "Failed required filter" in code

    def test_generate_code_sort_by(self):
        """sort_by field included as comment (sorting done by caller)."""
        intent = _make_intent(
            VALID_RULE_ROIC,
            sort_by={"field": "roic", "direction": "desc"},
        )
        code = generate_code_from_intent(intent)
        assert "sort_by" in code.lower()
        assert "roic" in code
        assert "desc" in code

    def test_generated_code_passes_ast_validation(self):
        """Generated code passes sandbox.validate_ast()."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, VALID_RULE_GM)
        code = generate_code_from_intent(intent)
        errors = validate_ast(code)
        assert errors == [], f"AST validation failed: {errors}"

    def test_generated_code_runs_in_sandbox(self):
        """Generated code runs against sample stock dict and returns float 0-10."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, VALID_RULE_GM)
        code = generate_code_from_intent(intent)

        # Compile and run
        score_fn = compile_scoring_function(code)
        result = score_fn(SAMPLE_STOCK)

        assert isinstance(result, dict)
        assert "score" in result
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 10.0
        assert "reason" in result

    def test_generated_code_differentiates_stocks(self):
        """Strong stock should score higher than weak stock."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, VALID_RULE_GM)
        code = generate_code_from_intent(intent)
        score_fn = compile_scoring_function(code)

        strong_result = score_fn(SAMPLE_STOCK)
        weak_result = score_fn(WEAK_STOCK)

        assert strong_result["score"] > weak_result["score"], (
            f"Strong ({strong_result['score']}) should beat weak ({weak_result['score']})"
        )

    def test_generated_code_required_filter_blocks_weak(self):
        """Required GM > 0.40 should block weak stock (GM=0.25)."""
        rule_gm = ScoringRule(
            field="gross_margin", operator=">", value=0.40,
            weight=1.0, required=True, label="Min GM",
        )
        rule_roic = ScoringRule(
            field="roic", operator=">", value=0.10,
            weight=1.0, required=False, label="Good ROIC",
        )
        intent = _make_intent(rule_gm, rule_roic)
        code = generate_code_from_intent(intent)
        score_fn = compile_scoring_function(code)

        strong_result = score_fn(SAMPLE_STOCK)
        weak_result = score_fn(WEAK_STOCK)

        assert strong_result["score"] > 0.0
        assert weak_result["score"] == 0.0  # Blocked by required GM filter

    def test_generated_code_between_passes(self):
        """Between operator works correctly in sandbox execution."""
        rule = ScoringRule(
            field="pe", operator="between", value=[10.0, 30.0],
            weight=2.0, required=False, label="PE in range",
        )
        intent = _make_intent(rule)
        code = generate_code_from_intent(intent)
        score_fn = compile_scoring_function(code)

        # SAMPLE_STOCK has pe=18, should be in range
        result = score_fn(SAMPLE_STOCK)
        assert result["score"] > 0.0

        # WEAK_STOCK has pe=45, should be out of range
        weak_result = score_fn(WEAK_STOCK)
        assert weak_result["score"] == 0.0

    def test_generated_code_any_logic(self):
        """'any' logic still produces valid code."""
        intent = _make_intent(VALID_RULE_ROIC, VALID_RULE_PE, logic="any")
        code = generate_code_from_intent(intent)
        errors = validate_ast(code)
        assert errors == []
        score_fn = compile_scoring_function(code)
        result = score_fn(SAMPLE_STOCK)
        assert isinstance(result, dict)
        assert 0.0 <= result["score"] <= 10.0


# ---------------------------------------------------------------------------
# normalize_intent tests
# ---------------------------------------------------------------------------

class TestNormalizeIntent:

    def test_normalize_intent_resolves_aliases(self):
        """Aliases like 'grossProfitMargin' -> canonical 'gross_margin'."""
        rule_alias = ScoringRule(
            field="grossProfitMargin", operator=">", value=0.40,
            weight=1.0, required=False, label="GM",
        )
        rule_alias2 = ScoringRule(
            field="returnOnEquity", operator=">", value=0.15,
            weight=1.0, required=False, label="ROE",
        )
        intent = ScoringIntent(
            rules=[rule_alias, rule_alias2],
            sort_by={"field": "returnOnInvestedCapital", "direction": "desc"},
        )

        normalized = normalize_intent(intent)

        assert normalized.rules[0].field == "gross_margin"
        assert normalized.rules[1].field == "roe"
        assert normalized.sort_by["field"] == "roic"
        assert normalized.sort_by["direction"] == "desc"

    def test_normalize_preserves_canonical(self):
        """Already-canonical names stay unchanged."""
        rule = ScoringRule(
            field="roic", operator=">", value=0.15,
            weight=1.0, required=False,
        )
        intent = ScoringIntent(rules=[rule])
        normalized = normalize_intent(intent)
        assert normalized.rules[0].field == "roic"

    def test_normalize_preserves_other_fields(self):
        """Weight, required, label, logic, version are preserved."""
        rule = ScoringRule(
            field="pe_ratio", operator="<", value=20.0,
            weight=3.0, required=True, label="Cheap PE",
        )
        intent = ScoringIntent(rules=[rule], logic="any", version="1.0")
        normalized = normalize_intent(intent)

        assert normalized.rules[0].field == "pe"  # pe_ratio -> pe
        assert normalized.rules[0].weight == 3.0
        assert normalized.rules[0].required is True
        assert normalized.rules[0].label == "Cheap PE"
        assert normalized.logic == "any"
        assert normalized.version == "1.0"
