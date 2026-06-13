"""Portfolio analytics: benchmark-relative performance, attribution,
exposure, and risk — all derived from the ledger (lots/sales) crossed with
retained daily bars. Pure local reads; projections, never independent truth.

The portfolio value series replays the ledger over the price calendar:
shares held per ticker per day x close on/before that day. Time-weighted
return chains daily returns with cash flows (buy cost / sale proceeds)
removed, so deposits don't masquerade as performance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BENCHMARK = "^GSPC"
BENCHMARK_LABEL = "S&P 500"
RANGE_DAYS = {"1m": 31, "6m": 183, "1y": 366, "5y": 1827}
TRADING_DAYS_PER_YEAR = 252
SERIES_POINT_CAP = 300


def _start_date(range_key: str) -> str:
    days = RANGE_DAYS.get(range_key, RANGE_DAYS["1y"])
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def _ledger_events(stores) -> tuple[dict[str, list], set[str]]:
    """Per-ticker dated share deltas and the set of tickers ever held."""
    events: dict[str, list] = defaultdict(list)   # ticker -> [(date, +/-shares, flow$)]
    tickers: set[str] = set()
    for lot in stores.portfolio.lots():
        t = lot["ticker"].upper()
        tickers.add(t)
        cost = (lot["cost_basis"] or 0) * lot["shares"]
        events[t].append((str(lot["purchase_date"])[:10], lot["shares"], cost))
    for sale in stores.portfolio.sales():
        t = sale["ticker"].upper()
        tickers.add(t)
        proceeds = (sale["price"] or 0) * sale["shares"]
        events[t].append((str(sale["sale_date"])[:10], -sale["shares"], -proceeds))
    for t in events:
        events[t].sort()
    return events, tickers


def value_series(stores, range_key: str = "1y") -> list[dict]:
    """[{date, value, flow}] — portfolio market value by day over the range.
    `flow` is the net cash invested that day (buys positive). Flows dated on
    non-trading days (manual ledger entries) attach to the FIRST trading day
    on or after their date so TWR never mistakes a deposit for performance."""
    import bisect

    events, tickers = _ledger_events(stores)
    if not tickers:
        return []
    start = _start_date(range_key)
    bars: dict[str, list[dict]] = {
        t: stores.bulk.price_range(t, start=start) for t in tickers
    }
    calendar = sorted({b["date"] for rows in bars.values() for b in rows})
    if not calendar:
        return []
    flows_by_date: dict[str, float] = defaultdict(float)
    for t, evs in events.items():
        for d, _shares, flow in evs:
            if d < calendar[0]:
                continue  # pre-window flows are the starting position
            i = bisect.bisect_left(calendar, d)
            if i < len(calendar):
                flows_by_date[calendar[i]] += flow

    series: list[dict] = []
    cursor: dict[str, int] = {t: 0 for t in tickers}      # bar index per ticker
    last_close: dict[str, float] = {}
    for day in calendar:
        value = 0.0
        for t in tickers:
            rows = bars[t]
            i = cursor[t]
            while i < len(rows) and rows[i]["date"] <= day:
                last_close[t] = rows[i]["close"]
                i += 1
            cursor[t] = i
            shares = sum(s for d, s, _ in events[t] if d <= day)
            if shares > 0 and t in last_close:
                value += shares * last_close[t]
        series.append({"date": day, "value": round(value, 2),
                       "flow": round(flows_by_date.get(day, 0.0), 2)})
    return series


def _growth_index(series: list[dict]) -> list[dict]:
    """Flow-adjusted growth index from a value series: chains daily
    (value - flow) / prior_value so deposits and withdrawals are neutral.
    Starts at 100 on the first day with value. The honest basis for indexed
    overlays, drawdown, and volatility."""
    out: list[dict] = []
    level = 100.0
    prev = None
    for p in series:
        if prev is None:
            if p["value"] > 0:
                prev = p["value"]
                out.append({"date": p["date"], "indexed": 100.0})
            continue
        r = (p["value"] - p["flow"]) / prev - 1.0
        level *= 1.0 + r
        out.append({"date": p["date"], "indexed": round(level, 2)})
        prev = p["value"] if p["value"] > 0 else None
        if prev is None:
            break  # fully exited; index freezes at the exit level
    return out


def _twr(series: list[dict]) -> float | None:
    """Time-weighted return over the series, decimal. Flow-adjusted daily
    chaining; days where the prior value is 0 (first buy) contribute nothing."""
    if len(series) < 2:
        return None
    growth = 1.0
    for prev, cur in zip(series, series[1:]):
        base = prev["value"]
        if base <= 0:
            continue
        r = (cur["value"] - cur["flow"]) / base - 1.0
        growth *= 1.0 + r
    return growth - 1.0


def _indexed(points: list[dict], key: str = "value") -> list[dict]:
    base = next((p[key] for p in points if p[key]), None)
    if not base:
        return []
    return [{"date": p["date"], "indexed": round(p[key] / base * 100, 2)} for p in points]


def _max_drawdown(values: list[float]) -> float | None:
    peak, worst = None, 0.0
    for v in values:
        if v <= 0:
            continue
        peak = v if peak is None or v > peak else peak
        if peak:
            worst = min(worst, v / peak - 1.0)
    return worst if peak is not None else None


def _daily_returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))
            if values[i - 1] > 0]


def benchmark_compare(stores, range_key: str = "1y") -> dict:
    """Portfolio vs benchmark: flow-adjusted indexed overlay + headline
    returns. Both legs are measured over the SAME window — from the first day
    the portfolio actually has value — so a 3-month-old portfolio is never
    compared against 12 months of index."""
    pv = value_series(stores, range_key)
    overlay_p = _growth_index(pv)
    window_start = overlay_p[0]["date"] if overlay_p else None
    bench = stores.bulk.price_range(BENCHMARK, start=_start_date(range_key))
    bench_points = [{"date": b["date"], "value": b["close"]} for b in bench
                    if window_start is None or b["date"] >= window_start]
    twr = _twr(pv)
    bench_return = (bench_points[-1]["value"] / bench_points[0]["value"] - 1.0) \
        if len(bench_points) >= 2 else None
    overlay_b = _indexed(bench_points)
    step = max(1, len(overlay_p) // SERIES_POINT_CAP)
    return {
        "range": range_key,
        "benchmark": BENCHMARK, "benchmark_label": BENCHMARK_LABEL,
        "portfolio_return": twr,
        "benchmark_return": bench_return,
        "excess_return": (twr - bench_return) if twr is not None and bench_return is not None else None,
        "window_start": window_start,
        "portfolio_series": overlay_p[::step],
        "benchmark_series": overlay_b[::max(1, len(overlay_b) // SERIES_POINT_CAP)],
        "benchmark_available": bool(bench_points),
        "note": None if bench_points else
                f"benchmark series {BENCHMARK} not ingested yet — runs with the daily sync",
    }


def contribution(stores) -> list[dict]:
    """Per-position P&L contribution: (unrealized + realized) per ticker as
    percentage points of total capital deployed. Capital deployed = remaining
    cost basis of open lots + original cost of sold shares (proceeds minus
    realized P&L), so a profitable sale doesn't inflate the denominator."""
    holdings = {h["ticker"]: h for h in stores.portfolio.holdings()}
    realized: dict[str, float] = defaultdict(float)
    sold_cost = 0.0
    for s in stores.portfolio.sales():
        pnl = s.get("realized_pnl") or 0.0
        realized[s["ticker"].upper()] += pnl
        sold_cost += (s["price"] or 0) * s["shares"] - pnl
    cost_total = sum((h["avg_cost"] or 0) * h["shares"] for h in holdings.values())
    cost_total += sold_cost
    rows = []
    tickers = set(holdings) | set(realized)
    for t in sorted(tickers):
        h = holdings.get(t)
        unreal = (h or {}).get("unrealized_pnl") or 0.0
        total = unreal + realized.get(t, 0.0)
        ent = stores.identity.resolve_ticker(t) or {}
        rows.append({
            "ticker": t,
            "sector": ent.get("sector"),
            "unrealized_pnl": round(unreal, 2),
            "realized_pnl": round(realized.get(t, 0.0), 2),
            "total_pnl": round(total, 2),
            "contribution_pp": round(total / cost_total * 100, 2) if cost_total else None,
            "weight": (h or {}).get("weight"),
            # Fully-sold names carry realized P&L but no open position; flag them
            # so the UI marks them closed instead of looking like ghost holdings
            # (ISSUE-013).
            "exited": h is None,
        })
    rows.sort(key=lambda r: -(r["total_pnl"]))
    return rows


