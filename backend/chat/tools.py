"""Chat analyst tools: read-only lookups over retained local data.

Each tool is a thin wrapper over existing store/service read paths — no tool
writes workspace state. A tool returns a ToolResult dict:

    {"summary":  compact text fed back into the model loop,
     "data":     full structured payload (raw values),
     "block":    optional render block for the chat UI (table/chart),
     "citations": citation pills [{artifact_id?, ticker?, kind, label}],
     "error":    error text (fed to the model as a step result, never raised)}

Table-block cell values are pre-formatted display strings (unit-aware via
labels.format_metric_value) so the client renders them verbatim; raw values
stay available under "data".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.chat import archive_qa
from backend.domain import labels, metric_catalog
from backend.domain.criteria import OPERATORS, Criterion, evaluate

MAX_COMPARE_TICKERS = 6
MAX_COMPARE_METRICS = 8
MAX_SCREEN_UNIVERSE = 500
MAX_SCREEN_ROWS = 50
DEFAULT_SCREEN_ROWS = 20
MAX_INSIDER_ROWS = 20
FINANCIAL_PERIOD_COLS = 5
PRICE_POINT_CAP = 260

DEFAULT_COMPARE_METRICS = (
    "market_cap", "pe", "revenue_growth", "gross_margin",
    "operating_margin", "roic", "fcf_yield", "debt_equity",
)
# Statement-style row order for the financials table; only metrics that
# actually have observations are shown.
FINANCIAL_ROW_METRICS = (
    "revenue", "revenue_growth", "gross_profit", "gross_margin",
    "operating_income", "operating_margin", "net_income", "net_margin",
    "eps", "operating_cash_flow", "free_cash_flow", "fcf_margin",
    "roic", "roe", "debt_equity", "shares_outstanding",
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: dict           # arg name -> {"type", "required", "desc"}
    fn: Callable


def _result(summary: str, data: dict | None = None, block: dict | None = None,
            citations: list[dict] | None = None, error: str | None = None) -> dict:
    return {"summary": summary, "data": data or {}, "block": block,
            "citations": citations or [], "error": error}


def _error(message: str) -> dict:
    return _result(message, error=message)


def _cite(kind: str, label: str, ticker: str | None = None,
          artifact_id: str | None = None) -> dict:
    return {"artifact_id": artifact_id, "ticker": ticker, "kind": kind, "label": label}


def _resolve(stores, ticker) -> tuple[str, dict | None]:
    t = str(ticker or "").strip().upper()
    if not t:
        return t, None
    return t, stores.identity.resolve_ticker(t)


def _fmt(metric: str, value) -> str:
    return labels.format_metric_value(metric, value)


def _canonical_metric(metric) -> str | None:
    m = metric_catalog.get_metric(str(metric or "").strip().lower())
    return m.id if m else None


def _enriched_latest(stores, ticker: str, ent: dict | None) -> dict:
    """Latest stored projection + read-time price/growth metrics, derived the
    ONE shared way (workflows.evidence_packets.enriched_snapshot → domain/
    derive.py): market_cap / pe / fcf_yield / earnings_yield are price-dependent
    and never stored (ADR-0017), and revenue_growth needs multi-period history —
    so chat must derive them at read time exactly as the Company snapshot, peers
    grid and portfolio factor tilts do, or every chat metric reads as a null.
    Fills gaps only (never overwrites a stored value). Returns {} for an unknown
    entity or one with no retained financials."""
    if not ent:
        return {}
    from backend.workflows.evidence_packets import enriched_snapshot

    price = stores.portfolio.prices().get(ticker)
    if price is None:
        lc = stores.bulk.latest_close(ticker)
        price = lc["close"] if lc else None
    return enriched_snapshot(stores, ent["id"], price)


# --- tools -------------------------------------------------------------------------

def get_company_financials(stores, args: dict) -> dict:
    ticker, ent = _resolve(stores, args.get("ticker"))
    if not ent:
        return _error(f"unknown ticker {ticker or '(missing)'} — no retained financial data")
    period_type = args.get("period_type") if args.get("period_type") in ("annual", "quarterly") else "annual"
    periods = stores.financial.periods(ent["id"], period_type)[:FINANCIAL_PERIOD_COLS]
    latest = _enriched_latest(stores, ticker, ent)
    if not periods and not latest:
        return _error(f"no financial observations retained for {ticker} yet")

    metrics_present = [m for m in FINANCIAL_ROW_METRICS
                       if any(m in p["metrics"] for p in periods)]
    columns = [{"key": "metric", "label": "Metric"}] + [
        {"key": p["period_end"], "label": p["period_end"]} for p in periods
    ]
    rows = [
        {"metric": labels.metric_label(m),
         **{p["period_end"]: _fmt(m, p["metrics"].get(m)) for p in periods}}
        for m in metrics_present
    ]
    as_of = periods[0]["period_end"] if periods else None
    head = (f"{ticker} ({ent.get('name') or ticker}) {period_type} financials"
            + (f" through {as_of}" if as_of else ""))
    key_latest = {m: latest.get(m) for m in
                  ("revenue", "gross_margin", "operating_margin", "roic", "pe", "fcf_yield")
                  if latest.get(m) is not None}
    summary = head + ". Latest: " + (
        ", ".join(f"{m}={_fmt(m, v)}" for m, v in key_latest.items()) or "no headline metrics"
    )
    return _result(
        summary,
        data={"ticker": ticker, "period_type": period_type, "periods": periods,
              "latest": latest, "as_of": as_of},
        block={"type": "table", "title": head, "columns": columns, "rows": rows},
        citations=[_cite("reported_financials",
                         f"{ticker} reported financials" + (f" (through {as_of})" if as_of else ""),
                         ticker=ticker)],
    )


def get_metric(stores, args: dict) -> dict:
    ticker, ent = _resolve(stores, args.get("ticker"))
    if not ent:
        return _error(f"unknown ticker {ticker or '(missing)'}")
    metric = _canonical_metric(args.get("metric"))
    if not metric:
        return _error(f"unsupported metric {args.get('metric')!r} — use ids from the metric catalog")
    period_type = args.get("period_type") if args.get("period_type") in ("annual", "quarterly") else "annual"
    limit = min(int(args.get("limit") or 12), 24)
    obs = stores.financial.observations(ent["id"], metric=metric, period_type=period_type, limit=limit)
    if not obs:
        latest = stores.financial.latest_value(ent["id"], metric)
        if latest is None:
            # market_cap / pe / fcf_yield / earnings_yield / revenue_growth are
            # derived, never stored (ADR-0017) — derive at read time before giving up.
            latest = _enriched_latest(stores, ticker, ent).get(metric)
        if latest is None:
            return _error(f"no retained {metric} observations for {ticker}")
        obs = [{"period_end": "latest", "value": latest}]
    label = labels.metric_label(metric)
    rows = [{"period_end": o["period_end"], "value": _fmt(metric, o["value"])} for o in obs]
    summary = f"{ticker} {label} ({period_type}): " + ", ".join(
        f"{o['period_end']}={_fmt(metric, o['value'])}" for o in obs[:8]
    )
    return _result(
        summary,
        data={"ticker": ticker, "metric": metric, "period_type": period_type,
              "observations": [{"period_end": o["period_end"], "value": o["value"]} for o in obs]},
        block={"type": "table", "title": f"{ticker} — {label} ({period_type})",
               "columns": [{"key": "period_end", "label": "Period"},
                           {"key": "value", "label": label, "metric": metric}],
               "rows": rows},
        citations=[_cite("reported_financials", f"{ticker} {label} history", ticker=ticker)],
    )


def get_price_history(stores, args: dict) -> dict:
    from backend.services.ingest.prices import price_chart

    ticker = str(args.get("ticker") or "").strip().upper()
    if not ticker:
        return _error("ticker is required")
    range_key = args.get("range") if args.get("range") in ("1m", "6m", "1y", "5y") else "1y"
    rows = price_chart(stores, ticker, range_key)
    if not rows:
        return _error(f"no retained price history for {ticker} — it arrives with data syncs")
    points = [{"date": r["date"], "close": r["close"]} for r in rows]
    if len(points) > PRICE_POINT_CAP:
        step = max(1, len(points) // PRICE_POINT_CAP)
        points = points[::step] + ([points[-1]] if points[-1] not in points[::step] else [])
    first, last = rows[0], rows[-1]
    change = ((last["close"] / first["close"]) - 1) * 100 if first["close"] else None
    summary = (f"{ticker} close {first['date']}={_fmt('price', first['close'])} → "
               f"{last['date']}={_fmt('price', last['close'])}"
               + (f" ({change:+.1f}% over {range_key})" if change is not None else ""))
    return _result(
        summary,
        data={"ticker": ticker, "range": range_key, "first": first, "last": last,
              "change_pct": change, "points": len(rows)},
        block={"type": "chart", "title": f"{ticker} — price ({range_key})",
               "ticker": ticker, "range": range_key, "points": points},
        citations=[_cite("price_history", f"{ticker} price history ({range_key}, "
                         f"through {last['date']})", ticker=ticker)],
    )


def compare_companies(stores, args: dict) -> dict:
    raw_tickers = args.get("tickers") or []
    if isinstance(raw_tickers, str):
        raw_tickers = [t for t in raw_tickers.replace(",", " ").split() if t]
    tickers = [str(t).strip().upper() for t in raw_tickers][:MAX_COMPARE_TICKERS]
    peers_of = str(args.get("peers_of") or "").strip().upper()
    if peers_of:
        from backend.services.research_hub import peers_for
        peer_rows = peers_for(stores, peers_of, limit=MAX_COMPARE_TICKERS)
        if not peer_rows:
            return _error(f"no peer group found for {peers_of}")
        tickers = [p["ticker"] for p in peer_rows][:MAX_COMPARE_TICKERS]
    if len(tickers) < 2:
        return _error("compare_companies needs at least 2 tickers (or peers_of)")
    raw_metrics = args.get("metrics") or list(DEFAULT_COMPARE_METRICS)
    if isinstance(raw_metrics, str):
        raw_metrics = [m for m in raw_metrics.replace(",", " ").split() if m]
    metrics, bad = [], []
    for m in raw_metrics:
        canon = _canonical_metric(m)
        (metrics.append(canon) if canon and canon not in metrics else bad.append(str(m)))
    metrics = metrics[:MAX_COMPARE_METRICS]
    if not metrics:
        return _error(f"no supported metrics among {raw_metrics!r}")

    rows, raw, citations, missing = [], {}, [], []
    for t in tickers:
        t, ent = _resolve(stores, t)
        if not ent:
            missing.append(t)
            continue
        latest = _enriched_latest(stores, t, ent)
        raw[t] = {m: latest.get(m) for m in metrics}
        rows.append({"ticker": t, "company": ent.get("name") or t,
                     **{m: _fmt(m, latest.get(m)) for m in metrics}})
        citations.append(_cite("reported_financials", f"{t} reported financials", ticker=t))
    if not rows:
        return _error(f"none of {', '.join(tickers)} have retained data")

    columns = [{"key": "ticker", "label": "Ticker"}, {"key": "company", "label": "Company"}] + [
        {"key": m, "label": labels.metric_label(m), "metric": m} for m in metrics
    ]
    summary_lines = [
        f"{r['ticker']}: " + ", ".join(f"{m}={r[m]}" for m in metrics) for r in rows
    ]
    notes = []
    if missing:
        notes.append(f"no data for {', '.join(missing)}")
    if bad:
        notes.append(f"unsupported metrics skipped: {', '.join(bad)}")
    summary = "Comparison — " + "; ".join(summary_lines) + (
        f" ({'; '.join(notes)})" if notes else "")
    return _result(
        summary,
        data={"tickers": [r["ticker"] for r in rows], "metrics": metrics,
              "values": raw, "missing": missing},
        block={"type": "table",
               "title": "Comparison — " + ", ".join(r["ticker"] for r in rows),
               "columns": columns, "rows": rows},
        citations=citations,
    )


def screen_universe(stores, args: dict) -> dict:
    """Ad-hoc screen over retained observations. Never touches the
    Constitution, screener runs, or artifacts — a pure read + evaluate."""
    raw_criteria = args.get("criteria") or []
    if isinstance(raw_criteria, dict):
        raw_criteria = [raw_criteria]
    criteria: list[Criterion] = []
    notes: list[str] = []
    for c in raw_criteria:
        if not isinstance(c, dict):
            continue
        metric = _canonical_metric(c.get("metric"))
        op = c.get("operator")
        value = c.get("value")
        if not metric:
            notes.append(f"unsupported metric {c.get('metric')!r} skipped")
            continue
        if op not in OPERATORS or not isinstance(value, (int, float)):
            notes.append(f"invalid rule for {metric} skipped")
            continue
        m = metric_catalog.get_metric(metric)
        if m and m.unit == "ratio" and abs(value) > 1.5:
            # "roic above 15" almost certainly means 15%, but only reinterpret
            # when the catalog's typical range agrees: raw value outside it,
            # value/100 inside it. "momentum_12m > 2" (a real 200% threshold
            # within range) stays untouched.
            lo, hi = (m.typical_range + (None, None))[:2]
            raw_in = isinstance(lo, (int, float)) and isinstance(hi, (int, float)) \
                and lo <= value <= hi
            scaled_in = isinstance(lo, (int, float)) and isinstance(hi, (int, float)) \
                and lo <= value / 100 <= hi
            if scaled_in and not raw_in:
                notes.append(f"{metric}: interpreted {value:g} as {value:g}% ({value / 100:g})")
                value = value / 100
        criteria.append(Criterion(
            criterion_id=f"adhoc.{metric}", kind="screen",
            rule_rationale="ad-hoc chat screen", rule_source="chat",
            metric=metric, operator=op, value=value,
        ))
    if not criteria:
        return _error("no valid criteria — each needs {metric, operator, value} "
                      "with a catalog metric and numeric value")

    universe = stores.constitution.active_universe()
    tickers = list(universe["tickers"]) if universe else stores.identity.all_tickers()
    universe_name = universe["name"] if universe else "known tickers"
    total = len(tickers)
    if total > MAX_SCREEN_UNIVERSE:
        tickers = tickers[:MAX_SCREEN_UNIVERSE]
        notes.append(f"evaluated first {MAX_SCREEN_UNIVERSE} of {total} tickers")

    sort_by = _canonical_metric(args.get("sort_by")) or criteria[0].metric
    limit = max(1, min(int(args.get("limit") or DEFAULT_SCREEN_ROWS), MAX_SCREEN_ROWS))

    passed, evaluated, unevaluable = [], 0, 0
    metric_available = {c.metric: False for c in criteria}
    for t in tickers:
        t, ent = _resolve(stores, t)
        if not ent:
            unevaluable += 1
            continue
        latest = _enriched_latest(stores, t, ent)
        if not latest:
            unevaluable += 1
            continue
        evaluated += 1
        for c in criteria:
            if latest.get(c.metric) is not None:
                metric_available[c.metric] = True
        results = [evaluate(c, latest.get(c.metric)) for c in criteria]
        if any(r.satisfied is None for r in results):
            unevaluable += 1
            continue
        if all(r.satisfied for r in results):
            passed.append({"ticker": t, "name": ent.get("name") or t, "metrics": latest})
    # Distinguish "screened out" from "metric not available anywhere": a
    # criterion whose metric is null for every evaluated company makes the
    # whole screen unevaluable, which would otherwise read as "0 passed".
    dead_metrics = [m for m, seen in metric_available.items() if not seen]
    if evaluated and dead_metrics:
        notes.append("no data for "
                     + ", ".join(labels.metric_label(m) for m in dead_metrics)
                     + f" across any of the {evaluated} evaluated companies")

    passed.sort(key=lambda p: (p["metrics"].get(sort_by) is None,
                               -(p["metrics"].get(sort_by) or 0)))
    shown = passed[:limit]
    show_metrics = list(dict.fromkeys([c.metric for c in criteria] + [sort_by]))
    columns = [{"key": "ticker", "label": "Ticker"}, {"key": "name", "label": "Company"}] + [
        {"key": m, "label": labels.metric_label(m), "metric": m} for m in show_metrics
    ]
    rows = [{"ticker": p["ticker"], "name": p["name"],
             **{m: _fmt(m, p["metrics"].get(m)) for m in show_metrics}} for p in shown]
    rule_text = " and ".join(
        f"{c.metric} {c.operator} {labels.format_metric_value(c.metric, c.value)}"
        for c in criteria
    )
    summary = (f"Ad-hoc screen ({rule_text}) over {universe_name}: {len(passed)} of "
               f"{evaluated} evaluated pass ({unevaluable} unevaluable); top "
               f"{len(shown)} by {sort_by}: "
               + (", ".join(p["ticker"] for p in shown) or "none")
               + (f". Notes: {'; '.join(notes)}" if notes else "")
               + ". This was an ad-hoc screen; the Constitution is unchanged.")
    return _result(
        summary,
        data={"criteria": [c.to_dict() for c in criteria], "universe": universe_name,
              "passed": len(passed), "evaluated": evaluated, "unevaluable": unevaluable,
              "tickers": [p["ticker"] for p in passed]},
        block={"type": "table",
               "title": f"Ad-hoc screen — {len(passed)} pass ({universe_name})",
               "columns": columns, "rows": rows},
        citations=[_cite("screen", f"Ad-hoc screen over {universe_name} "
                         f"({evaluated} evaluated)")],
    )


def get_portfolio_summary(stores, args: dict) -> dict:
    from backend.services.portfolio_service import PortfolioService

    rows_view = PortfolioService(stores).holdings_view()
    totals = stores.portfolio.totals()
    if not rows_view:
        return _result("The portfolio ledger is empty — no purchase lots recorded yet.",
                       data={"totals": totals, "holdings": []})
    columns = [
        {"key": "ticker", "label": "Ticker"}, {"key": "shares", "label": "Shares"},
        {"key": "avg_cost", "label": "Avg cost"}, {"key": "price", "label": "Price"},
        {"key": "market_value", "label": "Mkt value"},
        {"key": "unrealized_pnl", "label": "Unreal P&L"},
        {"key": "weight", "label": "Weight"}, {"key": "health", "label": "Thesis health"},
    ]
    rows = [{
        "ticker": h["ticker"],
        "shares": f"{h['shares']:g}",
        "avg_cost": _fmt("price", h["avg_cost"]),
        "price": _fmt("price", h["price"]),
        "market_value": _fmt("market_cap", h["market_value"]),
        "unrealized_pnl": _fmt("price", h["unrealized_pnl"]),
        "weight": f"{h['weight'] * 100:.1f}%" if h.get("weight") is not None else "—",
        "health": (h.get("thesis_health_label") or "—").replace("_", " "),
    } for h in rows_view]
    summary = (f"Portfolio: {totals['positions']} positions, market value "
               f"{_fmt('market_cap', totals['market_value'])}, unrealized P&L "
               f"{_fmt('price', totals['unrealized_pnl'])}, realized P&L "
               f"{_fmt('price', totals['realized_pnl'])}. Holdings: "
               + ", ".join(h["ticker"] for h in rows_view))
    return _result(
        summary,
        data={"totals": totals, "holdings": rows_view},
        block={"type": "table", "title": "Portfolio holdings", "columns": columns, "rows": rows},
        citations=[_cite("portfolio", f"Portfolio ledger ({totals['positions']} positions)")],
    )


ARTIFACT_CONTENT_CHARS = 9_000


def get_artifact(stores, args: dict) -> dict:
    """Read one retained artifact's content — the document the user is viewing
    (memo, thesis, IC verdict, research note). Lets the analyst answer
    questions ABOUT a report from the report itself."""
    aid = str(args.get("artifact_id") or "").strip()
    if not aid:
        return _error("artifact_id is required")
    art = stores.artifacts.get(aid)
    if not art:
        return _error(f"no retained artifact {aid!r}")
    body = (art.get("payload") or {}).get("body") or {}
    title = (body.get("title") or art.get("ticker") or art["kind"]).strip()
    content = (art.get("rendered_md") or "").strip()
    if not content:
        import json as _json
        content = _json.dumps(body, default=str)
    clipped = content[:ARTIFACT_CONTENT_CHARS]
    truncated = len(content) > len(clipped)
    summary = (
        f"Artifact {aid} — {art['kind']}"
        + (f" for {art['ticker']}" if art.get("ticker") else "")
        + f", created {str(art.get('created_at'))[:10]}: “{title}”."
        + (" Content truncated to the first "
           f"{ARTIFACT_CONTENT_CHARS} characters." if truncated else "")
        + "\n\n" + clipped
    )
    return _result(
        summary,
        data={"id": aid, "kind": art["kind"], "ticker": art.get("ticker"),
              "title": title, "truncated": truncated},
        citations=[_cite(art["kind"], title, ticker=art.get("ticker"), artifact_id=aid)],
    )


def get_thesis_health(stores, args: dict) -> dict:
    """Why a held position's thesis health is broken/watch/intact: the monitored
    watch items, their triggers, current values, and statuses. This is the data
    the morning Briefing's 'broken on KO' line is composed from."""
    from backend.domain import thesis_health as th
    from backend.workflows import thesis_health as th_wf

    ticker, _ = _resolve(stores, args.get("ticker"))
    if not ticker:
        return _error("ticker is required")
    plan = th_wf.active_plan(stores, ticker)
    if not plan:
        return _error(
            f"no retained thesis-health plan for {ticker} — it isn't a monitored "
            "position (monitoring begins from an approved memo's plan).")
    items = th_wf.plan_items(stores, plan["id"])
    if not items:
        return _error(f"{ticker} has a thesis-health plan but no watch items recorded.")

    quant = [i["status"] for i in items if i.get("tracking_mode") == "quantitative"]
    label = th.summary_label(quant) if quant else "Not Checked"
    buckets = {s: [i for i in items if i["status"] == s]
               for s in ("broken", "watch", "intact", "data_gap")}

    def _trigger(i):
        if i.get("metric") and i.get("threshold") is not None:
            return f"{i['comparator']} {_fmt(i['metric'], i['threshold'])}"
        return "—"

    def _current(i):
        if i.get("metric") and i.get("current_value") is not None:
            return _fmt(i["metric"], i["current_value"])
        return "—"

    def _desc(i):
        return f"{i['title']} ({i['metric']} now {_current(i)} vs trigger {_trigger(i)})"

    parts = [f"{ticker}'s thesis health is {label.upper()}."]
    if buckets["broken"]:
        parts.append("Breached — " + "; ".join(_desc(i) for i in buckets["broken"]) + ".")
    if buckets["watch"]:
        parts.append("On watch — " + "; ".join(_desc(i) for i in buckets["watch"]) + ".")
    tail = f"{len(buckets['intact'])} check(s) intact"
    if buckets["data_gap"]:
        tail += f", {len(buckets['data_gap'])} with a data gap"
    last = max((i.get("last_checked_at") or "" for i in items), default="")
    parts.append(tail + (f". Last checked {last[:10]}." if last else "."))

    columns = [{"key": "check", "label": "Check"}, {"key": "trigger", "label": "Trigger"},
               {"key": "current", "label": "Current"}, {"key": "status", "label": "Status"}]
    rows = [{
        "check": i["title"],
        "trigger": _trigger(i),
        "current": _current(i),
        "status": (i["status"] or "—").replace("_", " "),
    } for i in items]
    return _result(
        " ".join(parts),
        data={"ticker": ticker, "label": label, "items": items, "plan_id": plan["id"]},
        block={"type": "table", "title": f"{ticker} — thesis-health monitoring",
               "columns": columns, "rows": rows},
        citations=[_cite("thesis_health", f"{ticker} thesis-health plan", ticker=ticker)],
    )


