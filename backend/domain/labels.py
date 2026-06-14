"""Human labels and value formatting for internal identifiers.

The single place where metric/criterion ids become product language
("screen.roic_min: 0.45" -> "ROIC 45.0% (≥ 15%)"). Workflows and routes embed
the OUTPUT of these helpers in API payloads; the frontend never maps raw ids.

Pure functions over backend.core.metric_schema / backend.domain.metric_catalog
(the spine is read, never modified). Raw criterion ids and decimal values stay
in artifact payloads for audit — these helpers only add the display layer.
"""

from __future__ import annotations

from typing import Any

from backend.core.metric_schema import get_metric as _schema_metric

PRETTY_OPS = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=", "!=": "≠"}

# Compact display overrides where the catalog display name is too long for
# tables, chips and one-line summaries.
SHORT_LABELS = {
    "roic": "ROIC",
    "roe": "ROE",
    "roa": "ROA",
    "roce": "ROCE",
    "pe": "P/E",
    "pb": "P/B",
    "ps": "P/S",
    "peg": "PEG",
    "ev_ebitda": "EV/EBITDA",
    "ev_fcf": "EV/FCF",
    "pfcf": "P/FCF",
    "pffo": "P/FFO",
    "market_cap": "Market Cap",
    "expected_return": "Expected Return",
    "avg_dollar_volume_3m": "Avg $ Vol (3M)",
    "avg_volume_3m": "Avg Vol (3M)",
    "pct_below_52w_high": "Off 52W High",
    "volatility_90d": "Volatility",
}

# Stored as percent POINTS already (12.0 == 12%), never multiplied by 100.
PERCENT_POINT_METRICS = {
    "expected_return", "expected_return_pct", "discount_pct", "base_return",
    "bear_return", "upside_pct", "downside_pct", "discount_floor",
}

# Stored as 0-1 decimals but typed float in the schema (ratio-yield family).
DECIMAL_RATIO_METRICS = {"fcf_yield", "earnings_yield", "implied_growth", "growth_gap"}

_PERCENT_FAMILY_TOKENS = ("margin", "yield", "growth", "roic", "roe", "roa")

# Currency-denominated metrics (prices, statement line items, per-share).
DOLLAR_METRICS = {
    "avg_dollar_volume_3m",
    "price", "market_cap", "fair_value", "cost_basis", "market_value", "net_debt",
    "revenue", "gross_profit", "operating_income", "net_income", "ebitda", "eps",
    "free_cash_flow", "operating_cash_flow", "total_debt", "total_equity",
    "total_assets", "cash_and_equivalents", "depreciation_amortization", "sbc",
    "capex", "dividends_paid", "rd_expenses", "sga_expenses", "owner_earnings",
    "maintenance_capex", "growth_capex", "revenue_per_share", "fcf_per_share",
    "book_value_per_share", "tangible_book_per_share", "owner_earnings_per_share",
    "ffo_per_share",
}

# Multiples / coverage ratios rendered with an "x" suffix.
RATIO_X_METRICS = {
    "debt_equity", "net_debt_ebitda", "interest_coverage", "current_ratio",
    "fcf_conversion", "income_quality", "capex_to_ocf", "pe", "pb", "ps",
    "ev_ebitda", "ev_fcf", "pfcf", "peg", "ptangible_book", "pffo",
    "reserve_coverage", "gm_vs_sector", "roic_vs_sector", "growth_vs_sector",
    "ey_vs_sector",
}


def metric_label(metric_id: str | None) -> str:
    """Display name for a metric id ("roic" -> "ROIC", "gross_margin" ->
    "Gross Margin"); falls back to a title-cased id for unknown metrics."""
    if not metric_id:
        return ""
    d = _schema_metric(metric_id)
    canonical = d.canonical_name if d else str(metric_id)
    if canonical in SHORT_LABELS:
        return SHORT_LABELS[canonical]
    if d:
        return d.display_name
    return str(metric_id).split(".")[-1].replace("_", " ").title()


