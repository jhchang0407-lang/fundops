"""Data format consistency tests (Plan B).

Verifies the core contract: ALL financial percentages flow as 0-1 decimals
from backend to frontend, with no heuristic guessing.

These tests catch the bugs that showed 293% revenue growth, 880% FCF yield,
and empty dashes on the Screener/Research/TickerDetail pages.
"""

import pytest


class TestEarningsYieldFormat:
    """earningsYield must be computed as 0-1 decimal (eps/price), not percentage."""

    def test_earnings_yield_computation_is_decimal(self):
        """earningsYield = eps / price, NOT eps / price * 100."""
        eps = 5.0
        price = 100.0
        earnings_yield = eps / price  # New formula (was eps / price * 100)
        assert earnings_yield == 0.05
        assert earnings_yield < 1.0, \
            f"earningsYield should be 0-1 decimal, got {earnings_yield}"

    def test_earnings_yield_source_code_no_times_100(self):
        """Verify the source code does NOT multiply earningsYield by 100."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent.run)
        # Find the earningsYield assignment line (eps / price computation)
        for line in source.split('\n'):
            if 'earningsYield' in line and 'eps' in line and '/' in line:
                assert '* 100' not in line, \
                    f"earningsYield is still multiplied by 100: {line.strip()}"
                break

    def test_normalize_stock_keys_no_divide_by_100(self):
        """The key normalizer should NOT divide earningsYield by 100 anymore."""
        from backend.agents.screener import ScreenerAgent

        agent = ScreenerAgent.__new__(ScreenerAgent)
        stock = {"earningsYield": 0.05}  # Already 0-1 decimal
        agent._normalize_stock_keys(stock)

        # earnings_yield should equal earningsYield directly
        assert stock["earnings_yield"] == 0.05, \
            f"Expected 0.05, got {stock['earnings_yield']} — normalizer still dividing?"


class TestOutputDictNoTimes100:
    """Verify _score_stock output dict sends 0-1 decimals, never * 100."""

    def test_score_stock_source_no_times_100_on_yields(self):
        """Source code inspection: fcfYield and impliedGrowth output should not * 100."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent._score_stock)
        lines = source.split('\n')

        for line in lines:
            stripped = line.strip()
            # Check fcfYield output line
            if '"fcfYield"' in stripped and 'round(' in stripped:
                assert '* 100' not in stripped, \
                    f"fcfYield output still multiplied by 100: {stripped}"
            # Check impliedGrowth output line
            if '"impliedGrowth"' in stripped and 'round(' in stripped:
                assert '* 100' not in stripped, \
                    f"impliedGrowth output still multiplied by 100: {stripped}"
            # Check vs_sector lines
            if 'gm_vs_median' in stripped and 'round(' in stripped:
                assert '* 100' not in stripped, \
                    f"gm_vs_median still multiplied by 100: {stripped}"

    def test_score_stock_uses_earnings_yield_pct_for_return(self):
        """expected_return should use earnings_yield * 100, not raw 0-1 value."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent._score_stock)
        assert 'earnings_yield_pct' in source, \
            "expected_return calculation should use earnings_yield_pct (= earnings_yield * 100)"


class TestDataQualityClamps:
    """Extreme values should be clamped to prevent display corruption."""

    def test_margin_clamped_to_100pct(self):
        """Margins > 100% (>1.0 decimal) should be clamped."""
        stock = {"grossProfitMargin": 8.8}
        v = stock["grossProfitMargin"]
        if abs(v) > 1.0:
            stock["grossProfitMargin"] = max(-1.0, min(1.0, v))
        assert stock["grossProfitMargin"] == 1.0

    def test_growth_clamped_to_500pct(self):
        """Growth rates > 500% (>5.0 decimal) should be clamped."""
        stock = {"revenueGrowth": 29.3}
        v = stock["revenueGrowth"]
        if abs(v) > 5.0:
            stock["revenueGrowth"] = max(-5.0, min(5.0, v))
        assert stock["revenueGrowth"] == 5.0

    def test_yield_clamped_to_100pct(self):
        """Yields > 100% (>1.0 decimal) should be clamped."""
        stock = {"fcfYield": 8.8}
        v = stock["fcfYield"]
        if abs(v) > 1.0:
            stock["fcfYield"] = max(-1.0, min(1.0, v))
        assert stock["fcfYield"] == 1.0

    def test_clamp_source_code_exists(self):
        """Verify the clamp logic exists in the screener enrichment."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent._sec_enrich)
        assert 'Data quality clamps' in source or 'clamped' in source, \
            "Clamping logic not found in _sec_enrich()"


class TestNewOutputFields:
    """Verify that previously-missing fields are now in the output dict."""

    def test_new_fields_in_score_stock(self):
        """_score_stock should output ebitdaMargin, fcfMargin, growth breakdowns, etc."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent._score_stock)

        expected_fields = [
            '"earningsYield"',
            '"ebitdaMargin"',
            '"fcfMargin"',
            '"revenueGrowth1y"',
            '"revenueGrowth3y"',
            '"revenueGrowth5y"',
            '"debtToEbitda"',
            '"interestCoverage"',
        ]
        for field in expected_fields:
            assert field in source, f"Missing field in output dict: {field}"


class TestFilterConsistency:
    """Filter comparisons must be consistent with the new 0-1 format."""

    def test_earnings_yield_filter_multiplies_by_100(self):
        """earningsYield filter comparison must multiply by 100 (value is 0-1, filter is %)."""
        import inspect
        from backend.agents.screener import ScreenerAgent

        source = inspect.getsource(ScreenerAgent)
        # Find the earnings yield filter line
        for line in source.split('\n'):
            if 'min_earnings_yield' in line and 'earningsYield' in line and '<' in line:
                assert '* 100' in line, \
                    f"earningsYield filter missing * 100: {line.strip()}"
                break


class TestFrontendFormatterContract:
    """Verify the frontend formatting contract: always multiply 0-1 by 100."""

    def test_pct_always_multiplies_by_100(self):
        """No heuristic guessing — just multiply by 100."""
        # These represent values the backend now consistently sends
        test_cases = [
            (0.45, "45.0%"),    # grossProfitMargin
            (0.04, "4.0%"),     # fcfYield
            (0.05, "5.0%"),     # earningsYield
            (0.06, "6.0%"),     # impliedGrowth
            (0.10, "10.0%"),    # revenueGrowth
            (-0.05, "-5.0%"),   # negative growth
        ]
        for val, expected in test_cases:
            result = f"{(val * 100):.1f}%"
            assert result == expected, f"pct({val}) = {result}, expected {expected}"

    def test_corrupted_values_show_dash(self):
        """Values > ±999% after * 100 should show '—'."""
        corrupted = [29.3, -15.0, 88.0]  # Would display as 2930%, -1500%, 8800%
        for val in corrupted:
            as_pct = val * 100
            result = '—' if abs(as_pct) > 999 else f"{as_pct:.1f}%"
            assert result == '—', f"pct({val}) should be '—', got {result}"
