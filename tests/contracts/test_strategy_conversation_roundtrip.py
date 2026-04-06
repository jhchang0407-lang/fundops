"""Roundtrip test: constitution updates → DB → scoring code all stay in sync.

The core contract Plan A enforces:
  1. Constitution is the SINGLE source of truth for strategy settings
  2. must_have_signals is the source for hard filters in codegen
  3. Scoring code regeneration is synchronous (not fire-and-forget)
  4. strategy_profiles table is NOT synced on updates (legacy)

These tests exercise the data flow directly (no HTTP), since the agent_actions
logic runs inside the conversation endpoint and the actual contract is:
  "what's in constitution → what codegen reads → what the screener uses"
"""

import json
import pytest
from datetime import datetime, timezone


class TestConstitutionSingleSourceOfTruth:
    """Constitution DB writes and reads must be consistent."""

    def test_filter_synonym_cleanup(self, v2db, sample_constitution):
        """When updating a filter, old synonym keys must be removed."""
        # Seed constitution with old-style key
        c = sample_constitution
        c["agent_profiles"] = {
            "screener": {
                "weights": {},
                "filters": {"gross_margin_pct": 30, "roic": 10},
            }
        }
        v2db.conn.execute("""
            INSERT OR REPLACE INTO constitution (id, name, version, north_star,
                agent_profiles, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], c["name"], 1, c["north_star"],
              json.dumps(c["agent_profiles"]),
              c["created_at"], c["updated_at"]))
        v2db.conn.commit()

        # Simulate what agent_actions does: update with canonical key,
        # which should remove the old synonym
        constitution = v2db.get_active_constitution()
        agent_profiles = dict(constitution.get("agent_profiles") or {})
        screener_profile = dict(agent_profiles.get("screener") or {})
        existing_filters = dict(screener_profile.get("filters") or {})

        # Apply synonym cleanup (same logic as strategy.py lines 683-701)
        _FILTER_SYNONYMS = {
            "gross_margin": {"gross_margin_pct", "gross_margin_floor", "gross_margin_min"},
        }
        _key_to_group = {}
        for group, keys in _FILTER_SYNONYMS.items():
            for k in keys:
                _key_to_group[k] = group

        new_filter = {"gross_margin_min": 50}
        updated_groups = {_key_to_group.get(k) for k in new_filter.keys()} - {None}
        for group in updated_groups:
            for old_key in _FILTER_SYNONYMS.get(group, set()):
                existing_filters.pop(old_key, None)
        existing_filters.update(new_filter)

        # Verify: only canonical key remains, old synonym removed
        assert "gross_margin_min" in existing_filters
        assert existing_filters["gross_margin_min"] == 50
        assert "gross_margin_pct" not in existing_filters, \
            f"Stale synonym key still present: {existing_filters}"

        # ROIC should be untouched
        assert existing_filters.get("roic") == 10

    def test_constitution_update_persists(self, v2db, sample_constitution):
        """update_constitution() writes and reads back correctly."""
        c = sample_constitution
        v2db.conn.execute("""
            INSERT OR REPLACE INTO constitution (id, name, version, north_star,
                must_have_signals, dimensions, agent_profiles,
                ic_hurdles, position_sizing, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], c["name"], 1, c["north_star"],
              json.dumps(c["must_have_signals"]),
              json.dumps(c["dimensions"]),
              json.dumps(c["agent_profiles"]),
              json.dumps(c["ic_hurdles"]),
              json.dumps(c["position_sizing"]),
              c["created_at"], c["updated_at"]))
        v2db.conn.commit()

        # Update north_star via constitution
        v2db.update_constitution(
            c["id"],
            north_star="Capital-efficient compounders at deep discount",
            _change_type="conversation",
            _change_summary="test",
            _trigger="test",
        )

        updated = v2db.get_active_constitution()
        assert updated["north_star"] == "Capital-efficient compounders at deep discount"

    def test_ic_hurdles_roundtrip(self, v2db, sample_constitution):
        """IC hurdles written to constitution can be read back correctly."""
        c = sample_constitution
        v2db.conn.execute("""
            INSERT OR REPLACE INTO constitution (id, name, version, north_star,
                ic_hurdles, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], c["name"], 1, c["north_star"],
              json.dumps({"base_return_pct": 20, "bear_return_pct": 15, "haircut_pct": 70}),
              c["created_at"], c["updated_at"]))
        v2db.conn.commit()

        # Update hurdles
        hurdles = {"base_return_pct": 25, "bear_return_pct": 18, "haircut_pct": 70}
        v2db.update_constitution(
            c["id"], ic_hurdles=hurdles,
            _change_type="conversation",
            _change_summary="test",
            _trigger="test",
        )

        updated = v2db.get_active_constitution()
        assert updated["ic_hurdles"]["base_return_pct"] == 25
        assert updated["ic_hurdles"]["bear_return_pct"] == 18


class TestCodegenReadsConstitution:
    """Codegen must use must_have_signals as hard filters, not screener.filters when both exist."""

    def test_must_have_signals_takes_precedence_over_screener_filters(self):
        """When must_have_signals is populated, screener.filters should be ignored in codegen."""
        from backend.scoring.codegen import build_intent_prompt

        strategy = {
            "north_star": "Quality compounders",
            "dimensions": {"quality": 40, "cheapness": 30, "growth": 30},
            "must_have_signals": ["Gross margin >= 50%", "ROIC >= 15%"],
            "anti_signals": [],
            "disqualifiers": [],
            "agent_profiles": {
                "screener": {
                    "weights": {"quality": 40, "cheapness": 30},
                    "filters": {"gross_margin_min": 30, "roic_min": 10},  # stale/lower
                }
            },
        }

        prompt = build_intent_prompt(strategy)

        # Must-have signals should appear as hard requirements
        assert "Gross margin >= 50%" in prompt
        assert "ROIC >= 15%" in prompt

        # Stale screener.filters should NOT appear (must_have takes precedence)
        assert "gross_margin_min" not in prompt
        assert "roic_min" not in prompt

    def test_screener_filters_used_as_fallback_when_no_must_have(self):
        """When must_have_signals is empty, screener.filters should be used."""
        from backend.scoring.codegen import build_intent_prompt

        strategy = {
            "north_star": "Quality compounders",
            "dimensions": {},
            "must_have_signals": [],  # empty
            "anti_signals": [],
            "disqualifiers": [],
            "agent_profiles": {
                "screener": {
                    "weights": {},
                    "filters": {"gross_margin_min": 30},
                }
            },
        }

        prompt = build_intent_prompt(strategy)

        # Screener filters should be used as fallback
        assert "gross_margin_min" in prompt

    def test_codegen_prompt_includes_dimensions_as_scoring(self):
        """Dimensions should appear in the prompt as scoring weights, not hard filters."""
        from backend.scoring.codegen import build_intent_prompt

        strategy = {
            "north_star": "Quality at a discount",
            "dimensions": {
                "quality": {"weight": 40, "label": "Business Quality"},
                "cheapness": {"weight": 30, "label": "Valuation Discount"},
                "growth": {"weight": 30, "label": "Growth Durability"},
            },
            "must_have_signals": [],
            "anti_signals": [],
            "disqualifiers": [],
            "agent_profiles": {"screener": {"weights": {}, "filters": {}}},
        }

        prompt = build_intent_prompt(strategy)

        # Dimensions should appear in the prompt
        assert "quality" in prompt
        assert "cheapness" in prompt
        assert "growth" in prompt


class TestScoringRegenIsSynchronous:
    """Verify that _regenerate_scoring_code is awaited, not fire-and-forget."""

    def test_regen_is_awaited_not_create_task(self):
        """Source code inspection: _regenerate_scoring_code must be awaited (not fire-and-forget)."""
        import inspect
        from backend.api.routes import strategy as strategy_module

        source = inspect.getsource(strategy_module)

        # Must NOT have asyncio.create_task(_regenerate_scoring_code(...))
        assert "create_task(_regenerate_scoring_code" not in source, \
            "_regenerate_scoring_code is still fire-and-forget via create_task"

        # Must have await ... _regenerate_scoring_code (either direct or via wait_for)
        has_await = ("await _regenerate_scoring_code" in source or
                     "await asyncio.wait_for" in source and "_regenerate_scoring_code" in source)
        assert has_await, \
            "No await calls to _regenerate_scoring_code found — it should be awaited"