def _is_percent(metric_id: str | None, value: Any) -> bool:
    d = _schema_metric(metric_id) if metric_id else None
    canonical = d.canonical_name if d else (metric_id or "")
    if canonical in PERCENT_POINT_METRICS:
        return False
    if d and d.data_type == "percent":
        return True
    if canonical in DECIMAL_RATIO_METRICS:
        return True
    # Unknown/loosely-typed metric in a percent family with a clear 0-1 ratio.
    mid = str(canonical).lower()
    if any(tok in mid for tok in _PERCENT_FAMILY_TOKENS):
        return isinstance(value, (int, float)) and -1.0 <= value <= 1.0
    return False


def _dollars(value: float) -> str:
    sign = "-" if value < 0 else ""
    a = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= threshold:
            return f"{sign}${a / threshold:,.1f}{suffix}"
    return f"{sign}${a:,.2f}"


def _plain_number(value: float) -> str:
    if float(value).is_integer() and abs(value) < 1e6:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def format_metric_value(metric_id: str | None, value: Any) -> str:
    """Unit-aware human rendering of a stored metric value.

    Percent metrics (stored 0-1 decimals) -> "46.0%"; percent-point metrics
    (stored 12.0 == 12%) -> "12.0%"; dollars -> "$195.00" / "$2.1T";
    multiples -> "1.5x"; everything else with sensible precision.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    if not isinstance(value, (int, float)):
        return str(value)
    d = _schema_metric(metric_id) if metric_id else None
    canonical = d.canonical_name if d else (metric_id or "")
    if canonical in PERCENT_POINT_METRICS:
        return f"{value:,.1f}%"
    if _is_percent(metric_id, value):
        return f"{value * 100:,.1f}%"
    if canonical in DOLLAR_METRICS:
        return _dollars(float(value))
    if canonical in RATIO_X_METRICS:
        return f"{value:,.1f}x"
    if d and d.data_type == "int":
        return f"{value:,.0f}"
    return _plain_number(float(value))


def _compact(display: str) -> str:
    """Trim trailing '.0' in thresholds: '15.0%' -> '15%', '1.0x' -> '1x'."""
    for suffix in ("%", "x"):
        if display.endswith(suffix) and display[: -len(suffix)].endswith(".0"):
            return display[: -(len(suffix) + 2)] + suffix
    return display


def operator_display(operator: str | None) -> str:
    return PRETTY_OPS.get(operator or "", operator or "")


def threshold_display(metric_id: str | None, operator: str | None, value: Any) -> str:
    """Pretty operator + formatted threshold: (roic, '>=', 0.15) -> '≥ 15%'."""
    if operator == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = (_compact(format_metric_value(metric_id, v)) for v in value)
        return f"between {lo} and {hi}"
    if operator in ("in", "not_in") and isinstance(value, (list, tuple)):
        vals = ", ".join(str(v) for v in value)
        return ("one of " if operator == "in" else "not one of ") + vals
    return f"{operator_display(operator)} {_compact(format_metric_value(metric_id, value))}".strip()


def _criterion_dict(criterion: Any) -> dict:
    if hasattr(criterion, "to_dict"):
        return criterion.to_dict()
    return dict(criterion or {})


def describe_criterion(criterion: Any) -> str:
    """Human rule text for a Criterion (object or dict): 'ROIC ≥ 15%'."""
    d = _criterion_dict(criterion)
    metric = d.get("metric")
    label = metric_label(metric) if metric else metric_label(d.get("criterion_id"))
    return f"{label} {threshold_display(metric, d.get('operator'), d.get('value'))}".strip()


def describe_evaluation(criterion: Any, observed: Any, compact: bool = False) -> str:
    """Observed-vs-rule text: 'ROIC 45.0% (required ≥ 15%)'.

    compact=True drops the 'required' word: 'ROIC 45.0% (≥ 15%)'.
    """
    d = _criterion_dict(criterion)
    metric = d.get("metric")
    label = metric_label(metric) if metric else metric_label(d.get("criterion_id"))
    obs = "no data" if observed is None else format_metric_value(metric, observed)
    rule = threshold_display(metric, d.get("operator"), d.get("value"))
    prefix = "" if compact else "required "
    return f"{label} {obs} ({prefix}{rule})"


def _parse_legacy_threshold(metric_id: str | None, threshold: Any) -> str | None:
    """Stored evidence rows carry threshold as the raw string '>= 0.15';
    turn it back into '≥ 15%'. Unparseable values pass through as-is."""
    if threshold is None:
        return None
    if not isinstance(threshold, str):
        return threshold_display(metric_id, "==", threshold)
    parts = threshold.split(None, 1)
    if len(parts) == 2 and parts[0] in PRETTY_OPS:
        op, raw = parts
        try:
            return threshold_display(metric_id, op, float(raw))
        except ValueError:
            return f"{operator_display(op)} {raw}"
    return threshold


def evidence_key_number(row: dict) -> dict:
    """{label, value} pair for one stored evidence row, e.g.
    {"label": "ROIC", "value": "45.0% (≥ 15%)"}.

    Prefers the display fields newer artifacts carry; older payloads
    (criterion/metric/threshold/observed only) are humanized on the fly.
    """
    metric = row.get("metric")
    label = row.get("label") or (
        metric_label(metric) if metric else metric_label(row.get("criterion")))
    obs = row.get("observed_display")
    if not obs:
        raw = row.get("observed")
        obs = "no data" if raw is None else format_metric_value(metric, raw)
    thr = row.get("threshold_display") or _parse_legacy_threshold(metric, row.get("threshold"))
    return {"label": label, "value": obs + (f" ({thr})" if thr else "")}


def describe_evidence_row(row: dict) -> str:
    """One pass-evidence / fail-reason row -> 'ROIC 45.0% (≥ 15%)'."""
    kn = evidence_key_number(row)
    return f"{kn['label']} {kn['value']}".strip()


def top_ranking_component(components: list | None) -> str | None:
    """Display name of the strongest ranking component, by contribution then
    percentile. None when nothing was evaluable."""
    judged = [c for c in components or []
              if isinstance(c, dict)
              and isinstance(c.get("contribution") or c.get("percentile"), (int, float))]
    if not judged:
        return None
    best = max(judged, key=lambda c: (c.get("contribution") or 0.0,
                                      c.get("percentile") or 0.0))
    return best.get("label") or metric_label(best.get("metric"))


def screener_summary(pass_evidence: list | None, rank: int | None = None,
                     total: int | None = None, components: list | None = None) -> str:
    """Milestone/rendered_md summary for a passing screener result:
    'Passed 2 of 2 requirements — ROIC 45.0% (≥ 15%), Gross Margin 46.0%
    (≥ 40%). Ranked #1 of 5 on FCF Yield.'"""
    rows = [r for r in (pass_evidence or [])
            if isinstance(r, dict) and (r.get("metric") or r.get("criterion"))]
    if rows:
        reqs = ", ".join(describe_evidence_row(r) for r in rows)
        parts = [f"Passed {len(rows)} of {len(rows)} requirements — {reqs}."]
    else:
        parts = ["Passed screening with no hard requirements defined."]
    if rank:
        line = f"Ranked #{rank}" + (f" of {total}" if total else "")
        top = top_ranking_component(components)
        if top:
            line += f" on {top}"
        parts.append(line + ".")
    return " ".join(parts)


