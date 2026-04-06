"""Shared utilities for sector KPI extraction from XBRL facts."""

from __future__ import annotations


def extract_annual_values(
    gaap: dict,
    tag_candidates: list[str],
    years: int = 5,
) -> list[dict]:
    """Extract annual (10-K, FY) values for the first matching tag.

    Returns list of {date, fy, val} dicts sorted by date desc.
    """
    for tag in tag_candidates:
        if tag not in gaap:
            continue
        units = gaap[tag].get("units", {})
        if not units:
            continue
        unit_key = list(units.keys())[0]
        entries = units[unit_key]

        # Filter to 10-K FY entries
        fy_entries = [
            e for e in entries
            if e.get("form") == "10-K" and e.get("fp") == "FY"
        ]

        # Deduplicate by end date (keep latest filed)
        seen: dict[str, dict] = {}
        for e in fy_entries:
            end = e["end"]
            if end not in seen or e.get("filed", "") > seen[end].get("filed", ""):
                seen[end] = e

        result = sorted(seen.values(), key=lambda x: x["end"], reverse=True)
        if result:
            return [{"date": e["end"], "fy": e.get("fy"), "val": e["val"]} for e in result[:years]]

    return []


def safe_div(a: float | None, b: float | None) -> float | None:
    """Safe division."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def build_timeseries(
    gaap: dict,
    metrics: dict[str, list[str]],
    years: int = 5,
) -> dict[str, list[dict]]:
    """Build time series for multiple metrics.

    Args:
        gaap: us-gaap facts dict
        metrics: {metric_name: [tag_candidates]}
        years: number of years

    Returns: {metric_name: [{date, fy, val}]}
    """
    return {
        name: extract_annual_values(gaap, tags, years)
        for name, tags in metrics.items()
    }
