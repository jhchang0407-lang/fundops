"""Research Hub: deterministic industry/sector/theme dashboards.

Everything here is a pure local aggregation over identity groups x
latest_financials x ownership — no model calls, no network. Peer groups come
from entity industry (fallback sector); custom themes are watchlists with
kind='theme'. The AI research runs (industry notes etc.) build ON TOP of
these views — they never replace them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.domain.derive import derive_price_metrics

AGGREGATE_METRICS = ("roic", "gross_margin", "operating_margin", "revenue_growth",
                     "fcf_yield", "momentum_6m", "pe")
CONSTITUENT_METRICS = ("market_cap", "pe", "roic", "gross_margin", "revenue_growth",
                       "fcf_yield", "momentum_6m", "avg_dollar_volume_3m")
PEER_LIMIT_DEFAULT = 8
MCAP_BUCKETS = (("micro (<$300M)", 0, 3e8), ("small ($300M–$2B)", 3e8, 2e9),
                ("mid ($2B–$10B)", 2e9, 1e10), ("large (>$10B)", 1e10, float("inf")))


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if isinstance(v, (int, float)))
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2


def _percentile(values: list[float], pct: float) -> float | None:
    vals = sorted(v for v in values if isinstance(v, (int, float)))
    if not vals:
        return None
    idx = min(len(vals) - 1, max(0, round(pct * (len(vals) - 1))))
    return vals[idx]


def _derive_price_metrics(stores, ticker: str, latest: dict) -> None:
    """market_cap / pe / fcf_yield are price-dependent and never stored
    (ADR-0017). Look up the latest close and fill them via the ONE shared
    derivation (backend/domain/derive.py) so constituent grids agree with the
    Company snapshot and the portfolio factor tilts. Fills gaps only."""
    if latest.get("market_cap") and latest.get("pe") and latest.get("fcf_yield"):
        return
    lc = stores.bulk.latest_close(ticker)
    derive_price_metrics(latest, lc["close"] if lc else None)


def _rows_for_entities(stores, entities: list[dict]) -> list[dict]:
    rows = []
    for e in entities:
        latest = dict(stores.financial.latest(e["id"]))
        if not latest:
            continue
        _derive_price_metrics(stores, e["ticker"], latest)
        rows.append({"ticker": e["ticker"], "name": e.get("name") or e["ticker"],
                     "sector": e.get("sector"), "industry": e.get("industry"),
                     "metrics": latest})
    return rows


PE_BUCKETS = ((0, 10), (10, 15), (15, 20), (20, 30), (30, 45), (45, float("inf")))
TREND_YEARS = 5


def _pe_distribution(rows: list[dict]) -> list[dict]:
    """Histogram of constituents' P/E for the valuation-spread chart."""
    out = []
    values = [r["metrics"].get("pe") for r in rows]
    pes = [v for v in values if isinstance(v, (int, float)) and v > 0]
    for lo, hi in PE_BUCKETS:
        n = sum(1 for v in pes if lo <= v < hi)
        label = f"{lo:g}–{hi:g}x" if hi != float("inf") else f"{lo:g}x+"
        out.append({"bucket": label, "count": n})
    return out if pes else []


def _margin_trend(stores, entities: list[dict], metric: str = "gross_margin") -> list[dict]:
    """Median margin per fiscal year across the group, from retained annual
    observations — the 'is this industry's profitability improving' line."""
    by_year: dict[str, list[float]] = {}
    for e in entities:
        for p in stores.financial.periods(e["id"], "annual", limit=200):
            v = p["metrics"].get(metric)
            if isinstance(v, (int, float)):
                by_year.setdefault(p["period_end"][:4], []).append(v)
    years = sorted(by_year)[-TREND_YEARS:]
    return [{"year": y, "median": round(_median(by_year[y]) or 0, 4),
             "coverage": len(by_year[y])} for y in years]


