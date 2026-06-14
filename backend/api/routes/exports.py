"""CSV export routes: portfolio, company financials, latest screener run,
industry constituents. Raw stored values (decimals, dollars) — spreadsheets
do their own formatting. Local reads only."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.stores import get_stores

router = APIRouter()


def _csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@router.get("/export/portfolio.csv")
async def export_portfolio():
    from backend.services.portfolio_service import PortfolioService

    rows = PortfolioService(get_stores()).holdings_view()
    return _csv_response(
        f"fundops-portfolio-{_today()}.csv",
        ["ticker", "shares", "avg_cost", "price", "market_value",
         "unrealized_pnl", "weight", "position_type", "thesis_health"],
        [[h["ticker"], h["shares"], h["avg_cost"], h["price"], h["market_value"],
          h["unrealized_pnl"], h["weight"], h["position_type"],
          h["thesis_health_label"]] for h in rows],
    )


@router.get("/export/financials/{ticker}.csv")
async def export_financials(ticker: str, period_type: str = "annual"):
    stores = get_stores()
    ent = stores.identity.resolve_ticker(ticker.upper())
    if not ent:
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    if period_type not in ("annual", "quarterly"):
        period_type = "annual"
    # Route through the SAME normalized/density-filtered builder the Company Page
    # uses, so exports don't leak the orphan/near-blank columns the raw store
    # produces (fiscal-basis migrations, single-metric legacy period_ends).
    from backend.domain import statements

    raw = stores.financial.periods(ent["id"], period_type)
    cols = statements.statement_columns(raw, period_type)
    metrics: list[str] = []
    for c in cols:
        for m in c["metrics"]:
            if m not in metrics:
                metrics.append(m)  # canonical statement order, deduped
    return _csv_response(
        f"{ticker.upper()}-financials-{period_type}-{_today()}.csv",
        ["metric"] + [c["period_end"] for c in cols],
        [[m] + [c["metrics"].get(m) for c in cols] for m in metrics],
    )


@router.get("/export/screener.csv")
async def export_screener():
    stores = get_stores()
    run = stores.runs.latest_run("screener")
    if not run:
        raise HTTPException(status_code=404, detail="no completed screener run yet")
    rows = stores.ws.query(
        "SELECT ticker, passed, rank, score, selected FROM screener_results "
        "WHERE run_id = ? ORDER BY passed DESC, rank IS NULL, rank",
        (run["id"],),
    )
    return _csv_response(
        f"fundops-screener-{str(run.get('started_at'))[:10]}.csv",
        ["ticker", "passed", "rank", "score", "selected"],
        [[r["ticker"], r["passed"], r["rank"], r["score"], r["selected"]] for r in rows],
    )


@router.get("/export/industry.csv")
async def export_industry(sector: str | None = None, industry: str | None = None):
    from backend.services.research_hub import industry_dashboard

    if not sector and not industry:
        raise HTTPException(status_code=400, detail="sector or industry is required")
    dash = industry_dashboard(get_stores(), sector, industry)
    metrics = dash["constituent_metrics"]
    # Filename lands in a response header — keep it to a safe charset.
    raw = (industry or sector or "group").replace(" ", "-").lower()
    name = re.sub(r"[^a-z0-9_-]", "", raw) or "group"
    return _csv_response(
        f"fundops-industry-{name}-{_today()}.csv",
        ["ticker", "name"] + list(metrics),
        [[c["ticker"], c["name"]] + [c.get(m) for m in metrics]
         for c in dash["constituents"]],
    )
