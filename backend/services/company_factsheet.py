"""Shared company fact-sheet projection.

The normalized workspace tables remain canonical. This module builds disposable
read models for Company Page, chat/research packets, and quality dashboards:
latest metrics enriched with read-time valuation fields, statement sections,
source/version metadata, and compact data-quality findings.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from hashlib import sha256

from backend.domain import metric_catalog, statements
from backend.domain.derive import derive_price_metrics
from backend.domain.metric_catalog import CATALOG_VERSION, MAPPING_VERSION

SNAPSHOT_METRICS = (
    "market_cap", "pe", "revenue_growth", "gross_margin",
    "operating_margin", "fcf_yield", "roic", "debt_equity",
)

KEY_HISTORY_METRICS = (
    "revenue", "gross_margin", "operating_margin", "net_margin",
    "free_cash_flow", "eps", "roic", "debt_equity",
)
ANNUAL_PERIODS = 5
QUARTERLY_PERIODS = 8
PRICE_STALE_DAYS = 7

BASE_REQUIRED_METRICS = (
    "revenue", "gross_margin", "operating_margin", "free_cash_flow",
    "shares_outstanding", "debt_equity",
)
SECTOR_REQUIRED_METRICS = {
    "banks": ("roe", "net_margin", "debt_equity"),
    "reits": ("ffo_per_share", "debt_equity", "interest_coverage"),
    "insurance": ("combined_ratio", "roe", "book_value_per_share"),
    "software": ("revenue_growth", "rule_of_40", "sbc_to_revenue", "fcf_margin"),
}

READ_TIME_FORMULAS = {
    "market_cap": "price * shares_outstanding",
    "pe": "price / eps",
    "fcf_yield": "free_cash_flow / market_cap",
    "earnings_yield": "net_income / market_cap",
    "revenue_growth": "latest quarterly YoY revenue growth, else annual revenue CAGR",
}


def build_company_fact_sheet(
    stores, ticker: str, profile: str = "company_page",
    entity_id: str | None = None, ensure: bool = False,
) -> dict:
    """Build a deterministic company read model from retained workspace truth."""
    ticker = ticker.upper()
    ent = stores.identity.resolve_ticker(ticker)
    if ent is None and ensure:
        ent = stores.identity.ensure_entity(ticker)
    if ent is None:
        raise ValueError(f"unknown ticker {ticker}")
    entity_id = entity_id or ent["id"]

    price_context = build_price_context(stores, ticker, stores.financial.latest(entity_id))
    latest = dict(stores.financial.latest(entity_id))
    notes: list[str] = []
    history = build_history(stores, entity_id)
    trends = build_trends(history)
    enrich_valuation_metrics(latest, price_context.get("price"), trends, notes)
    price_context["market_cap"] = latest.get("market_cap")

    basis = stores.financial.latest_basis(entity_id)
    latest_price = _latest_price_basis(stores, ticker)
    snapshot = {m: latest.get(m) for m in SNAPSHOT_METRICS}
    snapshot_basis = _snapshot_basis(basis, latest, latest_price)
    annual = _periods(stores, entity_id, "annual")
    quarterly = _periods(stores, entity_id, "quarterly")
    coverage = _coverage(snapshot, annual, quarterly)
    quality = _data_quality(stores, ent, latest, basis, latest_price, coverage, notes)
    source_metadata = _source_metadata(
        ticker, latest, basis, latest_price, stores.bulk.filings_for(ticker, limit=1),
        quality,
    )
    source_drilldowns = _source_drilldowns(stores, entity_id, latest, snapshot_basis, latest_price)

    return {
        "profile": profile,
        "identity": {
            "ticker": ticker,
            "name": ent.get("name") or ticker,
            "sector": ent.get("sector"),
            "industry": ent.get("industry"),
            "entity_id": entity_id,
            "cik": ent.get("cik"),
            "sic": ent.get("sic"),
        },
        "latest": latest,
        "snapshot": snapshot,
        "snapshot_basis": snapshot_basis,
        "history": history,
        "trends": trends,
        "price_context": price_context,
        "annual": annual,
        "quarterly": quarterly,
        "coverage": coverage,
        "data_quality": quality,
        "data_quality_notes": quality["notes"],
        "source_metadata": source_metadata,
        "source_drilldowns": source_drilldowns,
    }


def enriched_snapshot(stores, entity_id: str, price: float | None,
                      latest: dict | None = None) -> dict:
    """Latest financials with read-time growth/valuation metrics filled in."""
    latest = dict(latest if latest is not None else stores.financial.latest(entity_id))
    if latest:
        trends = build_trends(build_history(stores, entity_id))
        enrich_valuation_metrics(latest, price, trends, notes=[])
    return latest


def build_history(stores, entity_id: str) -> dict:
    """Per-metric observation series, newest first."""
    out: dict[str, dict] = {}
    for period_type, cap in (("annual", ANNUAL_PERIODS), ("quarterly", QUARTERLY_PERIODS)):
        for o in stores.financial.observations(entity_id, period_type=period_type, limit=400):
            if o["metric"] not in KEY_HISTORY_METRICS or o["value"] is None:
                continue
            series = out.setdefault(o["metric"], {}).setdefault(period_type, [])
            if len(series) < cap:
                series.append({"period_end": o["period_end"], "value": o["value"]})
    return out


def build_trends(history: dict) -> dict:
    trends: dict = {}
    rev_annual = (history.get("revenue") or {}).get("annual") or []
    cagr = _cagr(rev_annual)
    if cagr is not None:
        trends["revenue_cagr_pct"] = round(cagr, 1)
        trends["revenue_cagr_years"] = len(rev_annual) - 1
    for metric in ("gross_margin", "operating_margin", "net_margin"):
        traj = _trajectory((history.get(metric) or {}).get("annual") or [])
        if traj:
            trends[f"{metric}_trajectory"] = traj
    qrev = (history.get("revenue") or {}).get("quarterly") or []
    if len(qrev) >= 5 and isinstance(qrev[4]["value"], (int, float)) and qrev[4]["value"]:
        trends["latest_quarter_revenue_yoy_pct"] = round(
            (qrev[0]["value"] / qrev[4]["value"] - 1) * 100, 1)
    return trends


def build_price_context(stores, ticker: str, latest: dict | None = None) -> dict:
    latest = latest or {}
    price_mark = stores.portfolio.prices().get(ticker)
    close = stores.bulk.latest_close(ticker)
    price = price_mark if price_mark is not None else (close["close"] if close else latest.get("price"))
    ctx: dict = {"price": price, "market_cap": latest.get("market_cap")}
    rows = stores.bulk.price_range(ticker)[-252:]
    closes = [r["close"] for r in rows if isinstance(r.get("close"), (int, float))]
    if closes:
        hi, lo = max(closes), min(closes)
        ctx["high_52w"], ctx["low_52w"] = round(hi, 2), round(lo, 2)
        if price and hi:
            ctx["pct_off_52w_high"] = round((price / hi - 1) * 100, 1)
    return ctx


def enrich_valuation_metrics(latest: dict, price: float | None,
                             trends: dict, notes: list[str]) -> None:
    """Fill price-dependent and growth metrics in-place, never overwriting."""
    def _f(key):
        v = latest.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    derive_price_metrics(latest, price)
    revenue = _f("revenue")
    if latest.get("revenue_growth") is None:
        yoy = trends.get("latest_quarter_revenue_yoy_pct")
        cagr = trends.get("revenue_cagr_pct")
        growth_pct = yoy if isinstance(yoy, (int, float)) else cagr
        if isinstance(growth_pct, (int, float)):
            latest["revenue_growth"] = growth_pct / 100.0
        elif revenue is not None:
            notes.append("revenue growth unavailable (need 2+ retained periods)")

    for key in ("roic", "roe"):
        v = _f(key)
        if v is not None and abs(v) > 1.5:
            notes.append(
                f"{key} {v * 100:.0f}% reflects an unusually small denominator "
                "(likely low book equity); treat as unreliable")


def data_quality_dashboard(stores, limit: int = 50) -> dict:
    """Unified local data-quality dashboard projection across active entities."""
    rows = []
    counts = {
        "entities": 0, "with_issues": 0, "missing_metrics": 0, "stale_metrics": 0,
        "unmapped_tags": 0, "stale_prices": 0, "failed_runs": 0,
    }
    for ticker in stores.identity.all_tickers()[:limit]:
        try:
            sheet = build_company_fact_sheet(stores, ticker, profile="quality_dashboard")
        except ValueError:
            continue
        q = sheet["data_quality"]
        counts["entities"] += 1
        counts["missing_metrics"] += len(q["missing_metrics"])
        counts["stale_metrics"] += len(q["stale_metrics"])
        counts["unmapped_tags"] += q["mapping_gaps"]["counts"].get("unmapped", 0)
        counts["stale_prices"] += 1 if q.get("price_stale") else 0
        counts["failed_runs"] += len(q["failed_runs"])
        if q["issues"]:
            counts["with_issues"] += 1
            rows.append({
                "ticker": ticker,
                "name": sheet["identity"]["name"],
                "sector": sheet["identity"].get("sector"),
                "latest_filing_period": sheet["source_metadata"].get("latest_filing_period"),
                "latest_price_date": sheet["source_metadata"].get("latest_price_date"),
                "issues": q["issues"][:8],
                "missing_metrics": q["missing_metrics"],
                "stale_metrics": q["stale_metrics"],
                "unmapped_tag_count": q["mapping_gaps"]["counts"].get("unmapped", 0),
            })
    rows.sort(key=lambda r: len(r["issues"]), reverse=True)
    return {"counts": counts, "rows": rows}


def _periods(stores, entity_id: str, period_type: str) -> dict:
    raw = stores.financial.periods(entity_id, period_type)
    block = {"periods": statements.normalize_periods(raw, period_type)}
    block.update(statements.sectioned(raw, period_type))
    return block


def _coverage(snapshot: dict, annual: dict, quarterly: dict) -> dict:
    sections: dict[str, dict] = {}
    for sec in ("income", "balance", "cashflow"):
        cols = (annual.get(sec) or []) + (quarterly.get(sec) or [])
        metrics = {m for c in cols for m in c["metrics"]}
        sections[sec] = {"available": bool(cols), "metric_count": len(metrics)}
    snap = {m: ("present" if snapshot.get(m) is not None else "missing")
            for m in SNAPSHOT_METRICS}
    notes: list[str] = []
    if not any(s["available"] for s in sections.values()):
        notes.append("No financial statements have been retained for this company yet — "
                     "it may be newly added, delisted, or awaiting its first data sync.")
    elif sections["cashflow"]["available"] and sections["cashflow"]["metric_count"] <= 1:
        notes.append("Cash-flow detail is limited for this filer; capex and free cash "
                     "flow are not fully mapped yet.")
    return {"sections": sections, "snapshot": snap, "notes": notes}


def _data_quality(stores, ent: dict, latest: dict, basis: dict, latest_price: dict,
                  coverage: dict, notes: list[str]) -> dict:
    ticker = stores.identity.current_ticker(ent["id"]) or ""
    required = _required_metrics(ent)
    missing = [m for m in required if latest.get(m) is None]
    stale = [m for m, b in basis.items() if b.get("stale")]
    mapping_gaps = stores.financial.mapping_gap_summary(ent["id"])
    suspicious = _suspicious_values(latest)
    failed_runs = _failed_runs(stores, ticker)
    price_stale = _price_stale(latest_price.get("latest_price_date"))
    issues: list[dict] = []
    for m in missing:
        issues.append({"kind": "missing_metric", "metric": m, "severity": "medium"})
    for m in stale:
        issues.append({"kind": "stale_metric", "metric": m, "severity": "medium",
                       "period_end": basis[m].get("period_end")})
    if mapping_gaps["counts"].get("unmapped"):
        issues.append({"kind": "unmapped_tags", "severity": "low",
                       "count": mapping_gaps["counts"]["unmapped"]})
    if mapping_gaps["counts"].get("rejected"):
        issues.append({"kind": "rejected_mappings", "severity": "low",
                       "count": mapping_gaps["counts"]["rejected"]})
    for s in suspicious:
        issues.append({"kind": "suspicious_value", "severity": "medium", **s})
    if price_stale:
        issues.append({"kind": "stale_price", "severity": "medium",
                       "latest_price_date": latest_price.get("latest_price_date")})
    for r in failed_runs:
        issues.append({"kind": "failed_run", "severity": "high",
                       "run_id": r.get("run_id"), "stage": r.get("name")})
    quality_notes = list(dict.fromkeys(coverage["notes"] + notes + [
        f"{len(missing)} required metric(s) missing for this sector/profile."
        if missing else "",
        "Latest price is stale." if price_stale else "",
    ]))
    quality_notes = [n for n in quality_notes if n]
    return {
        "required_metrics": list(required),
        "missing_metrics": missing,
        "stale_metrics": stale,
        "mapping_gaps": mapping_gaps,
        "suspicious_values": suspicious,
        "price_stale": price_stale,
        "failed_runs": failed_runs,
        "issues": issues,
        "notes": quality_notes,
    }


def _required_metrics(ent: dict) -> tuple[str, ...]:
    kind = _sector_kind(ent)
    return tuple(dict.fromkeys(BASE_REQUIRED_METRICS + SECTOR_REQUIRED_METRICS.get(kind, ())))


def _sector_kind(ent: dict) -> str:
    text = " ".join(str(ent.get(k) or "") for k in ("sector", "industry")).lower()
    if "bank" in text or "financial service" in text:
        return "banks"
    if "reit" in text or "real estate investment" in text:
        return "reits"
    if "insurance" in text:
        return "insurance"
    if "software" in text or "saas" in text:
        return "software"
    return "default"


def _suspicious_values(latest: dict) -> list[dict]:
    out = []
    for metric, value in latest.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        m = metric_catalog.get_metric(metric)
        if not m:
            continue
        lo, hi = m.typical_range
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            if value < lo or value > hi:
                out.append({"metric": metric, "value": value, "typical_range": [lo, hi]})
    return out[:12]


def _failed_runs(stores, ticker: str) -> list[dict]:
    if not ticker:
        return []
    rows = stores.ws.query(
        "SELECT run_id, name, item_ref, error, finished_at FROM workflow_steps "
        "WHERE item_ref = ? AND status = 'failed' ORDER BY finished_at DESC LIMIT 5",
        (ticker.upper(),),
    )
    return [dict(r) for r in rows]


def _latest_price_basis(stores, ticker: str) -> dict:
    close = stores.bulk.latest_close(ticker)
    mark = stores.ws.query_one(
        "SELECT price, as_of FROM price_marks WHERE ticker = ?", (ticker.upper(),))
    return {
        "latest_price": close["close"] if close else (mark["price"] if mark else None),
        "latest_price_date": close["date"] if close else (str(mark["as_of"])[:10] if mark else None),
        "price_source": "price_history" if close else ("price_mark" if mark else None),
    }


def _price_stale(latest_price_date: str | None) -> bool:
    if not latest_price_date:
        return True
    try:
        return (datetime.now(timezone.utc).date()
                - date.fromisoformat(str(latest_price_date)[:10])).days > PRICE_STALE_DAYS
    except ValueError:
        return False


def _snapshot_basis(basis: dict, latest: dict, latest_price: dict) -> dict:
    out = {m: basis.get(m) for m in SNAPSHOT_METRICS}
    for metric in SNAPSHOT_METRICS:
        if out.get(metric) or latest.get(metric) is None:
            continue
        if metric in READ_TIME_FORMULAS:
            out[metric] = {
                "period_end": _derived_period(metric, basis, latest_price),
                "period_type": "projection",
                "stale": metric != "revenue_growth" and _price_stale(latest_price.get("latest_price_date")),
                "source": "read_time_projection",
            }
    return out


def _derived_period(metric: str, basis: dict, latest_price: dict) -> str | None:
    if metric in ("market_cap", "pe", "fcf_yield", "earnings_yield"):
        return latest_price.get("latest_price_date") or _max_period(basis)
    return _max_period(basis)


def _source_metadata(ticker: str, latest: dict, basis: dict, latest_price: dict,
                     filings: list[dict], quality: dict) -> dict:
    latest_filing = filings[0] if filings else None
    latest_period = _max_period(basis)
    seed = {
        "ticker": ticker,
        "latest_period": latest_period,
        "latest_price_date": latest_price.get("latest_price_date"),
        "metrics": sorted(k for k, v in latest.items() if v is not None),
        "catalog_version": CATALOG_VERSION,
        "mapping_version": MAPPING_VERSION,
        "issue_count": len(quality["issues"]),
    }
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_filing_period": latest_period,
        "latest_filing_date": latest_filing.get("filed_at") if latest_filing else None,
        "latest_filing_form": latest_filing.get("form") if latest_filing else None,
        "latest_filing_accession": latest_filing.get("accession") if latest_filing else None,
        "latest_price_date": latest_price.get("latest_price_date"),
        "price_source": latest_price.get("price_source"),
        "catalog_version": CATALOG_VERSION,
        "mapping_version": MAPPING_VERSION,
        "quality_result": "pass" if not quality["issues"] else "warn",
        "source_hash": sha256(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()[:16],
    }


def _source_drilldowns(stores, entity_id: str, latest: dict, snapshot_basis: dict,
                       latest_price: dict) -> dict:
    out = stores.financial.latest_source_drilldowns(entity_id, SNAPSHOT_METRICS)
    for metric in SNAPSHOT_METRICS:
        if metric in out or latest.get(metric) is None:
            continue
        if metric in READ_TIME_FORMULAS:
            out[metric] = {
                "metric": metric,
                "value": latest.get(metric),
                "period_end": (snapshot_basis.get(metric) or {}).get("period_end"),
                "period_type": (snapshot_basis.get(metric) or {}).get("period_type"),
                "quality": "accepted",
                "is_calculated": True,
                "catalog_version": CATALOG_VERSION,
                "mapping_version": MAPPING_VERSION,
                "lineage": {
                    "source": "read_time_projection",
                    "formula": READ_TIME_FORMULAS[metric],
                    "latest_price_date": latest_price.get("latest_price_date"),
                },
                "facts": [],
                "sources": [],
            }
    return out


def _max_period(basis: dict) -> str | None:
    periods = [b.get("period_end") for b in basis.values() if b.get("period_end")]
    return max(periods) if periods else None


def _cagr(series: list[dict]) -> float | None:
    if len(series) < 2:
        return None
    latest, oldest = series[0]["value"], series[-1]["value"]
    years = len(series) - 1
    if not all(isinstance(v, (int, float)) and v > 0 for v in (latest, oldest)):
        return None
    return ((latest / oldest) ** (1.0 / years) - 1.0) * 100.0


def _trajectory(series: list[dict]) -> dict | None:
    if len(series) < 2:
        return None
    latest, oldest = series[0]["value"], series[-1]["value"]
    if not all(isinstance(v, (int, float)) for v in (latest, oldest)):
        return None
    change_bps = round((latest - oldest) * 10000)
    if change_bps > 50:
        direction = "expanding"
    elif change_bps < -50:
        direction = "contracting"
    else:
        direction = "stable"
    return {"direction": direction, "change_bps": change_bps,
            "periods": len(series), "latest": latest, "oldest": oldest}