def get_ownership(stores, args: dict) -> dict:
    from backend.services.ingest.beneficial import largest_holders

    ticker = str(args.get("ticker") or "").strip().upper()
    if not ticker:
        return _error("ticker is required")
    insiders = stores.bulk.ownership_for(ticker, kind="insider_transaction")
    holders = largest_holders(stores, ticker)
    if not insiders and not holders:
        return _error(f"no ownership history retained for {ticker} yet — insider "
                      "transactions and 13D/G holders arrive with data syncs")
    rows = [{
        "as_of": r["as_of"], "owner": r["owner_name"], "role": r["owner_role"] or "—",
        "type": r["txn_type"], "shares": f"{r['shares']:,.0f}" if r.get("shares") else "—",
        "value": _fmt("price", r["value"]) if r.get("value") else "—",
    } for r in insiders[:MAX_INSIDER_ROWS]]
    holder_text = "; ".join(
        f"{h['owner_name']}" + (f" {h['percent']:g}%" if h.get("percent") else "")
        for h in holders[:5] if h.get("owner_name")
    )
    summary = (f"{ticker} ownership: {len(insiders)} insider transactions retained"
               + (f"; largest holders: {holder_text}" if holder_text else
                  "; no 13D/G holders retained"))
    block = None
    if rows:
        block = {"type": "table", "title": f"{ticker} — insider transactions",
                 "columns": [{"key": "as_of", "label": "Date"}, {"key": "owner", "label": "Insider"},
                             {"key": "role", "label": "Role"}, {"key": "type", "label": "Type"},
                             {"key": "shares", "label": "Shares"}, {"key": "value", "label": "Value"}],
                 "rows": rows}
    return _result(
        summary,
        data={"ticker": ticker, "insiders": insiders[:MAX_INSIDER_ROWS], "largest_holders": holders},
        block=block,
        citations=[_cite("ownership", f"{ticker} ownership evidence (Forms 3/4/5, 13D/G)",
                         ticker=ticker)],
    )


