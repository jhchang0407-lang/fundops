"""Company Page statement assembly (ADR-0042/0043, ISSUE-014/016/017).

Turns the flat per-period observations from ``FinancialStore.periods()`` into
standardized Income / Balance / Cash Flow sections: one normalized column per
fiscal year (annual) or fiscal quarter (quarterly), canonical row order, and
mostly-blank stub columns suppressed. Market technicals are already excluded
upstream by ``periods()``; anything not catalogued as a statement line is a
derived ratio and stays out of the statement sections (shown in the snapshot /
peers instead). Pure functions — no store or I/O — so they unit-test directly.
"""

from __future__ import annotations

import math

from backend.domain.metric_catalog import (
    STATEMENT_SECTIONS,
    statement_order,
    statement_section,
)

# Thinness is RELATIVE to each statement's own density: a column is a stub only
# if it carries fewer than this fraction of the fullest column in that section.
# This drops mostly-blank partial-filing columns (ISSUE-016) WITHOUT hiding a
# statement that is uniformly sparse but real — e.g. a REIT whose only mapped
# cash-flow line is operating cash flow should still show that one line, not a
# blank "no data" tab.
SECTION_DENSITY_FRACTION = 0.34


def _fiscal_key(period_end: str, period_type: str) -> str:
    """Group key collapsing period_ends that belong to the same fiscal year
    (annual) or calendar quarter (quarterly)."""
    year = period_end[:4]
    if period_type == "annual":
        return year
    try:
        month = int(period_end[5:7])
    except (ValueError, IndexError):
        return period_end
    quarter = (max(1, min(12, month)) - 1) // 3 + 1
    return f"{year}-Q{quarter}"


def normalize_periods(period_list: list[dict], period_type: str) -> list[dict]:
    """Collapse multiple period_ends in the same fiscal year/quarter into one
    column (ISSUE-014). ``period_list`` is newest-first, so the first period
    seen in a fiscal group supplies the canonical period_end and each metric's
    freshest value; older period_ends only backfill metrics the newer column is
    missing. Returns columns newest-first."""
    groups: dict[str, dict] = {}
    order: list[str] = []
    for p in period_list:
        key = _fiscal_key(p["period_end"], period_type)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"period_end": p["period_end"], "metrics": {}}
            order.append(key)
        for metric, value in p["metrics"].items():
            if value is not None and metric not in g["metrics"]:
                g["metrics"][metric] = value
    cols = [groups[k] for k in order]
    cols.sort(key=lambda c: c["period_end"], reverse=True)
    return cols


def sectioned(period_list: list[dict], period_type: str) -> dict[str, list[dict]]:
    """Normalized statement sections keyed income | balance | cashflow. Each
    column carries only that section's metrics in canonical row order; columns
    that are stubs *relative to the section's fullest column* are suppressed,
    while uniformly-sparse-but-real statements are kept (ISSUE-016)."""
    normalized = normalize_periods(period_list, period_type)
    # Bucket each column's metrics per section first, so the suppression floor
    # can be set from the section's own peak density.
    per_section: dict[str, list[tuple[str, dict]]] = {s: [] for s in STATEMENT_SECTIONS}
    for col in normalized:
        for section in STATEMENT_SECTIONS:
            metrics = {m: v for m, v in col["metrics"].items()
                       if statement_section(m) == section}
            if metrics:
                per_section[section].append((col["period_end"], metrics))
    out: dict[str, list[dict]] = {s: [] for s in STATEMENT_SECTIONS}
    for section, cols in per_section.items():
        if not cols:
            continue
        section_max = max(len(m) for _, m in cols)
        floor = max(1, math.ceil(SECTION_DENSITY_FRACTION * section_max))
        for period_end, metrics in cols:
            if len(metrics) < floor:
                continue  # stub column relative to this statement's density
            ordered = dict(sorted(metrics.items(),
                                  key=lambda kv: (statement_order(kv[0]), kv[0])))
            out[section].append({"period_end": period_end, "metrics": ordered})
    return out


def statement_columns(period_list: list[dict], period_type: str) -> list[dict]:
    """Flat normalized columns (one per fiscal period, orphan/near-blank columns
    dropped, market metrics excluded upstream, metrics in canonical order) — for
    the CSV export and chat, which render a single metric×period matrix rather
    than the three sectioned tabs. Keeps ALL non-market metrics per column
    (statement lines AND derived ratios), but drops a column whose total metric
    count is a stub relative to the fullest column — the same density rule that
    de-clutters the Company Page, so exports no longer leak the orphan columns
    (fiscal-basis migrations, single-metric legacy period_ends) the raw store
    produced."""
    normalized = normalize_periods(period_list, period_type)
    if not normalized:
        return []
    max_metrics = max(len(c["metrics"]) for c in normalized)
    floor = max(1, math.ceil(SECTION_DENSITY_FRACTION * max_metrics))
    out = []
    for col in normalized:
        if len(col["metrics"]) < floor:
            continue
        out.append({
            "period_end": col["period_end"],
            "metrics": dict(sorted(col["metrics"].items(),
                                   key=lambda kv: (statement_order(kv[0]), kv[0]))),
        })
    return out
