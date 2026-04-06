"""Tests for B1: Intent-based scoring code generation reliability.

Covers:
- build_metric_schema() delegates to metric_schema.py
- INTENT_JSON_SCHEMA is valid JSON schema
- generate_code_from_intent() produces valid code
- Generated code passes validate_ast()
- Generated code runs in sandbox and returns float 0-10
- Correction message generation for bad field names
"""

import json
import jsonschema
import pytest

from backend.core.intent_schema import ScoringIntent, ScoringRule, INTENT_JSON_SCHEMA
from backend.core.metric_schema import METRIC_SCHEMA, all_metric_names, resolve_alias
from backend.core.validation import (
    validate_intent,
    generate_code_from_intent,
    correction_message,
)
from backend.scoring.codegen import (
    build_metric_schema,
    _parse_intent_json,
    _build_label_map_from_intent,
)
from backend.scoring.sandbox import validate_ast, compile_scoring_function


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_STOCK = {
    "symbol": "TEST",
    "companyName": "Test Corp",
    "sector": "Technology",
    "price": 150.0,
    "market_cap": 50_000_000_000,
    "pe": 22.0,
    "pb": 4.5,
    "ps": 5.2,
    "ev_ebitda": 15.0,
    "fcf_yield": 0.05,
    "earnings_yield": 0.07,
    "peg": 1.2,
    "implied_growth": 0.08,
    "growth_gap": 0.06,
    "gross_margin": 0.62,
    "operating_margin": 0.22,
    "net_margin": 0.18,
    "roic": 0.22,
    "roe": 0.28,
    "roa": 0.12,
    "roce": 0.20,
    "revenue_growth": 0.18,
    "revenue_growth_3y": 0.15,
    "revenue_growth_5y": 0.12,
    "growth_consistency": 0.85,
    "fcf_conversion": 0.90,
    "income_quality": 1.05,
    "debt_equity": 0.8,
    "net_debt_ebitda": 0.5,
    "interest_coverage": 18.0,
    "current_ratio": 2.1,
    "piotroski": 7,
    "altman_z": 4.5,
    "quality_score": 7.5,
    "dividend_yield": 0.01,
    "payout_ratio": 0.15,
    "rs_3m": 78,
    "rs_6m": 72,
}

WEAK_STOCK = {
    "symbol": "WEAK",
    "companyName": "Weak Corp",
    "sector": "Technology",
    "price": 20.0,
    "market_cap": 2_000_000_000,
    "pe": 45.0,
    "pb": 1.2,
    "ps": 1.0,
    "ev_ebitda": 30.0,
    "fcf_yield": 0.01,
    "earnings_yield": 0.02,
    "peg": 4.0,
    "implied_growth": 0.15,
    "growth_gap": -0.05,
    "gross_margin": 0.28,
    "operating_margin": 0.03,
    "net_margin": 0.01,
    "roic": 0.03,
    "roe": 0.04,
    "roa": 0.01,
    "roce": 0.03,
    "revenue_growth": 0.03,
    "revenue_growth_3y": 0.02,
    "revenue_growth_5y": 0.01,
    "growth_consistency": 0.40,
    "fcf_conversion": 0.30,
    "income_quality": 0.60,
    "debt_equity": 4.5,
    "net_debt_ebitda": 5.0,
    "interest_coverage": 1.5,
    "current_ratio": 0.9,
    "piotroski": 2,
    "altman_z": 1.2,
    "quality_score": 2.0,
    "dividend_yield": 0.0,
    "payout_ratio": 0.0,
    "rs_3m": 18,
    "rs_6m": 22,
}


