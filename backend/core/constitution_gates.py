"""Constitution enforcement — deterministic pre-flight checks.

Parses disqualifiers, must-have signals, and anti-signals from the
constitution and checks them mechanically against stock data. Free-form
text signals that can't be parsed become warnings, not violations.

Used by the orchestrator before running thesis/IC/memo agents.
"""

import logging
import re
from typing import Any

from backend.core.metric_schema import resolve_alias

log = logging.getLogger("fundops.constitution_gates")

# Operators we can parse from free-text disqualifier strings
_OP_MAP = {
    ">=": ">=", "<=": "<=",
    ">": ">", "<": "<",
    "==": "==", "=": "==",
}


def _parse_metric_condition(text: str) -> tuple[str, str, float] | None:
    """Try to parse a string like 'debt_equity > 5' into (field, op, value).

    Returns None if the string can't be parsed mechanically.
    """
    text = text.strip()
    # Match patterns like: metric_name > 5.0, roic >= 0.15
    match = re.match(
        r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|>|<|==|=)\s*(-?[\d.]+)",
        text,
    )
    if not match:
        return None

    field_raw, op_raw, value_raw = match.groups()
    canonical = resolve_alias(field_raw)
    if canonical is None:
        return None

    op = _OP_MAP.get(op_raw)
    if op is None:
        return None

    try:
        value = float(value_raw)
    except ValueError:
        return None

    return (canonical, op, value)


def _check_condition(data_value: float, operator: str, threshold: float) -> bool:
    """Evaluate a single condition."""
    if operator == ">":
        return data_value > threshold
    elif operator == ">=":
        return data_value >= threshold
    elif operator == "<":
        return data_value < threshold
    elif operator == "<=":
        return data_value <= threshold
    elif operator == "==":
        return abs(data_value - threshold) < 0.001
    return False


def check_preflight(
    constitution: dict,
    data: dict,
    agent: str = "",
) -> dict:
    """Run deterministic pre-flight checks against the constitution.

    Args:
        constitution: Active constitution dict (from DB)
        data: Stock/thesis data dict with metric values
        agent: Which agent is about to run (for context)

    Returns:
        {
            "pass": bool,
            "violations": list[str],   # hard blocks
            "warnings": list[str],     # advisories (free-text signals)
        }
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not constitution:
        return {"pass": True, "violations": [], "warnings": []}

    ticker = data.get("ticker", "unknown")

    # --- Disqualifiers: if matched, violation ---
    disqualifiers = constitution.get("disqualifiers") or []
    for dq in disqualifiers:
        if not isinstance(dq, str):
            continue
        parsed = _parse_metric_condition(dq)
        if parsed:
            field, op, threshold = parsed
            val = _get_metric_value(data, field)
            if val is not None and _check_condition(val, op, threshold):
                violations.append(
                    f"Disqualifier triggered: {dq} "
                    f"(actual {field}={val:.2f})"
                )
        else:
            # Free-form text disqualifier — can't check mechanically
            warnings.append(f"Cannot verify disqualifier mechanically: '{dq}'")

    # --- Anti-signals: if matched, violation ---
    anti_signals = constitution.get("anti_signals") or []
    for signal in anti_signals:
        if not isinstance(signal, str):
            continue
        parsed = _parse_metric_condition(signal)
        if parsed:
            field, op, threshold = parsed
            val = _get_metric_value(data, field)
            if val is not None and _check_condition(val, op, threshold):
                violations.append(
                    f"Anti-signal matched: {signal} "
                    f"(actual {field}={val:.2f})"
                )
        else:
            warnings.append(f"Cannot verify anti-signal mechanically: '{signal}'")

    # --- Must-have signals: if NOT matched, violation ---
    must_have = constitution.get("must_have_signals") or []
    for signal in must_have:
        if not isinstance(signal, str):
            continue
        parsed = _parse_metric_condition(signal)
        if parsed:
            field, op, threshold = parsed
            val = _get_metric_value(data, field)
            if val is not None and not _check_condition(val, op, threshold):
                violations.append(
                    f"Must-have signal not met: {signal} "
                    f"(actual {field}={val:.2f})"
                )
            elif val is None:
                warnings.append(
                    f"Cannot check must-have signal '{signal}': "
                    f"metric '{field}' not in data"
                )
        else:
            warnings.append(f"Cannot verify must-have signal mechanically: '{signal}'")

    passed = len(violations) == 0

    if violations:
        log.info(
            f"[{ticker}] Constitution pre-flight FAILED for {agent}: "
            f"{len(violations)} violation(s)"
        )
    elif warnings:
        log.debug(
            f"[{ticker}] Constitution pre-flight PASSED with "
            f"{len(warnings)} warning(s)"
        )

    return {
        "pass": passed,
        "violations": violations,
        "warnings": warnings,
    }


def _get_metric_value(data: dict, canonical_name: str) -> float | None:
    """Extract a metric value from data dict, trying common key patterns."""
    # Direct lookup
    val = data.get(canonical_name)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass

    # Try nested in 'quality' dict (common in thesis output)
    quality = data.get("quality", {})
    if isinstance(quality, dict):
        val = quality.get(canonical_name)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass

    return None
