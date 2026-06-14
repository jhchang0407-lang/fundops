"""Company Page routes: identity strip + workflow-map lanes, financials,
thesis health (api-contract). Read-only projections over retained records —
no fetches or refreshes triggered by page views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.workspace import loads
from backend.domain import labels
from backend.services import company_factsheet
from backend.stores import get_stores
from backend.workflows import thesis_health

router = APIRouter()

LANE_LIMIT = 10
PRICE_RANGE_DAYS = {"1m": 31, "6m": 183, "1y": 366, "5y": 1830}
STAGE_FOR_KIND = {"screener_snapshot": "screener", "thesis": "thesis",
                  "ic_verdict": "ic_review", "investment_memo": "memo"}


def _known(stores, ticker: str) -> bool:
    """Known ticker = entity or any retained history (artifacts, ledger,
    screener work)."""
    return bool(
        stores.identity.resolve_ticker(ticker)
        or stores.artifacts.for_ticker(ticker, limit=1)
        or stores.portfolio.lots(ticker)
        or stores.portfolio.sales(ticker)
        or stores.artifacts.screener_history_for_ticker(ticker, limit=1)
    )


@router.get("/company/{ticker}")
async def company_page(ticker: str):
    ticker = ticker.upper()
    stores = get_stores()
    if not _known(stores, ticker):
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    ent = stores.identity.resolve_ticker(ticker) or {}
    arts = [a for a in stores.artifacts.for_ticker(ticker, limit=50)
            if a["kind"] in STAGE_FOR_KIND]
    latest_stage = STAGE_FOR_KIND.get(arts[0]["kind"]) if arts else None
    screener_history = stores.artifacts.screener_history_for_ticker(ticker, limit=LANE_LIMIT)
    if latest_stage is None and screener_history:
        latest_stage = "screener"
    latest_ic = stores.artifacts.latest_ic_verdict(ticker)
    holding = stores.portfolio.holding(ticker)
    identity = {
        "ticker": ticker,
        "name": ent.get("name") or ticker,
        "sector": ent.get("sector"),
        "industry": ent.get("industry"),
        "price": stores.portfolio.prices().get(ticker),
        "latest_stage": latest_stage,
        "latest_verdict": latest_ic["verdict"] if latest_ic else None,
        "owned": holding is not None,
        "entity_id": ent.get("id"),
        # Phantom quarantine (#4): a delisted/dataless name is reachable by
        # deep-link but not actively researched — surface why instead of a wall
        # of nulls. 'active' for the overwhelming majority.
        "status": ent.get("status") or "active",
        "status_reason": ent.get("status_reason"),
    }
    return {"identity": identity, "lanes": _lanes(stores, ticker, screener_history)}


def _kn(label: str, value) -> dict:
    return {"label": label, "value": value}


def _detail(key_numbers: list[dict], extra: dict | None = None) -> dict | None:
    """Milestone preview-drawer body: {key_numbers: [{label, value}], extra?}."""
    key_numbers = [k for k in key_numbers if k.get("value") not in (None, "", "—")]
    if not key_numbers and not extra:
        return None
    out: dict = {"key_numbers": key_numbers}
    if extra:
        out["extra"] = extra
    return out


def _dollars(value) -> str | None:
    return labels.format_metric_value("price", value) if value is not None else None


def _screener_milestones(stores, screener_history: list[dict]) -> list[dict]:
    # Rank context ("#1 of N") comes from the per-run count of passing rows.
    run_ids = {r["run_id"] for r in screener_history if r.get("run_id")}
    totals: dict[str, int] = {}
    for rid in run_ids:
        row = stores.ws.query_one(
            "SELECT COUNT(*) AS n FROM screener_results WHERE run_id = ? AND passed = 1",
            (rid,))
        totals[rid] = row["n"] if row else 0
    out = []
    for r in screener_history:
        passed = bool(r["passed"])
        rank, total = r.get("rank"), totals.get(r.get("run_id")) or None
        evidence = [e for e in (r.get("pass_evidence") or []) if isinstance(e, dict)]
        fails = [f for f in (r.get("fail_reasons") or []) if isinstance(f, dict)]
        if passed and rank:
            title = f"Screened — rank #{rank}" + (f" of {total}" if total else "")
        elif passed:
            title = "Passed screen"
        else:
            title = "Did not pass screen"
        if passed:
            summary = labels.screener_summary(
                evidence, rank=rank, total=total,
                components=r.get("ranking_components"))
        else:
            summary = labels.screener_fail_summary(fails)
        key_numbers = []
        if rank:
            key_numbers.append(_kn("Rank", f"#{rank}" + (f" of {total}" if total else "")))
        if isinstance(r.get("score"), (int, float)):
            key_numbers.append(_kn("Screen score", f"{r['score']:.2f}"))
        for e in evidence:
            key_numbers.append(labels.evidence_key_number(e))
        for f in fails:
            if f.get("metric") or f.get("criterion"):
                key_numbers.append(labels.evidence_key_number(f))
        out.append({"date": r.get("run_started_at"), "title": title,
                    "status": "selected" if r.get("selected") else
                              ("passed" if passed else "failed"),
                    "artifact_id": r.get("snapshot_artifact_id"),
                    "kind": "screener_result", "summary": summary,
                    "detail": _detail(key_numbers)})
    return out[:LANE_LIMIT]


def _thesis_milestones(stores, ticker: str) -> list[dict]:
    out = []
    price_mark = stores.portfolio.prices().get(ticker)
    for meta in stores.artifacts.for_ticker(ticker, kind="thesis", limit=LANE_LIMIT):
        art = stores.artifacts.get(meta["id"]) or {}
        body = ((art.get("payload") or {}).get("body") or {})
        rp = body.get("return_potential") or {}
        expected = rp.get("expected_return_pct")
        title = "Thesis"
        if isinstance(expected, (int, float)):
            title = f"Thesis — {expected:+.1f}% expected"
        price = body.get("price") if isinstance(body.get("price"), (int, float)) else price_mark
        key_numbers = [
            _kn("Price", _dollars(price)),
            _kn("Fair value", _dollars(rp.get("fair_value"))),
        ]
        if isinstance(expected, (int, float)):
            key_numbers.append(_kn("Expected return", f"{expected:+.1f}%"))
        components = rp.get("components") or {}
        if isinstance(components, dict):
            top = sorted(((k, v) for k, v in components.items()
                          if isinstance(v, (int, float))),
                         key=lambda kv: -abs(kv[1]))[:2]
            for name, value in top:
                key_numbers.append(_kn(name.replace("_", " ").capitalize(), f"{value:+.1f}%"))
        out.append({"date": meta["created_at"], "title": title,
                    "status": "completed", "artifact_id": meta["id"],
                    "kind": "thesis", "summary": body.get("summary"),
                    "detail": _detail(key_numbers)})
    return out


def _ic_milestones(stores, ticker: str) -> list[dict]:
    out = []
    for r in stores.ws.query(
            "SELECT * FROM ic_verdicts WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
            (ticker, LANE_LIMIT)):
        gate, cutoff = r["gate_score"], r["cutoff"]
        title = "IC Review" + (f" — {gate:.0f}/100" if gate is not None else "")
        findings = [f for f in (loads(r["hurdle_findings"]) or []) if isinstance(f, dict)]
        met = sum(1 for f in findings if f.get("met"))
        key_numbers = []
        for label, col in (("Conviction", "conviction"),
                           ("Constitution fit", "constitution_fit"),
                           ("Data quality", "data_quality")):
            if r[col] is not None:
                key_numbers.append(_kn(label, f"{r[col]:.0f}/100"))
        if gate is not None:
            key_numbers.append(_kn("Gate score", f"{gate:.0f}" + (
                f" vs cutoff {cutoff:.0f}" if cutoff is not None else "")))
        if findings:
            key_numbers.append(_kn("Hurdles", f"{met} met, {len(findings) - met} missed"))
        extra = {"override": True} if r["is_override"] else None
        out.append({"date": r["created_at"], "title": title, "status": r["verdict"],
                    "artifact_id": r["artifact_id"], "kind": "ic_verdict",
                    "summary": r["rationale"],
                    "detail": _detail(key_numbers, extra)})
    return out


def _memo_milestones(stores, ticker: str) -> list[dict]:
    out = []
    for meta in stores.artifacts.for_ticker(ticker, kind="investment_memo", limit=LANE_LIMIT):
        art = stores.artifacts.get(meta["id"]) or {}
        body = ((art.get("payload") or {}).get("body") or {})
        sections = body.get("sections") or {}
        decision = body.get("decision") or (
            (sections.get("decision_summary") or {}).get("fields") or {}).get("decision")
        val = body.get("valuation") or {}
        fair_value = val.get("fair_value_base")
        upside, downside = val.get("upside_pct"), val.get("downside_pct")
        plan_items = [p for p in (body.get("monitoring_plan_items") or [])
                      if isinstance(p, dict)]
        summary_bits = []
        if decision:
            summary_bits.append(f"Decision: {decision.replace('_', ' ')}.")
        if isinstance(fair_value, (int, float)):
            line = f"Fair value {_dollars(fair_value)}"
            if isinstance(upside, (int, float)):
                line += f" ({upside:+.1f}% vs price)"
            summary_bits.append(line + ".")
        if plan_items:
            summary_bits.append(
                f"{len(plan_items)} watch item{'s' if len(plan_items) != 1 else ''} "
                f"under monitoring.")
        key_numbers = [
            _kn("Decision", decision.replace("_", " ") if decision else None),
            _kn("Fair value", _dollars(fair_value)),
            _kn("Upside", f"{upside:+.1f}%" if isinstance(upside, (int, float)) else None),
            _kn("Downside", f"{downside:+.1f}%" if isinstance(downside, (int, float)) else None),
            _kn("Watch items", str(len(plan_items)) if plan_items else None),
        ]
        out.append({"date": meta["created_at"], "title": "Investment Memo",
                    "status": decision, "artifact_id": meta["id"],
                    "kind": "investment_memo",
                    "summary": " ".join(summary_bits) or None,
                    "detail": _detail(key_numbers)})
    return out


def _portfolio_milestones(stores, ticker: str) -> list[dict]:
    out = []
    for lot in stores.portfolio.lots(ticker):
        shares, cost = lot["shares"], lot["cost_basis"]
        total = shares * cost if isinstance(cost, (int, float)) else None
        out.append({"date": lot["purchase_date"],
                    "title": f"Bought {shares:g} @ {_dollars(cost)}",
                    "status": None, "kind": "purchase", "summary": lot.get("note"),
                    "detail": _detail([
                        _kn("Shares", f"{shares:g}"),
                        _kn("Price", _dollars(cost)),
                        _kn("Total value", _dollars(total)),
                    ])})
    for sale in stores.portfolio.sales(ticker):
        shares, price, pnl = sale["shares"], sale["price"], sale.get("realized_pnl")
        total = shares * price if isinstance(price, (int, float)) else None
        out.append({"date": sale["sale_date"],
                    "title": f"Sold {shares:g} @ {_dollars(price)}",
                    "status": None, "kind": "sale", "summary": sale.get("note"),
                    "detail": _detail([
                        _kn("Shares", f"{shares:g}"),
                        _kn("Price", _dollars(price)),
                        _kn("Proceeds", _dollars(total)),
                        _kn("Realized P&L", f"{pnl:+,.2f}" if pnl is not None else None),
                    ])})
    out.sort(key=lambda m: m["date"] or "", reverse=True)
    return out[:LANE_LIMIT]


def _lanes(stores, ticker: str, screener_history: list[dict]) -> list[dict]:
    return [
        {"lane": "screener", "milestones": _screener_milestones(stores, screener_history)},
        {"lane": "thesis", "milestones": _thesis_milestones(stores, ticker)},
        {"lane": "ic_review", "milestones": _ic_milestones(stores, ticker)},
        {"lane": "memo", "milestones": _memo_milestones(stores, ticker)},
        {"lane": "portfolio", "milestones": _portfolio_milestones(stores, ticker)},
    ]


@router.get("/company/{ticker}/financials")
async def company_financials(ticker: str):
    ticker = ticker.upper()
    stores = get_stores()
    ent = stores.identity.resolve_ticker(ticker)
    if not ent:
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    sheet = company_factsheet.build_company_fact_sheet(
        stores, ticker, profile="company_page", entity_id=ent["id"],
    )
    period_ends = ([p["period_end"] for p in sheet["annual"]["periods"]]
                   + [p["period_end"] for p in sheet["quarterly"]["periods"]])
    return {
        "snapshot": sheet["snapshot"],
        "snapshot_basis": sheet["snapshot_basis"],
        "annual": sheet["annual"],
        "quarterly": sheet["quarterly"],
        "as_of": max(period_ends) if period_ends else None,
        "coverage": sheet["coverage"],
        "data_quality": sheet["data_quality"],
        "source_metadata": sheet["source_metadata"],
        "sources": sheet["source_drilldowns"],
    }


@router.get("/company/{ticker}/financials/source")
async def company_financial_source(
    ticker: str, metric: str, period_end: str | None = None,
    period_type: str | None = None,
):
    ticker = ticker.upper()
    stores = get_stores()
    ent = stores.identity.resolve_ticker(ticker)
    if not ent:
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    sheet = company_factsheet.build_company_fact_sheet(
        stores, ticker, profile="source_drilldown", entity_id=ent["id"],
    )
    if period_end or period_type:
        out = stores.financial.source_drilldown(ent["id"], metric, period_end, period_type)
    else:
        out = sheet["source_drilldowns"].get(metric) or stores.financial.source_drilldown(
            ent["id"], metric)
    if not out:
        raise HTTPException(status_code=404, detail=f"no source retained for {metric}")
    return {"ticker": ticker, "source": out}


@router.get("/company/{ticker}/thesis-health")
async def company_thesis_health(ticker: str):
    return thesis_health.thesis_health_view(get_stores(), ticker)


@router.get("/company/{ticker}/prices")
async def company_prices(ticker: str, range: str = "1y"):
    """Price-history chart rows from the bulk price store (ADR-0059).
    An unknown or history-less ticker returns an empty list, never 404."""
    ticker = ticker.upper()
    stores = get_stores()
    try:
        from backend.services.ingest.prices import price_chart  # guarded: parallel module
        rows = price_chart(stores, ticker, range)
    except ImportError:
        start = (datetime.now(timezone.utc)
                 - timedelta(days=PRICE_RANGE_DAYS.get(range, 366))).date().isoformat()
        rows = stores.bulk.price_range(ticker, start=start)
    prices = [{"date": r["date"], "close": r["close"], "volume": r.get("volume")}
              for r in rows]
    # Set a reason ONLY for a genuinely dataless/delisted name (known entity with
    # zero retained price ever) — so the chart explains itself instead of nulling
    # every price-derived metric in silence. Transient/loading empties stay null
    # so the chart simply hides until the sync lands.
    empty_reason = None
    if not prices and stores.identity.resolve_ticker(ticker) and not stores.bulk.latest_close(ticker):
        empty_reason = (
            "No price history is retained for this ticker — it may be delisted or "
            "acquired, so market cap, P/E, and FCF yield can't be computed.")
    return {"ticker": ticker, "range": range, "prices": prices,
            "empty_reason": empty_reason}


class CompanyResearchIn(BaseModel):
    kind: str   # risk_diff | mdna_note


@router.post("/company/{ticker}/research")
async def company_research(ticker: str, body: CompanyResearchIn):
    """Filing-text research run for one ticker (Phase 4 harness): risk-factor
    YoY diff or a cited MD&A note. Produces a filing_note artifact."""
    from backend.workflows import research_runs

    try:
        out = await research_runs.run_company_note(get_stores(), ticker.upper(), body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("error", "run failed"))
    return out


@router.get("/company/{ticker}/news")
async def company_news(ticker: str):
    """Live headlines (yfinance, briefly cached). Context only — explicitly
    not retained as workspace evidence."""
    from backend.services.news import company_news as fetch

    return {"ticker": ticker.upper(), **(await fetch(ticker.upper()))}


@router.get("/company/{ticker}/peers")
async def company_peers(ticker: str):
    """Deterministic peer comparison grid (same industry, fallback sector,
    nearest by market cap). Local-only read."""
    from backend.services.research_hub import peers_for, profile_for

    stores = get_stores()
    t = ticker.upper()
    ent = stores.identity.resolve_ticker(t)
    profile = profile_for([ent] if ent else [])
    peers = peers_for(stores, t)
    return {"ticker": t, "metrics": list(profile["constituents"]),
            "na_metrics": list(profile["na"]), "peers": peers}


@router.get("/company/{ticker}/events")
async def company_events(ticker: str):
    """Merged event timeline: stored calendar events (earnings/dividends),
    filing events from the retained index, insider-transaction clusters.
    Local-only read."""
    from backend.services.ingest.events import events_empty_reason, events_view

    stores = get_stores()
    t = ticker.upper()
    events = events_view(stores, t)
    out = {"ticker": t, "events": events}
    if not events:
        out["empty_reason"] = events_empty_reason(stores, t)
    return out


@router.get("/company/{ticker}/ownership")
async def company_ownership(ticker: str):
    """Ownership evidence (ADR-0059/0061): insider transactions from the
    quarterly Form 3/4/5 data sets and largest holders from Schedule 13D/13G
    filings. Institutional (13F) rows are not ingested at baseline."""
    from backend.services.ingest.beneficial import largest_holders

    stores = get_stores()
    rows = stores.bulk.ownership_for(ticker.upper(), kind="insider_transaction")
    insiders = [{"as_of": r["as_of"], "owner_name": r["owner_name"],
                 "owner_role": r["owner_role"], "txn_type": r["txn_type"],
                 "shares": r["shares"], "value": r["value"]} for r in rows]
    holders = largest_holders(stores, ticker.upper())
    out: dict = {"insiders": insiders, "largest_holders": holders}
    if not insiders and not holders:
        out["empty_reason"] = (
            "No ownership history retained yet — insider transactions and 13D/G "
            "holders arrive with data syncs."
        )
    elif not holders:
        # Insiders present but no 13D/G: explain the empty panel rather than
        # silently hiding it (it was rendering blank for KO/AAPL).
        out["holders_reason"] = (
            "No 5%+ beneficial-owner schedules (13D/G) retained for this ticker yet — "
            "these are filed only when a holder crosses 5%, and arrive as the filings "
            "index syncs."
        )
    # 13F decision (DROP-PANEL): institutional holdings are not ingested — 13F
    # INFO TABLE filings key positions by CUSIP and there is no local CUSIP→ticker
    # map. Surface the reason instead of a permanently-empty hardcoded panel.
    out["institutions_reason"] = (
        "Institutional (13F) holdings are not ingested — 13F INFO TABLE filings key "
        "positions by CUSIP and there is no local CUSIP→ticker map."
    )
    return out
