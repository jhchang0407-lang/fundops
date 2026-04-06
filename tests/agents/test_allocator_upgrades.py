"""Tests for Allocator sell discipline integration (Work Stream G1)."""

import asyncio
import pytest

from backend.agents.allocator import AllocatorAgent


def _run(coro):
    """Helper to run async agent in sync tests."""
    return asyncio.run(coro)


def _make_context(holdings, alerts=None, sell_discipline=None, constitution_extra=None):
    """Build a context dict with optional sell discipline."""
    constitution = {}
    if sell_discipline is not None:
        constitution["sell_discipline"] = sell_discipline
    if constitution_extra:
        constitution.update(constitution_extra)
    return {
        "holdings": holdings,
        "alerts": alerts or [],
        "constitution": constitution if constitution else {},
    }


class TestSellDisciplineMaxLoss:
    def test_exit_when_loss_exceeds_threshold(self):
        """pnl_pct of -30% with max_loss_pct=25 should produce EXIT."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{"ticker": "ACME", "weight": 10, "pnl_pct": -30, "type": "core"}],
            sell_discipline={"max_loss_pct": 25},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        actions = result.data["actions_required"]
        assert len(actions) == 1
        act = actions[0]
        assert act["action"] == "EXIT"
        assert act["ticker"] == "ACME"
        assert act["urgency"] == "high"
        assert act["sell_discipline_triggered"] is True
        assert "max_loss_pct" in act["sell_rule"]

    def test_no_exit_when_loss_below_threshold(self):
        """pnl_pct of -10% with max_loss_pct=25 should NOT trigger EXIT."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{"ticker": "ACME", "weight": 10, "pnl_pct": -10, "type": "core"}],
            sell_discipline={"max_loss_pct": 25},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        # Should land in no_action (HOLD), not actions_required
        actions = result.data["actions_required"]
        exit_actions = [a for a in actions if a.get("sell_discipline_triggered")]
        assert len(exit_actions) == 0


class TestSellDisciplineMinReturn:
    def test_trim_when_return_below_threshold(self):
        """Expected return 5% with min_remaining_return_pct=10 should TRIM."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{
                "ticker": "SLOW",
                "weight": 8,
                "pnl_pct": 5,
                "expected_return": 5,
                "type": "core",
            }],
            sell_discipline={"min_remaining_return_pct": 10},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        actions = result.data["actions_required"]
        assert len(actions) == 1
        act = actions[0]
        assert act["action"] == "TRIM"
        assert act["sell_discipline_triggered"] is True
        assert "min_remaining_return_pct" in act["sell_rule"]

    def test_no_trim_when_return_above_threshold(self):
        """Expected return 15% with min_remaining_return_pct=10 should not trigger."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{
                "ticker": "FAST",
                "weight": 8,
                "pnl_pct": 5,
                "expected_return": 15,
                "type": "core",
            }],
            sell_discipline={"min_remaining_return_pct": 10},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        sell_actions = [
            a for a in result.data["actions_required"]
            if a.get("sell_discipline_triggered")
        ]
        assert len(sell_actions) == 0


class TestNoSellDiscipline:
    def test_no_constitution_no_sell_actions(self):
        """Without constitution, allocator behaves exactly as before."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{"ticker": "SAFE", "weight": 10, "pnl_pct": -30, "type": "core"}],
            sell_discipline=None,
        )
        result = _run(agent.run(ctx))
        assert result.ok
        # -30% loss but no sell discipline, so no EXIT from sell rules
        sell_actions = [
            a for a in result.data["actions_required"]
            if a.get("sell_discipline_triggered")
        ]
        assert len(sell_actions) == 0

    def test_empty_sell_discipline_no_sell_actions(self):
        """Empty sell_discipline dict should not trigger any sell rules."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{"ticker": "SAFE", "weight": 10, "pnl_pct": -30, "type": "core"}],
            sell_discipline={},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        sell_actions = [
            a for a in result.data["actions_required"]
            if a.get("sell_discipline_triggered")
        ]
        assert len(sell_actions) == 0


class TestSellDisciplinePriority:
    def test_sell_discipline_exit_overrides_hold(self):
        """A position that would normally HOLD gets EXIT from sell discipline."""
        agent = AllocatorAgent()
        # weight=10 (within limits), no alerts -> would normally HOLD
        # But pnl_pct=-30 with max_loss_pct=25 -> EXIT from sell discipline
        ctx = _make_context(
            holdings=[{"ticker": "OVER", "weight": 10, "pnl_pct": -30, "type": "core"}],
            sell_discipline={"max_loss_pct": 25},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        actions = result.data["actions_required"]
        assert len(actions) == 1
        assert actions[0]["action"] == "EXIT"
        assert actions[0]["sell_discipline_triggered"] is True
        # Should NOT appear in no_action (HOLD)
        hold_tickers = [a["ticker"] for a in result.data["no_action"]]
        assert "OVER" not in hold_tickers

    def test_sell_discipline_exit_overrides_add_on_weakness(self):
        """A position that would be ADD_ON_WEAKNESS gets EXIT instead."""
        agent = AllocatorAgent()
        # weight=1 (below typical range) and pnl_pct > -20 -> would be ADD_ON_WEAKNESS
        # But sell discipline max_loss is very low (5%) and pnl = -10 -> EXIT
        ctx = _make_context(
            holdings=[{"ticker": "WEAK", "weight": 1, "pnl_pct": -10, "type": "core"}],
            sell_discipline={"max_loss_pct": 5},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        actions = result.data["actions_required"]
        assert len(actions) == 1
        assert actions[0]["action"] == "EXIT"
        # Should NOT appear in monitoring
        mon_tickers = [a["ticker"] for a in result.data["monitoring"]]
        assert "WEAK" not in mon_tickers


class TestThesisBreachConsecutiveQuarters:
    def test_exit_on_consecutive_breaches(self):
        """Consecutive breach quarters >= threshold should EXIT."""
        agent = AllocatorAgent()
        ctx = _make_context(
            holdings=[{
                "ticker": "BREACH",
                "weight": 8,
                "pnl_pct": -5,
                "consecutive_breach_quarters": 3,
                "type": "core",
            }],
            sell_discipline={"thesis_breach_consecutive_quarters": 2},
        )
        result = _run(agent.run(ctx))
        assert result.ok
        actions = result.data["actions_required"]
        assert len(actions) == 1
        assert actions[0]["action"] == "EXIT"
        assert "thesis_breach_consecutive_quarters" in actions[0]["sell_rule"]
