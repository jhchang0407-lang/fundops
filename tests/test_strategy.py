"""Tests for strategy profile extraction and validation."""

import pytest
from backend.scoring.strategy import (
    parse_strategy_response,
    validate_strategy_profile,
    build_conversation_messages,
    create_strategy_id,
    STRATEGY_DIMENSIONS,
)


def test_parse_valid_json_response():
    response = '{"message": "What does cheap mean?", "options": ["Low PE", "High FCF yield"], "extracted": {}, "dimensions_complete": ["north_star"], "is_complete": false}'
    parsed = parse_strategy_response(response)
    assert parsed["message"] == "What does cheap mean?"
    assert len(parsed["options"]) == 2
    assert "north_star" in parsed["dimensions_complete"]
    assert not parsed["is_complete"]


def test_parse_plain_text_fallback():
    parsed = parse_strategy_response("I understand. Tell me more about quality.")
    assert "Tell me more" in parsed["message"]
    assert parsed["options"] == []
    assert not parsed["is_complete"]


def test_parse_complete_strategy():
    response = '{"message": "Done!", "options": [], "extracted": {}, "dimensions_complete": ["north_star", "cheapness", "quality"], "is_complete": true, "strategy_profile": {"north_star": "Compounders", "dimensions": {"cheapness": "DCF gap", "quality": "ROIC"}}}'
    parsed = parse_strategy_response(response)
    assert parsed["is_complete"]
    assert parsed["strategy_profile"]["north_star"] == "Compounders"


def test_validate_complete_profile():
    profile = {
        "north_star": "Find compounders",
        "dimensions": {"cheapness": "DCF gap", "quality": "ROIC > 15%"},
    }
    errors = validate_strategy_profile(profile)
    assert errors == []


def test_validate_missing_north_star():
    profile = {"dimensions": {"cheapness": "PE", "quality": "ROIC"}}
    errors = validate_strategy_profile(profile)
    assert any("north star" in e.lower() for e in errors)


def test_validate_too_few_dimensions():
    profile = {"north_star": "Find stocks", "dimensions": {"growth": "10%"}}
    errors = validate_strategy_profile(profile)
    assert any("at least 2" in e for e in errors)


def test_validate_sector_routing_is_freeform():
    """Sector names are free-form — the AI generates them and uses them in scoring code."""
    profile = {
        "north_star": "test",
        "dimensions": {"cheapness": "PE", "quality": "ROIC"},
        "sector_routing": {"Technology": {"cheapness": "ev/fcf"}, "Financials": {"cheapness": "ptbv"}},
    }
    errors = validate_strategy_profile(profile)
    assert errors == []  # No validation on sector names


def test_build_conversation_messages_new():
    messages = build_conversation_messages("I want quality compounders", [])
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "quality compounders" in messages[-1]["content"]


def test_build_conversation_messages_with_history():
    history = [
        {"role": "user", "content": "I like value investing"},
        {"role": "assistant", "content": "What does value mean to you?"},
    ]
    messages = build_conversation_messages("Low PE stocks", history)
    assert len(messages) == 4  # system + 2 history + current


def test_build_conversation_messages_refinement():
    strategy = {"north_star": "Compounders", "dimensions": {"cheapness": "DCF"}}
    messages = build_conversation_messages("Change cheapness to PE", [], strategy)
    assert "CURRENT STRATEGY" in messages[0]["content"]


def test_create_strategy_id():
    sid = create_strategy_id()
    assert sid.startswith("strat-")
    assert len(sid) > 10


def test_strategy_dimensions_are_dynamic():
    # Dimensions are no longer hardcoded — they come from the AI conversation
    assert isinstance(STRATEGY_DIMENSIONS, list)
    # Empty by default, populated dynamically
    assert len(STRATEGY_DIMENSIONS) == 0