def get_macro(stores, args: dict) -> dict:
    from backend.services import macro as macro_service

    series = str(args.get("series") or "").strip().upper()
    if series and series in macro_service.MACRO_SERIES:
        label, _kind = macro_service.MACRO_SERIES[series]
        points = macro_service.macro_history(stores, series, limit=260)
        if not points:
            return _error(f"no cached data for {series} yet — it arrives with the daily sync")
        rows = [{"date": p["date"], "value": f"{p['value']:.2f}"} for p in points[-12:]]
        summary = f"{label} ({series}): latest {points[-1]['value']:.2f} on {points[-1]['date']}"
        return _result(
            summary,
            data={"series": series, "points": points},
            block={"type": "table", "title": f"{label} — recent readings",
                   "columns": [{"key": "date", "label": "Date"},
                               {"key": "value", "label": label}],
                   "rows": rows},
            citations=[_cite("macro", f"{label} (FRED {series})")],
        )
    strip = macro_service.macro_strip(stores)
    if all(s["value"] is None for s in strip):
        return _error("no macro data cached yet — it arrives with the daily sync")
    rows = [{"label": s["label"], "value": s["display"], "as_of": s["as_of"] or "—"}
            for s in strip]
    summary = "Macro: " + ", ".join(f"{s['label']} {s['display']}" for s in strip)
    return _result(
        summary,
        data={"strip": strip},
        block={"type": "table", "title": "Macro snapshot (FRED)",
               "columns": [{"key": "label", "label": "Series"},
                           {"key": "value", "label": "Latest"},
                           {"key": "as_of", "label": "As of"}],
               "rows": rows},
        citations=[_cite("macro", "FRED macro series (local cache)")],
    )


