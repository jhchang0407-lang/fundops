"""Feedback Loop — Loop 1 (Preference Alignment).

Detects patterns in user feedback on screener results, proposes
scoring code refinements, and applies them via suggest-and-confirm.

Flow:
  User dismisses 3+ stocks with same tag → pattern detected →
  AI proposes scoring code change → user accepts/rejects →
  new strategy version created (or not)

This is the fastest learning loop. Works immediately with user actions.
"""

import json
import logging
import uuid
from collections import Counter
from typing import Optional

log = logging.getLogger("fundops.learning.feedback_loop")

# Minimum feedback count before a pattern is actionable
MIN_PATTERN_THRESHOLD = 3


async def detect_patterns(db) -> list[dict]:
    """Analyze feedback records for recurring patterns.

    Groups dismissals by reason and promotions by shared traits.
    Returns patterns that cross the MIN_PATTERN_THRESHOLD.

    Args:
        db: ScreenerV2DB instance

    Returns:
        List of pattern dicts:
        [{
            "type": "dismiss_cluster" | "promote_cluster",
            "count": int,
            "tag": str,           # dismiss reason or shared trait
            "tickers": [str],
            "details": str,       # human-readable description
            "evidence": [dict],   # the feedback records
        }]
    """
    patterns = []

    # Get all feedback across recent runs
    recent_runs = db.get_runs_by_strategy(limit=10)
    all_feedback = []
    for run in recent_runs:
        run_feedback = db.get_feedback_for_run(run["id"])
        for fb in run_feedback:
            fb["run_id"] = run["id"]
            all_feedback.append(fb)

    if not all_feedback:
        return []

    # --- Dismiss patterns: cluster by reason ---
    dismissals = [f for f in all_feedback if f.get("feedback") == "dismissed"]
    reason_counter = Counter()
    reason_tickers: dict[str, list] = {}
    reason_evidence: dict[str, list] = {}

    for d in dismissals:
        reason = d.get("dismiss_reason") or "unspecified"
        reason_counter[reason] += 1
        reason_tickers.setdefault(reason, []).append(d.get("ticker", ""))
        reason_evidence.setdefault(reason, []).append(d)

    for reason, count in reason_counter.items():
        if count >= MIN_PATTERN_THRESHOLD:
            patterns.append({
                "type": "dismiss_cluster",
                "count": count,
                "tag": reason,
                "tickers": reason_tickers[reason],
                "details": f"{count} stocks dismissed with reason '{reason}': {', '.join(reason_tickers[reason][:5])}",
                "evidence": reason_evidence[reason],
            })

    # --- Promote patterns: look for shared traits in promoted stocks ---
    promotions = [f for f in all_feedback if f.get("feedback") == "promoted"]
    if len(promotions) >= MIN_PATTERN_THRESHOLD:
        promoted_tickers = [p.get("ticker", "") for p in promotions]
        patterns.append({
            "type": "promote_cluster",
            "count": len(promotions),
            "tag": "promoted_favorites",
            "tickers": promoted_tickers,
            "details": f"{len(promotions)} stocks promoted: {', '.join(promoted_tickers[:5])}",
            "evidence": promotions,
        })

    # --- Score-based patterns: consistently dismissing high-scored stocks ---
    high_score_dismissals = [
        d for d in dismissals
        if d.get("score_at_feedback") and d["score_at_feedback"] >= 70
    ]
    if len(high_score_dismissals) >= 2:
        patterns.append({
            "type": "high_score_dismiss",
            "count": len(high_score_dismissals),
            "tag": "scoring_mismatch",
            "tickers": [d.get("ticker", "") for d in high_score_dismissals],
            "details": f"{len(high_score_dismissals)} high-scoring stocks (>70) were dismissed — scoring function may be overweighting something",
            "evidence": high_score_dismissals,
        })

    return patterns