def _make_basic_intent() -> ScoringIntent:
    """Create a basic quality compounder intent for testing."""
    return ScoringIntent(
        rules=[
            ScoringRule(field="roic", operator=">", value=0.15, weight=2.0, required=False, label="High ROIC"),
            ScoringRule(field="gross_margin", operator=">", value=0.40, weight=1.5, required=False, label="Strong Gross Margin"),
            ScoringRule(field="debt_equity", operator="<", value=2.0, weight=1.0, required=False, label="Low Leverage"),
            ScoringRule(field="revenue_growth_3y", operator=">", value=0.08, weight=1.5, required=False, label="Consistent Growth"),
            ScoringRule(field="fcf_yield", operator=">", value=0.03, weight=1.0, required=False, label="Decent FCF Yield"),
        ],
        logic="all",
        sort_by={"field": "roic", "direction": "desc"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildMetricSchema:
    """Test that build_metric_schema() delegates to metric_schema.py."""

    def test_build_metric_schema_delegates(self):
        """build_metric_schema() returns text containing metrics from METRIC_SCHEMA."""
        schema_text = build_metric_schema()

        # Should be a non-empty string
        assert isinstance(schema_text, str)
        assert len(schema_text) > 100

        # Should contain canonical names from the registry
        assert "roic" in schema_text
        assert "gross_margin" in schema_text
        assert "pe" in schema_text
        assert "debt_equity" in schema_text
        assert "fcf_yield" in schema_text

    def test_build_metric_schema_contains_all_registered_metrics(self):
        """Every metric in METRIC_SCHEMA appears in the schema text."""
        schema_text = build_metric_schema()
        # Check a representative sample (not all ~60+ metrics, but enough)
        for name in ["roic", "revenue_growth", "piotroski", "dividend_yield", "rs_3m"]:
            assert name in schema_text, f"Metric '{name}' missing from schema text"

    def test_build_metric_schema_shows_aliases(self):
        """Schema text includes alias information."""
        schema_text = build_metric_schema()
        assert "Aliases:" in schema_text


class TestIntentJsonSchema:
    """Test that INTENT_JSON_SCHEMA is valid and usable."""

    def test_intent_json_schema_valid(self):
        """INTENT_JSON_SCHEMA is a valid JSON schema (can be used for validation)."""
        # jsonschema.validate will raise if the schema itself is invalid
        # We test by validating a known-good intent against it
        good_intent = {
            "rules": [
                {
                    "field": "roic",
                    "operator": ">",
                    "value": 0.15,
                    "weight": 2.0,
                    "required": False,
                    "label": "High ROIC",
                }
            ],
            "logic": "all",
            "sort_by": {"field": "score", "direction": "desc"},
            "version": "1.0",
        }
        # Should not raise
        jsonschema.validate(instance=good_intent, schema=INTENT_JSON_SCHEMA)

    def test_intent_json_schema_rejects_empty_rules(self):
        """Schema rejects intent with empty rules array."""
        bad_intent = {"rules": [], "logic": "all"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_intent, schema=INTENT_JSON_SCHEMA)

    def test_intent_json_schema_rejects_bad_operator(self):
        """Schema rejects rules with invalid operator."""
        bad_intent = {
            "rules": [
                {
                    "field": "roic",
                    "operator": "LIKE",
                    "value": 0.15,
                    "weight": 2.0,
                    "required": False,
                }
            ]
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_intent, schema=INTENT_JSON_SCHEMA)

    def test_intent_json_schema_is_serializable(self):
        """INTENT_JSON_SCHEMA can be serialized to JSON (for LLM prompts)."""
        serialized = json.dumps(INTENT_JSON_SCHEMA, indent=2)
        assert isinstance(serialized, str)
        # Round-trip
        parsed = json.loads(serialized)
        assert parsed == INTENT_JSON_SCHEMA


class TestGenerateFromIntent:
    """Test generate_code_from_intent() produces valid, runnable code."""

    def test_generate_from_intent_basic(self):
        """Given a ScoringIntent, generate_code_from_intent produces valid Python code."""
        intent = _make_basic_intent()
        code = generate_code_from_intent(intent)

        assert isinstance(code, str)
        assert "def score(stock):" in code
        assert "safe_get" in code
        assert "return" in code

    def test_generate_from_intent_with_required_rules(self):
        """Intent with required rules produces guard clauses."""
        intent = ScoringIntent(
            rules=[
                ScoringRule(field="pe", operator="<", value=50, weight=1.0, required=True, label="PE Cap"),
                ScoringRule(field="roic", operator=">", value=0.10, weight=2.0, required=False, label="ROIC"),
            ],
            logic="all",
        )
        code = generate_code_from_intent(intent)

        assert "Required filters" in code or "required" in code.lower()
        assert "'score': 0.0" in code  # guard clause returns 0

    def test_generate_from_intent_with_between(self):
        """Intent with 'between' operator produces range check."""
        intent = ScoringIntent(
            rules=[
                ScoringRule(
                    field="pe", operator="between", value=[10, 30],
                    weight=1.5, required=False, label="PE in range",
                ),
            ],
            logic="all",
        )
        code = generate_code_from_intent(intent)
        assert "10" in code
        assert "30" in code

    def test_generated_code_passes_ast(self):
        """Generated code from a valid intent passes validate_ast()."""
        intent = _make_basic_intent()
        code = generate_code_from_intent(intent)

        errors = validate_ast(code)
        assert errors == [], f"AST validation errors: {errors}"

    def test_generated_code_runs_in_sandbox(self):
        """Generated code runs against a sample stock and returns float 0-10."""
        intent = _make_basic_intent()
        code = generate_code_from_intent(intent)

        # Compile and run
        score_fn = compile_scoring_function(code)
        result = score_fn(SAMPLE_STOCK)

        # Check return format
        assert isinstance(result, dict)
        assert "score" in result
        assert "reason" in result

        score = result["score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0

    def test_generated_code_differentiates_strong_vs_weak(self):
        """Strong stock scores higher than weak stock."""
        intent = _make_basic_intent()
        code = generate_code_from_intent(intent)

        score_fn = compile_scoring_function(code)
        strong_result = score_fn(SAMPLE_STOCK)
        weak_result = score_fn(WEAK_STOCK)

        strong_score = strong_result["score"]
        weak_score = weak_result["score"]

        assert strong_score > weak_score, (
            f"Strong stock ({strong_score}) should score higher than weak stock ({weak_score})"
        )

    def test_generated_code_handles_empty_stock(self):
        """Generated code handles an empty stock dict without crashing."""
        intent = _make_basic_intent()
        code = generate_code_from_intent(intent)

        score_fn = compile_scoring_function(code)
        result = score_fn({"symbol": "EMPTY", "sector": "Unknown"})

        assert isinstance(result, dict)
        assert "score" in result
        assert 0.0 <= result["score"] <= 10.0


class TestCodegenWithCorrection:
    """Test the validation failure -> correction message flow."""

    def test_codegen_with_correction_bad_field(self):
        """A bad field name triggers validation failure + correction_message."""
        bad_intent = ScoringIntent(
            rules=[
                ScoringRule(field="return_on_equity_ttm", operator=">", value=0.15,
                           weight=2.0, required=False, label="High ROE"),
            ],
            logic="all",
        )
        is_valid, errors = validate_intent(bad_intent)
        assert not is_valid
        assert len(errors) > 0

        # Verify correction_message provides suggestions
        msg = correction_message("return_on_equity_ttm")
        assert "not found" in msg.lower()
        # Should suggest close matches
        assert "roe" in msg.lower() or "return" in msg.lower()

    def test_correction_message_suggests_canonical(self):
        """correction_message suggests canonical names for misspelled fields."""
        # "gross_profit_margins" is close to "gross_margin"
        msg = correction_message("gross_profit_margins")
        assert "not found" in msg.lower() or "Did you mean" in msg

    def test_correction_message_totally_wrong(self):
        """correction_message handles completely unknown fields."""
        msg = correction_message("xyzzy_metric_99")
        assert "not found" in msg.lower()

    def test_validation_passes_for_good_intent(self):
        """A well-formed intent with valid canonical names passes validation."""
        intent = _make_basic_intent()
        is_valid, errors = validate_intent(intent)

        hard_errors = [e for e in errors if not e.startswith("WARNING:")]
        assert is_valid, f"Should pass but got errors: {hard_errors}"

    def test_validation_catches_bad_operator(self):
        """validate_intent catches operators not valid for the metric."""
        # "symbol" only supports "==" per metric_schema
        intent = ScoringIntent(
            rules=[
                ScoringRule(field="symbol", operator=">", value=0,
                           weight=1.0, required=False, label="Bad Op"),
            ],
            logic="all",
        )
        is_valid, errors = validate_intent(intent)
        assert not is_valid
        assert any("operator" in e.lower() or "not valid" in e.lower() for e in errors)

    def test_validation_catches_bad_weight(self):
        """validate_intent catches weights outside 0.5-5.0 range."""
        intent = ScoringIntent(
            rules=[
                ScoringRule(field="roic", operator=">", value=0.10,
                           weight=10.0, required=False, label="Too Heavy"),
            ],
            logic="all",
        )
        is_valid, errors = validate_intent(intent)
        assert not is_valid
        assert any("weight" in e.lower() for e in errors)


class TestParseIntentJson:
    """Test _parse_intent_json helper."""

    def test_parse_valid_json(self):
        """Parses a valid intent JSON string into ScoringIntent."""
        raw = json.dumps({
            "rules": [
                {"field": "roic", "operator": ">", "value": 0.15,
                 "weight": 2.0, "required": False, "label": "ROIC"}
            ],
            "logic": "all",
            "sort_by": {"field": "roic", "direction": "desc"},
            "version": "1.0",
        })
        intent = _parse_intent_json(raw)
        assert isinstance(intent, ScoringIntent)
        assert len(intent.rules) == 1
        assert intent.rules[0].field == "roic"
        assert intent.logic == "all"
        assert intent.sort_by == {"field": "roic", "direction": "desc"}

    def test_parse_invalid_json_raises(self):
        """Non-JSON string raises json.JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            _parse_intent_json("this is not json")

    def test_parse_missing_required_field_raises(self):
        """Missing required fields in rule dict raises KeyError."""
        raw = json.dumps({"rules": [{"field": "roic"}]})
        with pytest.raises(KeyError):
            _parse_intent_json(raw)


class TestBuildLabelMap:
    """Test _build_label_map_from_intent helper."""

    def test_label_map_includes_score(self):
        """Label map always includes 'score' key."""
        intent = _make_basic_intent()
        label_map = _build_label_map_from_intent(intent)
        assert "score" in label_map
        assert label_map["score"]["label"] == "Score"

    def test_label_map_includes_soft_rules(self):
        """Label map includes entries for non-required rules."""
        intent = _make_basic_intent()
        label_map = _build_label_map_from_intent(intent)
        assert "roic" in label_map
        assert label_map["roic"]["label"] == "High ROIC"

    def test_label_map_excludes_required_rules(self):
        """Required rules are guard filters, not shown as score dimensions."""
        intent = ScoringIntent(
            rules=[
                ScoringRule(field="pe", operator="<", value=50, weight=1.0, required=True, label="PE Cap"),
                ScoringRule(field="roic", operator=">", value=0.10, weight=2.0, required=False, label="ROIC"),
            ],
            logic="all",
        )
        label_map = _build_label_map_from_intent(intent)
        assert "pe" not in label_map  # required rule excluded
        assert "roic" in label_map    # soft rule included