def exposure(stores) -> dict:
    """Sector weights + concentration over current holdings, flagged against
    the Constitution's concentration threshold (portfolio_review wiring)."""
    holdings = stores.portfolio.holdings()
    total = sum(h["market_value"] or 0 for h in holdings)
    sectors: dict[str, float] = defaultdict(float)
    positions = []
    for h in holdings:
        ent = stores.identity.resolve_ticker(h["ticker"]) or {}
        mv = h["market_value"] or 0
        sectors[ent.get("sector") or "Unknown"] += mv
        positions.append({"ticker": h["ticker"], "weight": h.get("weight")})
    proj = stores.constitution.projection("portfolio_review")
    flag_pct = float(((proj or {}).get("settings") or {})
                     .get("concentration_flag_pct", 20.0))
    sector_rows = []
    flags = []
    for s, v in sorted(sectors.items(), key=lambda kv: -kv[1]):
        weight = round(v / total, 4) if total else None
        over = weight is not None and weight * 100 > flag_pct * 2
        sector_rows.append({"sector": s, "weight": weight, "over_threshold": over})
        if over:
            flags.append(f"{s} is {weight * 100:.0f}% of market value "
                         f"(sector watch line {flag_pct * 2:.0f}%)")
    positions.sort(key=lambda p: -(p["weight"] or 0))
    top = positions[0] if positions else None
    if top and top["weight"] is not None and top["weight"] * 100 > flag_pct:
        flags.append(f"{top['ticker']} is {top['weight'] * 100:.0f}% of the portfolio "
                     f"(concentration flag threshold {flag_pct:.0f}%)")
    return {
        "sectors": sector_rows,
        "top_position_weight": top["weight"] if top else None,
        "top3_weight": round(sum(p["weight"] or 0 for p in positions[:3]), 4)
                       if positions else None,
        "positions": len(positions),
        "concentration_flag_pct": flag_pct,
        "flags": flags,
    }