async def propose_refinement(llm, pattern: dict, current_code: str,
                              constitution: dict = None) -> dict:
    """Given a detected pattern, propose a scoring code change.

    Uses the LLM to analyze the pattern and suggest a modification to the
    existing scoring function. The proposal includes the new code, a diff
    description, and confidence level.

    Args:
        llm: LLMClient instance
        pattern: Pattern dict from detect_patterns()
        current_code: Current scoring function source code
        constitution: Active constitution for context

    Returns:
        {
            "id": str,
            "pattern": dict,
            "proposal": str,          # human description of the change
            "new_code": str | None,    # modified scoring code (or None if no code change)
            "confidence": float,       # 0-1
            "evidence_summary": str,
            "status": "pending",
        }
    """
    proposal_id = f"prop-{uuid.uuid4().hex[:8]}"

    # Build context for the LLM
    constitution_context = ""
    if constitution:
        constitution_context = f"""
INVESTOR'S CONSTITUTION:
- North Star: {constitution.get('north_star', 'N/A')}
- Style: {constitution.get('style_identity', 'N/A')}
- Must-have signals: {constitution.get('must_have_signals', [])}
- Anti-signals: {constitution.get('anti_signals', [])}
"""

    prompt = f"""You are a quantitative analyst reviewing user feedback on a stock screener.

CURRENT SCORING FUNCTION:
```python
{current_code}
```
{constitution_context}
PATTERN DETECTED:
Type: {pattern['type']}
Details: {pattern['details']}
Tickers affected: {', '.join(pattern['tickers'][:10])}
Dismiss reasons: {pattern.get('tag', 'N/A')}

The user keeps dismissing stocks that score well in the current function, or the function
misses what the user actually wants. Analyze why and propose a specific change to the
scoring function.

RESPOND IN THIS EXACT JSON FORMAT:
{{
    "analysis": "Why does the current scoring miss what the user wants? (2-3 sentences)",
    "proposal": "What should change in the scoring function? (1 sentence, plain English)",
    "code_change": "The specific lines to add/modify in the score() function. Just the changed/new lines, not the whole function.",
    "confidence": 0.7,
    "risk": "What could go wrong with this change? (1 sentence)"
}}

Be specific. Reference actual variable names from the scoring function.
If the pattern is weak or unclear, set confidence below 0.5 and say so.
RETURN ONLY VALID JSON. No markdown fences."""

    try:
        result = await llm.generate(prompt, agent="feedback_loop", reasoning_effort="high")
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())

        return {
            "id": proposal_id,
            "pattern": {
                "type": pattern["type"],
                "tag": pattern["tag"],
                "count": pattern["count"],
                "tickers": pattern["tickers"][:10],
            },
            "proposal": parsed.get("proposal", ""),
            "analysis": parsed.get("analysis", ""),
            "code_change": parsed.get("code_change", ""),
            "confidence": min(1.0, max(0.0, float(parsed.get("confidence", 0.5)))),
            "risk": parsed.get("risk", ""),
            "evidence_summary": pattern["details"],
            "status": "pending",
            "cost": result.cost,
        }

    except Exception as e:
        log.warning(f"Refinement proposal generation failed: {e}")
        return {
            "id": proposal_id,
            "pattern": {
                "type": pattern["type"],
                "tag": pattern["tag"],
                "count": pattern["count"],
                "tickers": pattern["tickers"][:10],
            },
            "proposal": f"Pattern detected ({pattern['details']}) but auto-analysis failed: {e}",
            "analysis": "",
            "code_change": "",
            "confidence": 0.0,
            "risk": "Auto-analysis failed",
            "evidence_summary": pattern["details"],
            "status": "error",
        }


async def generate_refined_code(llm, current_code: str, proposal: dict,
                                 strategy: dict = None) -> Optional[str]:
    """Generate a full updated scoring function incorporating the proposal.

    Args:
        llm: LLMClient instance
        current_code: Current scoring function source
        proposal: Proposal dict from propose_refinement()
        strategy: Strategy profile for context

    Returns:
        New scoring code string (validated), or None if generation fails.
    """
    from backend.scoring.sandbox import validate_ast, compile_scoring_function, ScoringCodeError
    from backend.scoring.codegen import build_metric_schema

    prompt = f"""Modify this scoring function based on the proposed change.

CURRENT FUNCTION:
```python
{current_code}
```

PROPOSED CHANGE:
{proposal['proposal']}

SPECIFIC CODE CHANGE:
{proposal.get('code_change', 'N/A')}

AVAILABLE METRICS:
{build_metric_schema()}

RULES:
- Return ONLY the complete modified score() function
- Keep the same signature: def score(stock):
- Keep safe_get(), clamp(), normalize() helpers
- No imports allowed
- Must return a dict with at least 'score' and 'reason' keys
- Under 100 lines
- Do NOT wrap in markdown fences

Return the complete function."""

    try:
        result = await llm.generate(prompt, agent="feedback_loop_codegen")
        code = result.text.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[1] if "\n" in code else code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        errors = validate_ast(code)
        if errors:
            log.warning(f"Refined code validation failed: {errors}")
            return None

        compile_scoring_function(code)
        return code

    except Exception as e:
        log.warning(f"Refined code generation failed: {e}")
        return None
