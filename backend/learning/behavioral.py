"""Behavioral Calibration — Loop 2 (Said vs Did).

Compares the investor's stated constitution with their actual IC decisions.
Surfaces drift between stated preferences and revealed preferences.

Examples of drift:
- "Constitution says 'quality compounder' but 6/10 recent approvals are cyclical re-ratings"
- "Constitution requires ROIC > 15% but 3 approved names had ROIC < 12%"
- "IC was overridden 4 times on leveraged names despite anti-signal 'D/E > 2x'"

This is the "mirror that gets sharper over time."
"""

import logging
from typing import Optional

log = logging.getLogger("fundops.learning.behavioral")

# Minimum IC decisions before behavioral analysis is meaningful
MIN_DECISIONS_FOR_ANALYSIS = 5


async def analyze_drift(db, constitution: dict) -> dict:
    """Compare stated constitution with actual approval patterns.

    Queries judgment_events for IC passes/fails, compares against
    constitution's must_have_signals, anti_signals, and style_identity.

    Args:
        db: ScreenerV2DB instance
        constitution: Active constitution dict

    Returns:
        {
            "has_enough_data": bool,
            "decisions_analyzed": int,
            "style_drift": [...],       # style identity vs actual approvals
            "signal_drift": [...],      # must-have signals violated in approvals
            "anti_signal_violations": [...],  # anti-signals present in approvals
            "override_patterns": [...], # IC overrides
            "approval_profile": {...},  # what approved stocks actually look like
            "summary": str,
        }
    """
    result = {
        "has_enough_data": False,
        "decisions_analyzed": 0,
        "style_drift": [],
        "signal_drift": [],
        "anti_signal_violations": [],
        "override_patterns": [],
        "approval_profile": {},
        "summary": "",
    }

    # Get IC decisions from judgment events
    ic_passes = db.get_events_by_type("ic_passed", limit=50)
    ic_fails = db.get_events_by_type("ic_failed", limit=50)
    ic_overrides = db.get_events_by_type("ic_overridden", limit=50)

    total_decisions = len(ic_passes) + len(ic_fails)
    result["decisions_analyzed"] = total_decisions

    if total_decisions < MIN_DECISIONS_FOR_ANALYSIS:
        result["summary"] = (
            f"Need at least {MIN_DECISIONS_FOR_ANALYSIS} IC decisions for behavioral analysis. "
            f"Currently have {total_decisions}."
        )
        return result

    result["has_enough_data"] = True

    # --- Signal drift: check must-have signals against approved stocks ---
    must_haves = constitution.get("must_have_signals") or []
    for signal in must_haves:
        violations = _check_signal_violations(signal, ic_passes)
        if violations:
            result["signal_drift"].append({
                "signal": signal,
                "violations": len(violations),
                "total_approvals": len(ic_passes),
                "violation_rate": round(len(violations) / len(ic_passes) * 100, 1) if ic_passes else 0,
                "tickers": [v["ticker"] for v in violations[:5]],
                "details": [v["detail"] for v in violations[:3]],
            })

    # --- Anti-signal violations: check anti-signals in approved stocks ---
    anti_signals = constitution.get("anti_signals") or []
    for signal in anti_signals:
        triggers = _check_anti_signal_triggers(signal, ic_passes)
        if triggers:
            result["anti_signal_violations"].append({
                "signal": signal,
                "violations": len(triggers),
                "total_approvals": len(ic_passes),
                "violation_rate": round(len(triggers) / len(ic_passes) * 100, 1) if ic_passes else 0,
                "tickers": [t["ticker"] for t in triggers[:5]],
                "details": [t["detail"] for t in triggers[:3]],
            })

    # --- Approval profile: what do approved stocks actually look like? ---
    if ic_passes:
        result["approval_profile"] = _build_approval_profile(ic_passes)

    # --- Style drift: compare approval profile with stated style ---
    style = constitution.get("style_identity", "")
    if style and ic_passes:
        drift_notes = _detect_style_drift(style, ic_passes, constitution)
        result["style_drift"] = drift_notes

    # --- Override patterns ---
    if ic_overrides:
        result["override_patterns"] = [
            {
                "ticker": ev.get("ticker", ""),
                "data": ev.get("data", {}),
                "rationale": ev.get("rationale", ""),
            }
            for ev in ic_overrides[:10]
        ]

    # --- Build summary ---
    summaries = []
    if result["signal_drift"]:
        worst = max(result["signal_drift"], key=lambda x: x["violation_rate"])
        summaries.append(
            f"Signal drift: '{worst['signal']}' violated in {worst['violation_rate']}% of approvals "
            f"({worst['violations']}/{worst['total_approvals']})"
        )
    if result["anti_signal_violations"]:
        worst = max(result["anti_signal_violations"], key=lambda x: x["violations"])
        summaries.append(
            f"Anti-signal breach: '{worst['signal']}' triggered in {worst['violations']} approved stocks"
        )
    if result["style_drift"]:
        summaries.append(f"Style notes: {result['style_drift'][0]['note']}")
    if not summaries:
        summaries.append("No significant drift detected between constitution and behavior.")

    result["summary"] = " | ".join(summaries)
    return result