def risk(stores, range_key: str = "1y") -> dict:
    """Volatility, beta/correlation vs benchmark, max drawdown — all over the
    flow-adjusted growth index, so deposits/withdrawals never read as gains,
    crashes, or volatility."""
    pv = value_series(stores, range_key)
    growth = _growth_index(pv)
    levels = [g["indexed"] for g in growth]
    rets = _daily_returns(levels)
    bench = stores.bulk.price_range(BENCHMARK, start=_start_date(range_key))
    bench_by_date = {b["date"]: b["close"] for b in bench}
    paired: list[tuple[float, float]] = []
    prev_g, prev_b = None, None
    for g in growth:
        b = bench_by_date.get(g["date"])
        if b is None:
            continue
        if prev_g and prev_b:
            paired.append((g["indexed"] / prev_g - 1.0, b / prev_b - 1.0))
        prev_g, prev_b = g["indexed"], b
    out: dict = {"range": range_key, "max_drawdown": _max_drawdown(levels)}
    if len(rets) >= 20:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        out["volatility"] = math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR)
    if len(paired) >= 20:
        pr = [a for a, _ in paired]
        br = [b for _, b in paired]
        mp, mb = sum(pr) / len(pr), sum(br) / len(br)
        cov = sum((a - mp) * (b - mb) for a, b in paired) / (len(paired) - 1)
        var_b = sum((b - mb) ** 2 for b in br) / (len(paired) - 1)
        var_p = sum((a - mp) ** 2 for a in pr) / (len(paired) - 1)
        if var_b > 0:
            out["beta"] = cov / var_b
        if var_b > 0 and var_p > 0:
            out["correlation"] = cov / math.sqrt(var_b * var_p)
    return out