def get_watchlist(stores, args: dict) -> dict:
    name = str(args.get("name") or "").strip()
    lists = stores.context.list_watchlists()
    if not lists:
        return _error("no watchlists or themes exist yet")
    wl = stores.context.watchlist_by_name(name) if name else None
    if name and not wl:
        return _error(f"no watchlist named {name!r} — existing: "
                      + ", ".join(w["name"] for w in lists))
    if not wl:
        summary = "Watchlists: " + "; ".join(
            f"{w['name']} ({w['kind']}, {len(w['tickers'])} tickers)" for w in lists)
        return _result(summary, data={"watchlists": lists})
    prices = stores.portfolio.prices()
    rows = []
    for t in wl["tickers"]:
        ent = stores.identity.resolve_ticker(t)
        latest = _enriched_latest(stores, t, ent)
        rows.append({"ticker": t, "price": _fmt("price", prices.get(t)),
                     "momentum_3m": _fmt("momentum_3m", latest.get("momentum_3m")),
                     "pe": _fmt("pe", latest.get("pe")),
                     "fcf_yield": _fmt("fcf_yield", latest.get("fcf_yield"))})
    summary = (f"{wl['name']} ({wl['kind']}): " + ", ".join(wl["tickers"]))
    return _result(
        summary,
        data={"watchlist": wl},
        block={"type": "table", "title": f"{wl['name']} — watchlist",
               "columns": [{"key": "ticker", "label": "Ticker"},
                           {"key": "price", "label": "Price"},
                           {"key": "momentum_3m", "label": "3M Momentum"},
                           {"key": "pe", "label": "P/E"},
                           {"key": "fcf_yield", "label": "FCF Yield"}],
               "rows": rows},
        citations=[_cite("watchlist", f"{wl['name']} watchlist")],
    )