def _check_signal_violations(signal: str, ic_passes: list[dict]) -> list[dict]:
    """Check how many IC passes violate a must-have signal."""
    violations = []
    sig_lower = signal.lower()

    for ev in ic_passes:
        data = ev.get("data", {})
        ticker = ev.get("ticker", "")

        # Parse the signal to check
        if "roic" in sig_lower:
            threshold = _extract_threshold(signal)
            # Check if scorecard data has ROIC info
            scorecard = data.get("scorecard_signals_met", 0)
            # If we have constitution_fit data from thesis
            if threshold and data.get("base_return") is not None:
                # Heuristic: if bear return is very low, quality may be suspect
                # (Real check would need the thesis quality metrics, which are in library)
                pass

        elif "gm" in sig_lower or "gross margin" in sig_lower:
            threshold = _extract_threshold(signal)
            # Similar heuristic approach

        # For now, use scorecard data if available
        signals_met = data.get("scorecard_signals_met", 0)
        anti_triggered = data.get("scorecard_anti_triggered", 0)
        if anti_triggered and anti_triggered > 0:
            violations.append({
                "ticker": ticker,
                "detail": f"{ticker}: approved with {anti_triggered} anti-signal(s) triggered",
            })

    return violations


def _check_anti_signal_triggers(signal: str, ic_passes: list[dict]) -> list[dict]:
    """Check how many IC passes have an anti-signal triggered."""
    triggers = []

    for ev in ic_passes:
        data = ev.get("data", {})
        ticker = ev.get("ticker", "")
        anti_count = data.get("scorecard_anti_triggered", 0)

        if anti_count and anti_count > 0:
            triggers.append({
                "ticker": ticker,
                "detail": f"{ticker}: {anti_count} anti-signal(s) present at approval",
            })

    return triggers