def decision_attribution(stores, min_age_days: int = 30) -> dict:
    """What promote/dismiss choices did after the fact: forward price return
    from each selection event to the latest retained close. Observational
    evidence (selection_events are recorded by the workflow pages), never a
    verdict — and events younger than min_age_days are excluded as noise."""
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc).date()
              - timedelta(days=min_age_days)).isoformat()
    rows = []
    for e in stores.runs.selection_events(limit=500):
        event_date = str(e["created_at"])[:10]
        if event_date > cutoff:
            continue
        bars = stores.bulk.price_range(e["ticker"], start=event_date)
        if len(bars) < 2:
            continue
        fwd = bars[-1]["close"] / bars[0]["close"] - 1.0
        rows.append({"ticker": e["ticker"], "action": e["action"],
                     "capability": e["capability"], "date": event_date,
                     "forward_return": round(fwd, 4),
                     "days": (datetime.fromisoformat(str(bars[-1]["date"]))
                              - datetime.fromisoformat(event_date)).days})
    def _avg(action: str) -> float | None:
        vals = [r["forward_return"] for r in rows if r["action"] == action]
        return round(sum(vals) / len(vals), 4) if vals else None
    rows.sort(key=lambda r: r["date"], reverse=True)
    return {
        "events_measured": len(rows),
        "min_age_days": min_age_days,
        "promoted_avg_return": _avg("promote"),
        "dismissed_avg_return": _avg("dismiss"),
        "recent": rows[:10],
        "note": ("Forward price returns since each promote/dismiss — observational "
                 "evidence about your selection instincts, not proof of skill."),
    }


FACTOR_METRICS = (("size", "market_cap", "Size"),
                  ("value", "fcf_yield", "Value (FCF yield)"),
                  ("quality", "roic", "Quality (ROIC)"),
                  ("momentum", "momentum_6m", "Momentum (6M)"))


def factor_tilts(stores) -> list[dict]:
    """Weight-averaged percentile of each holding vs every data-bearing
    entity, per factor proxy. 50 = universe-typical; higher = tilted toward
    bigger / cheaper-on-FCF / higher-ROIC / stronger-momentum names."""
    # Price-derived factors (size=market_cap, value=fcf_yield) are never stored,
    # so reading raw latest() left them empty for every name — half the panel
    # dead. Derive them the same way the snapshot does, from a one-pass price map.
    from backend.domain.derive import derive_price_metrics

    closes = stores.bulk.latest_closes()
    distributions: dict[str, list[float]] = {m: [] for _, m, _ in FACTOR_METRICS}
    for t in stores.identity.all_tickers():
        ent = stores.identity.resolve_ticker(t)
        if not ent:
            continue
        latest = derive_price_metrics(dict(stores.financial.latest(ent["id"])),
                                      closes.get(t.upper()))
        for _, metric, _ in FACTOR_METRICS:
            v = latest.get(metric)
            if isinstance(v, (int, float)):
                distributions[metric].append(v)
    for metric in distributions:
        distributions[metric].sort()

    def _percentile(metric: str, value: float) -> float | None:
        dist = distributions[metric]
        if len(dist) < 5:
            return None
        below = sum(1 for v in dist if v <= value)
        return below / len(dist) * 100

    holdings = stores.portfolio.holdings()
    total_w = sum(h["weight"] or 0 for h in holdings) or None
    # Same shared derivation for the held names, so a holding's size/value factor
    # is measured against the universe distribution on the same basis.
    held_metrics = {}
    for h in holdings:
        ent = stores.identity.resolve_ticker(h["ticker"])
        if ent:
            held_metrics[h["ticker"]] = derive_price_metrics(
                dict(stores.financial.latest(ent["id"])), closes.get(h["ticker"].upper()))
    out = []
    for key, metric, label in FACTOR_METRICS:
        acc, w_acc = 0.0, 0.0
        for h in holdings:
            if not h.get("weight") or h["ticker"] not in held_metrics:
                continue
            v = held_metrics[h["ticker"]].get(metric)
            if not isinstance(v, (int, float)):
                continue
            pct = _percentile(metric, v)
            if pct is None:
                continue
            acc += pct * h["weight"]
            w_acc += h["weight"]
        out.append({
            "factor": key, "label": label, "metric": metric,
            "percentile": round(acc / w_acc, 1) if w_acc else None,
            "coverage": round(w_acc / total_w, 2) if total_w and w_acc else None,
        })
    return out


def analytics_view(stores, range_key: str = "1y") -> dict:
    return {
        "performance": benchmark_compare(stores, range_key),
        "contribution": contribution(stores),
        "exposure": exposure(stores),
        "risk": risk(stores, range_key),
        "decisions": decision_attribution(stores),
        "factor_tilts": factor_tilts(stores),
    }