def screener_fail_summary(fail_reasons: list | None) -> str:
    """Milestone summary for a failed screener result, evidence-first."""
    rows = [r for r in (fail_reasons or [])
            if isinstance(r, dict) and (r.get("metric") or r.get("criterion"))]
    if not rows:
        return "Did not pass screening."
    reqs = ", ".join(describe_evidence_row(r) for r in rows)
    return f"Missed {len(rows)} requirement{'s' if len(rows) != 1 else ''} — {reqs}."


# --- kind / capability labels --------------------------------------------------------

KIND_LABELS = {
    "screen": "Screen",
    "rank": "Ranking factor",
    "ic_hurdle": "IC hurdle",
    "research_review": "Research-review criterion",
    "preference": "Preference",
}
CAPABILITY_LABELS = {
    "screener": "Screener",
    "thesis": "Thesis",
    "ic_review": "IC Review",
    "memo": "Memo",
    "portfolio_review": "Portfolio Review",
    "portfolio": "Portfolio",
    "company_page": "Company Page",
    "learning": "Learning / Evals",
}


def kind_label(kind: str | None) -> str:
    return KIND_LABELS.get(kind or "", (kind or "").replace("_", " ").capitalize())


def capability_label(capability: str | None) -> str:
    return CAPABILITY_LABELS.get(capability or "", (capability or "").replace("_", " ").title())