def group_dashboard(stores, entities: list[dict], group_label: str) -> dict:
    """Aggregate stats + constituents for any entity group."""
    rows = _rows_for_entities(stores, entities)
    aggregates = {}
    for metric in AGGREGATE_METRICS:
        values = [r["metrics"].get(metric) for r in rows]
        aggregates[metric] = {
            "median": _median(values),
            "p25": _percentile(values, 0.25),
            "p75": _percentile(values, 0.75),
            "coverage": sum(1 for v in values if isinstance(v, (int, float))),
        }
    mcap_breakdown = []
    caps = [(r["ticker"], r["metrics"].get("market_cap")) for r in rows]
    for label, lo, hi in MCAP_BUCKETS:
        n = sum(1 for _, c in caps if isinstance(c, (int, float)) and lo <= c < hi)
        if n:
            mcap_breakdown.append({"bucket": label, "count": n})
    since = (datetime.now(timezone.utc).date() - timedelta(days=90)).isoformat()
    insider_buys = 0
    for r in rows[:200]:
        insider_buys += sum(
            1 for o in stores.bulk.ownership_for(r["ticker"], kind="insider_transaction",
                                                 limit=50)
            if str(o.get("as_of", ""))[:10] >= since
            and (o.get("txn_type") or "").lower().startswith("b"))
    constituents = [
        {"ticker": r["ticker"], "name": r["name"],
         **{m: r["metrics"].get(m) for m in CONSTITUENT_METRICS}}
        for r in rows
    ]
    constituents.sort(key=lambda c: (c.get("market_cap") is None,
                                     -(c.get("market_cap") or 0)))
    return {
        "group": group_label,
        "size": len(entities),
        "with_data": len(rows),
        "aggregates": aggregates,
        "market_cap_breakdown": mcap_breakdown,
        "pe_distribution": _pe_distribution(rows),
        "margin_trend": _margin_trend(stores, entities),
        "insider_buys_90d": insider_buys,
        "constituents": constituents,
        "constituent_metrics": list(CONSTITUENT_METRICS),
    }


def industry_dashboard(stores, sector: str | None, industry: str | None) -> dict:
    entities = stores.identity.entities_in_group(sector=sector, industry=industry)
    label = industry or sector or "unknown"
    out = group_dashboard(stores, entities, label)
    out["sector"] = sector
    out["industry"] = industry
    return out


def theme_dashboard(stores, watchlist_id: str) -> dict | None:
    wl = stores.context.get_watchlist(watchlist_id)
    if not wl:
        return None
    entities = []
    for t in wl["tickers"]:
        ent = stores.identity.resolve_ticker(t)
        if ent:
            entities.append({**ent, "ticker": t})
    out = group_dashboard(stores, entities, wl["name"])
    out["watchlist_id"] = watchlist_id
    out["kind"] = wl["kind"]
    return out


def peers_for(stores, ticker: str, limit: int = PEER_LIMIT_DEFAULT) -> list[dict]:
    """Deterministic peer set: same industry (fallback sector), nearest by
    market cap, the subject first."""
    ticker = ticker.upper()
    ent = stores.identity.resolve_ticker(ticker)
    if not ent:
        return []
    # Widen gradually: exact industry → 3-digit SIC group → 2-digit SIC major
    # group → sector. Jumping straight to sector put Coca-Cola next to
    # semiconductor makers ("Manufacturing" spans both).
    group = []
    if ent.get("industry"):
        group = stores.identity.entities_in_group(industry=ent["industry"])
    sic = str(ent.get("sic") or "")
    if len(group) < 3 and len(sic) == 4:
        group = stores.identity.entities_with_sic_prefix(sic[:3])
    if len(group) < 3 and len(sic) == 4:
        group = stores.identity.entities_with_sic_prefix(sic[:2])
    if len(group) < 3 and ent.get("sector"):
        group = stores.identity.entities_in_group(sector=ent["sector"])
    rows = _rows_for_entities(stores, [e for e in group if e["ticker"] != ticker])
    subject_latest = dict(stores.financial.latest(ent["id"]))
    _derive_price_metrics(stores, ticker, subject_latest)
    subject_cap = subject_latest.get("market_cap") or 0
    rows.sort(key=lambda r: abs((r["metrics"].get("market_cap") or 0) - subject_cap))
    out = [{"ticker": ticker, "name": ent.get("name") or ticker, "is_subject": True,
            **{m: subject_latest.get(m) for m in CONSTITUENT_METRICS}}]
    for r in rows[: max(0, limit - 1)]:
        out.append({"ticker": r["ticker"], "name": r["name"], "is_subject": False,
                    **{m: r["metrics"].get(m) for m in CONSTITUENT_METRICS}})
    return out
