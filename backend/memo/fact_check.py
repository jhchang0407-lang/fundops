"""Deterministic fact-checking for memo sections.

Extracts numeric claims from prose, cross-checks against known financial data,
and detects cross-section inconsistencies.

Adapted from backend/memo/writers.py fact_check_section() and
cross_section_coherence_check() — extracted to avoid old pipeline import deps.

Usage:
    from backend.memo.fact_check import fact_check_section, cross_section_coherence_check

    violations = fact_check_section(section_text, fact_sheet)
    warnings = cross_section_coherence_check({"S2": text2, "S3": text3})
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

log = logging.getLogger("fundops.memo.fact_check")

# ─────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────

_NUMBER_PATTERN = re.compile(
    r"(?<!\w)"               # not preceded by a word char
    r"\$?"                   # optional dollar sign
    r"(\d[\d,]*\.?\d*)"     # digits with optional commas and decimal
    r"\s*"                   # optional whitespace
    r"(%|[BbMm]\b)?"        # optional percent or B/M suffix
    r"(?!\w)"               # not followed by a word char
)

# ─────────────────────────────────────────────────────────────
# Keyword → metric key mapping
# ─────────────────────────────────────────────────────────────

_KEYWORD_MAP: dict[str, list[str]] = {
    "revenue":       ["revenue"],
    "gross margin":  ["gross_margin", "grossProfitRatio", "grossMargin"],
    "gross profit":  ["gross_profit", "grossProfit"],
    "operating margin": ["operating_margin", "operatingIncomeRatio", "operatingMargin"],
    "ebitda margin": ["ebitda_margin"],
    "ebitda":        ["ebitda"],
    "net margin":    ["net_margin", "net_profit_margin", "netIncomeRatio", "netProfitMargin"],
    "roic":          ["roic"],
    "roe":           ["roe", "return_on_equity", "returnOnEquity"],
    "roa":           ["roa", "return_on_assets", "returnOnAssets"],
    "growth":        ["growth"],
    "eps":           ["eps", "epsDiluted"],
    "fcf":           ["fcf", "free_cash_flow", "freeCashFlow"],
    "free cash flow": ["fcf", "free_cash_flow", "freeCashFlow"],
    "dividend":      ["dividend"],
    "capex":         ["capex", "capitalExpenditure"],
    "debt":          ["debt", "totalDebt"],
    "interest":      ["interest", "interestExpense"],
    "shares":        ["shares", "share_count", "weightedAverageShsOutDil"],
    "market cap":    ["market_cap", "marketCap"],
    "ev":            ["ev_to", "enterprise_value"],
    "p/e":           ["price_to_earnings", "peRatio"],
    "price to earnings": ["price_to_earnings", "peRatio"],
    "net income":    ["netIncome", "net_income"],
    "operating income": ["operatingIncome", "operating_income"],
    "aum":           ["aum", "assets_under_management"],
    "price":         ["price"],
    "beta":          ["beta"],
}


# ─────────────────────────────────────────────────────────────
# Flatten any dict into {dotted_key: numeric_value}
# ─────────────────────────────────────────────────────────────

def _flatten(d: Any, prefix: str = "") -> dict[str, float]:
    """Recursively flatten a dict into {dotted_key: numeric_value}."""
    result: dict[str, float] = {}
    if d is None:
        return result
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{prefix}.{k}" if prefix else str(k)
            result.update(_flatten(v, new_key))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            result.update(_flatten(v, f"{prefix}[{i}]"))
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        if not math.isnan(d) and not math.isinf(d):
            result[prefix] = float(d)
    return result


def _parse_number(raw: str, suffix: str | None) -> tuple[float | None, bool]:
    """Parse a captured number string into (value, is_percentage)."""
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None, False

    is_pct = suffix == "%"
    if suffix and suffix.upper() == "B":
        value *= 1_000_000_000
    elif suffix and suffix.upper() == "M":
        value *= 1_000_000
    return value, is_pct


def _extract_context(text: str, start: int, end: int, window: int = 10) -> str:
    """Return up to window words on each side of the match."""
    before = text[:start].split()[-window:]
    after = text[end:].split()[:window]
    return " ".join(before + after).lower()


def _find_matching_metric(
    context: str,
    value: float,
    is_pct: bool,
    flat_facts: dict[str, float],
) -> tuple[str, float] | None:
    """Find the best matching metric for a prose number."""
    matched_fragments: list[str] = []
    for keyword, fragments in _KEYWORD_MAP.items():
        if keyword in context:
            matched_fragments.extend(fragments)

    if not matched_fragments:
        return None

    candidates: list[tuple[str, float]] = []
    for key, fact_value in flat_facts.items():
        key_lower = key.lower()
        for frag in matched_fragments:
            if frag.lower() in key_lower:
                candidates.append((key, fact_value))
                break

    if not candidates:
        return None

    best: tuple[str, float, float] | None = None

    for key, fact_value in candidates:
        if fact_value == 0:
            continue
        dev = abs(value - fact_value) / abs(fact_value)

        # If prose is a percentage, also try fact_value * 100 (decimal → pct)
        if is_pct and abs(fact_value) < 1.0:
            alt_dev = abs(value - fact_value * 100) / abs(fact_value * 100)
            if alt_dev < dev:
                dev = alt_dev
                fact_value = fact_value * 100

        if best is None or dev < best[2]:
            best = (key, fact_value, dev)

    if best is None:
        return None
    if best[2] <= 2.0:
        return (best[0], best[1])
    return None


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def fact_check_section(
    section_text: str,
    fact_sheet: dict,
    tolerance: float = 0.05,
) -> list[str]:
    """Extract all numbers from prose, cross-check against fact_sheet.

    Args:
        section_text: The prose text of one memo section.
        fact_sheet: Any dict structure — gets flattened recursively.
            Can be built from FinancialData: {financials_annual, market_data, ratios, ...}
        tolerance: Maximum allowed fractional deviation (default 5%).

    Returns:
        List of violation messages. Empty list means all checks passed.
    """
    if not section_text or not fact_sheet:
        return []

    flat_facts = _flatten(fact_sheet)
    if not flat_facts:
        return []

    violations: list[str] = []

    for match in _NUMBER_PATTERN.finditer(section_text):
        raw_num = match.group(1)
        suffix = match.group(2)
        value, is_pct = _parse_number(raw_num, suffix)
        if value is None:
            continue

        # Skip year-like numbers
        if not suffix and 1900 <= value <= 2099 and value == int(value):
            continue

        context = _extract_context(section_text, match.start(), match.end())
        result = _find_matching_metric(context, value, is_pct, flat_facts)
        if result is None:
            continue

        metric_key, actual_value = result
        if actual_value == 0:
            continue
        deviation = abs(value - actual_value) / abs(actual_value)

        if deviation > tolerance:
            snippet_start = max(0, match.start() - 30)
            snippet_end = min(len(section_text), match.end() + 30)
            snippet = section_text[snippet_start:snippet_end].replace("\n", " ").strip()
            msg = (
                f"Prose says '{snippet}' ({value}) but data shows "
                f"{metric_key}: {actual_value} ({deviation:.1%} deviation)"
            )
            violations.append(msg)
            log.warning("Fact-check violation: %s", msg)

    return violations


def cross_section_coherence_check(sections: dict[str, str]) -> list[str]:
    """Verify that the same metric has the same value across all sections.

    Args:
        sections: Dict mapping section name to its prose text.

    Returns:
        List of warning messages for cross-section inconsistencies.
    """
    if not sections or len(sections) < 2:
        return []

    section_metrics: dict[str, dict[str, list[float]]] = {}

    for section_name, text in sections.items():
        if not text:
            continue
        metrics: dict[str, list[float]] = {}
        for match in _NUMBER_PATTERN.finditer(text):
            raw_num = match.group(1)
            suffix = match.group(2)
            value, is_pct = _parse_number(raw_num, suffix)
            if value is None:
                continue
            context = _extract_context(text, match.start(), match.end())
            for keyword in _KEYWORD_MAP:
                if keyword in context:
                    key = keyword + ("_pct" if is_pct else "")
                    metrics.setdefault(key, []).append(value)
        section_metrics[section_name] = metrics

    warnings: list[str] = []
    all_keys: set[str] = set()
    for m in section_metrics.values():
        all_keys.update(m.keys())

    for metric_key in sorted(all_keys):
        appearances: list[tuple[str, float]] = []
        for section_name, metrics in section_metrics.items():
            for v in metrics.get(metric_key, []):
                appearances.append((section_name, v))
        if len(appearances) < 2:
            continue
        seen: set[tuple[str, str]] = set()
        for i, (sec_a, val_a) in enumerate(appearances):
            for j, (sec_b, val_b) in enumerate(appearances):
                if i >= j or sec_a == sec_b:
                    continue
                pair = (min(sec_a, sec_b), max(sec_a, sec_b))
                if pair in seen:
                    continue
                if val_a != val_b:
                    display = metric_key.replace("_pct", "").replace("_", " ")
                    sfx = "%" if metric_key.endswith("_pct") else ""
                    msg = f"Inconsistency: '{display}' is {val_a}{sfx} in {sec_a} but {val_b}{sfx} in {sec_b}"
                    warnings.append(msg)
                    seen.add(pair)
                    log.warning("Cross-section: %s", msg)

    return warnings