def describe_rule(criterion: Any) -> str:
    """Kind-aware human rule for chat/draft text: rank rules read 'Rank by FCF
    Yield' (the >0 sentinel is meaningless to a reader); gates read 'ROIC ≥ 15%'."""
    d = _criterion_dict(criterion)
    kind = d.get("kind")
    metric = d.get("metric")
    if kind == "rank":
        return f"Rank by {metric_label(metric) if metric else metric_label(d.get('criterion_id'))}"
    if kind in ("research_review", "preference") and not (d.get("operator") and d.get("value") is not None):
        return metric_label(metric) if metric else metric_label(d.get("criterion_id"))
    return describe_criterion(d)


# --- chat-output sanitizer (the deterministic safety net) ----------------------------

import re as _re

# All catalog metric ids -> display label, for whole-word substitution. Built
# lazily so import order stays clean.
_METRIC_LABEL_MAP: dict[str, str] | None = None


def _metric_label_map() -> dict[str, str]:
    global _METRIC_LABEL_MAP
    if _METRIC_LABEL_MAP is None:
        from backend.core.metric_schema import METRIC_SCHEMA
        out: dict[str, str] = {}
        for mid in METRIC_SCHEMA:
            # Only substitute unambiguous ids: snake_case (has '_') or known
            # finance acronyms in SHORT_LABELS. Single common-word ids are left
            # alone so ordinary prose is never mangled.
            if "_" in mid or mid in SHORT_LABELS:
                out[mid] = metric_label(mid)
        _METRIC_LABEL_MAP = out
    return _METRIC_LABEL_MAP


_KIND_TAG_RE = _re.compile(r"\[(screen|rank|ic_hurdle|research_review|preference)\]")
_CRITERION_ID_RE = _re.compile(
    r"\b(screen|rank|ic_hurdle|research_review|preference)\.([a-z0-9_]+)\b")
_CAPABILITY_LINE_RE = _re.compile(
    r"(?m)^(\s*(?:[-*]\s*)?)(" + "|".join(CAPABILITY_LABELS) + r")(\s*:)")
_OPERATOR_RE = _re.compile(r"(?<![<>=!])(>=|<=|!=)(?![<>=])")


def _humanize_criterion_id(match: "_re.Match") -> str:
    suffix = match.group(2)
    # Drop sentinel comparator suffixes so 'screen.roic_min' -> 'ROIC'.
    base = _re.sub(r"_(min|max|floor|cap|ceiling|target|threshold)$", "", suffix)
    label = metric_label(base)
    return label or suffix.replace("_", " ").title()


def humanize_chat_text(text: str | None) -> str:
    """Final deterministic pass over any chat reply: replace leaked internal
    tokens (kind tags, capability keys, criterion ids, raw metric ids, raw
    comparison operators) with product language. Conservative — it only rewrites
    well-defined internal patterns, never free prose, so deterministic composers
    and model output both stay clean (the verifier the user asked for)."""
    if not text:
        return text or ""
    out = _CRITERION_ID_RE.sub(_humanize_criterion_id, text)
    out = _KIND_TAG_RE.sub(lambda m: kind_label(m.group(1)), out)
    out = _CAPABILITY_LINE_RE.sub(
        lambda m: f"{m.group(1)}{capability_label(m.group(2))}{m.group(3)}", out)
    label_map = _metric_label_map()
    if label_map:
        ids = sorted(label_map, key=len, reverse=True)  # longest first
        metric_re = _re.compile(r"\b(" + "|".join(_re.escape(i) for i in ids) + r")\b")
        out = metric_re.sub(lambda m: label_map[m.group(1)], out)
    out = _OPERATOR_RE.sub(lambda m: PRETTY_OPS[m.group(1)], out)
    return out