def search_archive(stores, args: dict) -> dict:
    query = str(args.get("query") or "")
    known = set(stores.identity.known_tickers())
    mentioned, _unknown = archive_qa.ticker_mentions(query, known)
    records = archive_qa.gather_records(stores, mentioned)
    if not records:
        return _error("no retained archive records match — the archive fills as "
                      "screener runs, theses, IC verdicts, memos, and ledger entries accumulate")
    lines = [f"[{i}] {r['date']} {r['kind']}: {r['label']}"
             for i, r in enumerate(records[:12], start=1)]
    citations = [
        _cite(r["kind"], f"{r['label']} ({r['date']})", ticker=r.get("ticker"),
              artifact_id=r.get("artifact_id"))
        for r in records[:8]
    ]
    return _result(
        "Archive records:\n" + "\n".join(lines),
        data={"records": records[:12], "tickers": mentioned},
        citations=citations,
    )


# --- registry ----------------------------------------------------------------------

TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in (
    ToolSpec(
        "get_company_financials",
        "Retained financial statements and headline metrics for one ticker.",
        {"ticker": {"type": "string", "required": True},
         "period_type": {"type": "string", "required": False, "desc": "annual|quarterly (default annual)"}},
        get_company_financials,
    ),
    ToolSpec(
        "get_metric",
        "History of one metric for one ticker (e.g. roic, gross_margin, revenue).",
        {"ticker": {"type": "string", "required": True},
         "metric": {"type": "string", "required": True, "desc": "metric catalog id"},
         "period_type": {"type": "string", "required": False, "desc": "annual|quarterly"},
         "limit": {"type": "integer", "required": False}},
        get_metric,
    ),
    ToolSpec(
        "get_price_history",
        "Stored daily closes for one ticker over a range; returns a chart.",
        {"ticker": {"type": "string", "required": True},
         "range": {"type": "string", "required": False, "desc": "1m|6m|1y|5y (default 1y)"}},
        get_price_history,
    ),
    ToolSpec(
        "compare_companies",
        "Latest metrics side by side for 2-6 tickers, or a ticker vs its "
        "industry peers via peers_of.",
        {"tickers": {"type": "array of strings", "required": False},
         "peers_of": {"type": "string", "required": False,
                      "desc": "compare this ticker against its peer group"},
         "metrics": {"type": "array of strings", "required": False,
                     "desc": "metric catalog ids (default headline set)"}},
        compare_companies,
    ),
    ToolSpec(
        "screen_universe",
        "Ad-hoc screen of the universe against metric rules. Read-only: never "
        "changes the Constitution or creates runs. Percent values are decimals "
        "(15% -> 0.15).",
        {"criteria": {"type": "array", "required": True,
                      "desc": '[{"metric", "operator" (one of >,>=,<,<=,==), "value"}]'},
         "sort_by": {"type": "string", "required": False, "desc": "metric to rank by"},
         "limit": {"type": "integer", "required": False}},
        screen_universe,
    ),
    ToolSpec(
        "get_portfolio_summary",
        "Current holdings with P&L, weights, and thesis health, plus totals.",
        {},
        get_portfolio_summary,
    ),
    ToolSpec(
        "get_artifact",
        "Read one retained artifact's full content by id (memo, thesis, IC "
        "verdict, research note). Use when the user asks about 'this report/"
        "memo/note' they are viewing, or about a specific artifact's content.",
        {"artifact_id": {"type": "string", "required": True}},
        get_artifact,
    ),
    ToolSpec(
        "get_thesis_health",
        "Why a held position's thesis health is broken/watch/intact: the "
        "monitored watch items, their triggers, current values, and statuses. "
        "Use for 'why did X's thesis health break', 'what's breaking on X'.",
        {"ticker": {"type": "string", "required": True}},
        get_thesis_health,
    ),
    ToolSpec(
        "get_ownership",
        "Insider transactions (Forms 3/4/5) and largest 13D/G holders for one ticker.",
        {"ticker": {"type": "string", "required": True}},
        get_ownership,
    ),
    ToolSpec(
        "get_macro",
        "Macro snapshot or one series history from the local FRED cache "
        "(DGS10, DFF, UNRATE, CPIAUCSL).",
        {"series": {"type": "string", "required": False,
                    "desc": "FRED series id; omit for the full snapshot"}},
        get_macro,
    ),
    ToolSpec(
        "get_watchlist",
        "List watchlists/themes, or show one by name with snapshot metrics.",
        {"name": {"type": "string", "required": False}},
        get_watchlist,
    ),
    ToolSpec(
        "search_archive",
        "Retained research history (artifacts, screener runs, verdicts, ledger) "
        "matching a query.",
        {"query": {"type": "string", "required": True}},
        search_archive,
    ),
)}


def catalog_text() -> str:
    """Tool catalog rendered for the analyst system prompt."""
    lines = []
    for spec in TOOLS.values():
        args = ", ".join(
            f"{name}{'' if meta.get('required') else '?'}: {meta['type']}"
            + (f" ({meta['desc']})" if meta.get("desc") else "")
            for name, meta in spec.args.items()
        )
        lines.append(f"- {spec.name}({args or 'no args'}): {spec.description}")
    return "\n".join(lines)


def execute(stores, name: str, args: dict | None) -> dict:
    """Validate and run one tool; errors become ToolResults, never exceptions."""
    spec = TOOLS.get(name)
    if spec is None:
        return _error(f"unknown tool {name!r} — available: {', '.join(TOOLS)}")
    args = args if isinstance(args, dict) else {}
    missing = [a for a, meta in spec.args.items() if meta.get("required") and not args.get(a)]
    if missing:
        return _error(f"{name}: missing required argument(s) {', '.join(missing)}")
    try:
        return spec.fn(stores, args)
    except Exception as exc:  # tool bugs degrade to a model-visible error step
        return _error(f"{name} failed: {exc}")
