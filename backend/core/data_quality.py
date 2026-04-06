"""Data quality monitoring — completeness, anomaly detection, staleness.

Checks financial data for missing fields, outlier values, and stale dates.
Returns a quality score (0-100) with categorized issues.
"""

import logging
from typing import Any

from backend.core.utils import safe_float, check_data_freshness

log = logging.getLogger("fundops.data_quality")

# Core metrics that should always be present for a valid analysis
_CORE_METRICS = [
    "revenue", "gross_margin", "roic", "pe", "fcf_yield", "debt_equity",
]

# Extended metrics (nice to have)
_EXTENDED_METRICS = [
    "roe", "operating_margin", "revenue_growth", "price",
    "market_cap", "sector", "industry",
]

# Typical ranges for anomaly detection (metric: (min, max))
_ANOMALY_RANGES = {
    "gross_margin": (-0.5, 1.0),
    "operating_margin": (-2.0, 0.8),
    "roic": (-1.0, 1.0),
    "roe": (-2.0, 2.0),
    "pe": (-500, 500),
    "debt_equity": (-5, 50),
    "fcf_yield": (-1.0, 1.0),
    "revenue_growth": (-1.0, 10.0),
    "dividend_yield": (0, 0.30),
}


def audit_data_quality(
    data: dict,
    ticker: str = "",
) -> dict:
    """Audit financial data quality.

    Returns:
        {
            "quality_score": int (0-100),
            "issues": list[str],
            "missing_fields": list[str],
            "anomalies": list[str],
            "freshness": dict,
        }
    """
    issues: list[str] = []
    missing_fields: list[str] = []
    anomalies: list[str] = []

    # Flatten nested dicts so we can find metrics stored under 'quality', 'valuation', etc.
    flat = dict(data)
    for nested_key in ("quality", "valuation", "return_sources", "financials"):
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                if k not in flat or flat[k] is None:
                    flat[k] = v

    # --- Completeness check ---
    core_present = 0
    for metric in _CORE_METRICS:
        val = flat.get(metric)
        if val is None:
            missing_fields.append(metric)
        else:
            core_present += 1

    extended_present = 0
    for metric in _EXTENDED_METRICS:
        val = flat.get(metric)
        if val is not None:
            extended_present += 1

    completeness_score = (core_present / len(_CORE_METRICS)) * 70
    completeness_score += (extended_present / len(_EXTENDED_METRICS)) * 30

    if missing_fields:
        issues.append(f"Missing {len(missing_fields)} core metrics: {', '.join(missing_fields)}")

    # --- Anomaly detection ---
    for metric, (lo, hi) in _ANOMALY_RANGES.items():
        val = flat.get(metric)
        if val is None:
            continue
        try:
            fval = float(val)
            if fval < lo or fval > hi:
                anomalies.append(
                    f"{metric}={fval:.3f} outside expected range ({lo}, {hi})"
                )
        except (ValueError, TypeError):
            pass

    anomaly_penalty = min(len(anomalies) * 5, 20)  # Max 20 point penalty

    # --- Freshness check ---
    # Prefer thesis-computed freshness (has filing dates from SEC), fall back to recomputing
    freshness = data.get("data_freshness") or flat.get("data_freshness") or check_data_freshness(flat)
    if isinstance(freshness, str):
        freshness = {"fresh": True, "age_days": None, "warning": None}
    freshness_penalty = 0
    if freshness.get("fresh") is False:
        freshness_penalty = 15
        issues.append(freshness.get("warning") or "Data may be stale")

    # --- Provider disagreement (if both sources present) ---
    # Check if SEC and FMP data are both present and diverge
    sec_rev = data.get("sec_revenue")
    fmp_rev = data.get("fmp_revenue") or data.get("revenue")
    if sec_rev and fmp_rev:
        try:
            sec_f = float(sec_rev)
            fmp_f = float(fmp_rev)
            if sec_f > 0 and abs(sec_f - fmp_f) / sec_f > 0.10:
                issues.append(
                    f"Provider disagreement: SEC revenue ${sec_f:,.0f} vs "
                    f"FMP ${fmp_f:,.0f} ({abs(sec_f - fmp_f)/sec_f*100:.1f}% divergence)"
                )
        except (ValueError, TypeError):
            pass

    # --- Final score ---
    quality_score = max(0, min(100, int(completeness_score - anomaly_penalty - freshness_penalty)))

    if quality_score < 50:
        log.warning(f"[{ticker}] Low data quality: {quality_score}/100")

    return {
        "quality_score": quality_score,
        "issues": issues,
        "missing_fields": missing_fields,
        "anomalies": anomalies,
        "freshness": freshness,
    }
