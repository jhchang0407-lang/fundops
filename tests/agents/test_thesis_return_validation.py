"""Tests for ThesisAgent._validate_return_sources (C3)."""

import pytest

from backend.agents.thesis import ThesisAgent


@pytest.fixture
def agent():
    return ThesisAgent(config={})


# --- Sum check ---

def test_return_sources_sum_correctly(agent):
    """Sources that sum to expected_return should pass validation."""
    return_sources = {"discount": 10.0, "growth": 8.0, "margin": 3.0, "dividends": 1.5}
    expected_return = 22.5
    data = {"discount_pct": 20.0, "revenue_growth": 0.08}

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is True
    assert result["warnings"] == []


def test_return_sources_sum_within_tolerance(agent):
    """Sources that sum within tolerance should pass."""
    return_sources = {"discount": 10.0, "growth": 8.0, "margin": 3.0, "dividends": 1.5}
    expected_return = 24.0  # diff = 1.5, within default 2.0 tolerance
    data = {"discount_pct": 20.0, "revenue_growth": 0.08}

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is True


def test_return_sources_sum_mismatch(agent):
    """Sources that don't sum to expected_return should warn."""
    return_sources = {"discount": 10.0, "growth": 8.0, "margin": 3.0, "dividends": 1.5}
    expected_return = 30.0  # actual sum is 22.5, diff = 7.5
    data = {"discount_pct": 20.0, "revenue_growth": 0.08}

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is False
    assert any("sum" in w.lower() for w in result["warnings"])


# --- Negative source check ---

def test_return_sources_negative_caught(agent):
    """Negative return source should produce a warning."""
    return_sources = {"discount": 10.0, "growth": -3.0, "margin": 5.0, "dividends": 1.0}
    expected_return = 13.0
    data = {"discount_pct": 20.0, "revenue_growth": 0.05}

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is False
    assert any("negative" in w.lower() for w in result["warnings"])
    assert any("growth" in w.lower() for w in result["warnings"])


# --- Growth reasonableness ---

def test_return_sources_growth_reasonable(agent):
    """Growth source matching actual revenue growth should not warn."""
    return_sources = {"discount": 10.0, "growth": 8.0, "margin": 3.0, "dividends": 1.0}
    expected_return = 22.0
    data = {"discount_pct": 20.0, "revenue_growth": 0.10}  # 10% actual, 8% source = fine

    result = agent._validate_return_sources(return_sources, expected_return, data)

    # No growth-specific warning
    assert not any("exceeds actual revenue growth" in w for w in result["warnings"])


def test_return_sources_growth_unreasonable(agent):
    """Growth source of 20% but actual growth is 3% should warn."""
    return_sources = {"discount": 5.0, "growth": 20.0, "margin": 2.0, "dividends": 0.5}
    expected_return = 27.5
    data = {"discount_pct": 10.0, "revenue_growth": 0.03}  # 3% actual vs 20% source

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is False
    assert any("exceeds actual revenue growth" in w for w in result["warnings"])
    assert "growth" in result["adjustments"]
    assert result["adjustments"]["growth"]["actual_revenue_growth"] == 3.0


# --- Discount consistency ---

def test_discount_source_consistent(agent):
    """Discount source consistent with discount_pct * 0.5 should not warn."""
    return_sources = {"discount": 15.0, "growth": 5.0, "margin": 2.0, "dividends": 1.0}
    expected_return = 23.0
    data = {"discount_pct": 30.0, "revenue_growth": 0.05}  # 30 * 0.5 = 15.0 = matches

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert not any("inconsistent" in w.lower() for w in result["warnings"])


def test_discount_source_inconsistent(agent):
    """Discount source far from discount_pct * 0.5 should warn."""
    return_sources = {"discount": 20.0, "growth": 5.0, "margin": 2.0, "dividends": 1.0}
    expected_return = 28.0
    data = {"discount_pct": 10.0, "revenue_growth": 0.05}  # 10 * 0.5 = 5.0 vs stated 20.0

    result = agent._validate_return_sources(return_sources, expected_return, data)

    assert result["valid"] is False
    assert any("inconsistent" in w.lower() for w in result["warnings"])
    assert "discount" in result["adjustments"]