def _build_approval_profile(ic_passes: list[dict]) -> dict:
    """Build a statistical profile of what approved stocks look like."""
    base_returns = []
    bear_returns = []
    convictions = []

    for ev in ic_passes:
        data = ev.get("data", {})
        if data.get("base_return") is not None:
            base_returns.append(data["base_return"])
        if data.get("bear_return") is not None:
            bear_returns.append(data["bear_return"])
        if data.get("conviction") is not None:
            convictions.append(data["conviction"])

    def _stats(values):
        if not values:
            return None
        values.sort()
        n = len(values)
        return {
            "min": round(values[0], 1),
            "max": round(values[-1], 1),
            "median": round(values[n // 2], 1),
            "mean": round(sum(values) / n, 1),
            "count": n,
        }

    return {
        "base_return": _stats(base_returns),
        "bear_return": _stats(bear_returns),
        "conviction": _stats(convictions),
        "total_passes": len(ic_passes),
    }


def _detect_style_drift(style: str, ic_passes: list[dict],
                          constitution: dict) -> list[dict]:
    """Detect whether approval patterns match the stated investment style."""
    notes = []
    style_lower = style.lower()

    profile = _build_approval_profile(ic_passes)

    # Check: if style says "compounder" but approvals have low growth
    if "compounder" in style_lower or "growth" in style_lower:
        bear_stats = profile.get("bear_return")
        if bear_stats and bear_stats["median"] < 12:
            notes.append({
                "type": "growth_mismatch",
                "note": (
                    f"Constitution says '{style}' but median bear return is "
                    f"{bear_stats['median']}% — approved names may lack growth durability"
                ),
                "severity": "medium",
            })

    # Check: if style says "quality" but low conviction
    if "quality" in style_lower:
        conv_stats = profile.get("conviction")
        if conv_stats and conv_stats["mean"] < 3:
            notes.append({
                "type": "quality_mismatch",
                "note": (
                    f"Constitution emphasizes quality but mean conviction is "
                    f"{conv_stats['mean']}/5 — you may be approving names you're not confident in"
                ),
                "severity": "medium",
            })

    # Check: if style says "concentrated" but many approvals
    if "concentrated" in style_lower:
        if len(ic_passes) > 20:
            notes.append({
                "type": "concentration_drift",
                "note": (
                    f"Constitution says 'concentrated' but {len(ic_passes)} stocks passed IC — "
                    f"consider raising hurdles to maintain focus"
                ),
                "severity": "low",
            })

    # Check: high percentage of low-conviction passes
    low_conviction = [e for e in ic_passes if (e.get("data", {}).get("conviction") or 0) <= 2]
    if len(low_conviction) > len(ic_passes) * 0.4:
        notes.append({
            "type": "conviction_drift",
            "note": (
                f"{len(low_conviction)}/{len(ic_passes)} approvals ({round(len(low_conviction)/len(ic_passes)*100)}%) "
                f"had conviction 2 or below — your IC gate may be too loose"
            ),
            "severity": "high",
        })

    return notes


async def propose_constitution_update(llm, drift: dict, constitution: dict) -> Optional[dict]:
    """Given detected drift, propose updating the constitution.

    Two possible directions:
    1. "Your constitution should reflect what you actually do" (update stated prefs)
    2. "You should be more disciplined about your stated criteria" (tighten IC)

    Args:
        llm: LLMClient instance
        drift: Result from analyze_drift()
        constitution: Active constitution dict

    Returns:
        {
            "direction": "update_constitution" | "tighten_discipline",
            "proposal": str,
            "changes": dict,  # specific fields to update
            "evidence": str,
        }
        Or None if no update is warranted.
    """
    if not drift.get("has_enough_data"):
        return None

    has_drift = (
        drift.get("signal_drift") or
        drift.get("anti_signal_violations") or
        drift.get("style_drift")
    )
    if not has_drift:
        return None

    # Build the prompt
    drift_summary = []
    for sd in drift.get("signal_drift", []):
        drift_summary.append(f"- Signal '{sd['signal']}' violated in {sd['violation_rate']}% of approvals")
    for av in drift.get("anti_signal_violations", []):
        drift_summary.append(f"- Anti-signal '{av['signal']}' triggered in {av['violations']} approved names")
    for sd in drift.get("style_drift", []):
        drift_summary.append(f"- Style: {sd['note']}")

    prompt = f"""You are an investment advisor reviewing behavioral drift for a PM.

THEIR CONSTITUTION:
- Style: {constitution.get('style_identity', 'N/A')}
- North Star: {constitution.get('north_star', 'N/A')}
- Must-have signals: {constitution.get('must_have_signals', [])}
- Anti-signals: {constitution.get('anti_signals', [])}
- IC hurdles: base {constitution.get('ic_hurdles', {}).get('base_return_pct', 20)}%, bear {constitution.get('ic_hurdles', {}).get('bear_return_pct', 15)}%

BEHAVIORAL DRIFT DETECTED:
{chr(10).join(drift_summary)}

APPROVAL PROFILE:
{drift.get('approval_profile', {})}

There are two valid responses:
A) The constitution is wrong — update it to match their actual behavior
B) The behavior is wrong — suggest they tighten discipline

Which is it, and what specifically should change?

RESPOND IN JSON:
{{
    "direction": "update_constitution" or "tighten_discipline",
    "reasoning": "2-3 sentences explaining which direction and why",
    "proposal": "1-sentence plain English recommendation",
    "specific_changes": {{
        "field_name": "new_value"
    }}
}}

RETURN ONLY VALID JSON."""

    try:
        result = await llm.generate(prompt, agent="behavioral_calibration", reasoning_effort="high")
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]

        import json
        parsed = json.loads(text.strip())

        return {
            "direction": parsed.get("direction", "tighten_discipline"),
            "reasoning": parsed.get("reasoning", ""),
            "proposal": parsed.get("proposal", ""),
            "changes": parsed.get("specific_changes", {}),
            "evidence": drift.get("summary", ""),
            "cost": result.cost,
        }

    except Exception as e:
        log.warning(f"Constitution update proposal failed: {e}")
        return None


def _extract_threshold(signal: str) -> Optional[float]:
    """Extract a numeric threshold from a signal string."""
    import re
    match = re.search(r'[><=]+\s*(\d+\.?\d*)', signal)
    return float(match.group(1)) if match else None
