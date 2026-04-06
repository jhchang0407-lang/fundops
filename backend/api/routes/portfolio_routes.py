"""Portfolio routes — holdings management with lot-based tracking."""

from collections import defaultdict
from datetime import date
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.deps import get_db

router = APIRouter()


class PositionIn(BaseModel):
    ticker: str
    shares: float
    cost_basis: float
    date: Optional[str] = ""
    type: Optional[str] = "core"


class SavePositionsRequest(BaseModel):
    positions: List[PositionIn]
    cash: Optional[float] = None  # Cash balance (not invested)


@router.get("/portfolio")
async def get_portfolio():
    """Get current holdings."""
    import json as _json
    db = get_db()
    snapshot = db.get_latest_portfolio_snapshot()
    if not snapshot:
        return {"holdings": [], "total_value": 0}
    for field in ("holdings", "alerts"):
        val = snapshot.get(field)
        if isinstance(val, str):
            try:
                snapshot[field] = _json.loads(val)
            except Exception:
                snapshot[field] = []
        elif val is None:
            snapshot[field] = []
    # Enrich holdings with sector/industry from tickers table
    for h in (snapshot.get("holdings") or []):
        if not h.get("sector"):
            row = db.conn.execute(
                "SELECT sector, industry FROM tickers WHERE ticker = ?",
                (h.get("ticker", ""),)
            ).fetchone()
            if row:
                h["sector"] = row[0] or ""
                h["industry"] = row[1] or ""
    return snapshot


@router.post("/portfolio/positions")
async def save_positions(req: SavePositionsRequest):
    """Save portfolio positions with lot-based tracking.

    Multiple rows with the same ticker are treated as separate lots.
    The system aggregates them into one combined position per ticker
    with weighted average cost basis, while preserving individual lots
    for date tracking.

    After saving, fetches current prices so P&L is returned immediately.
    """
    db = get_db()
    today = date.today().isoformat()

    # Group lots by ticker
    lots_by_ticker: dict[str, list[dict]] = defaultdict(list)
    for p in req.positions:
        ticker = p.ticker.strip().upper()
        if not ticker or p.shares <= 0:
            continue
        lots_by_ticker[ticker].append({
            "shares": p.shares,
            "cost_basis": p.cost_basis,
            "date": p.date or today,
        })

    # Build aggregated holdings with lots preserved
    holdings = []
    for ticker, lots in lots_by_ticker.items():
        total_shares = sum(lot["shares"] for lot in lots)
        total_cost = sum(lot["shares"] * lot["cost_basis"] for lot in lots)
        avg_cost = total_cost / total_shares if total_shares > 0 else 0

        holdings.append({
            "ticker": ticker,
            "shares": round(total_shares, 4),
            "cost_basis": round(avg_cost, 4),
            "lots": lots,
            "type": "core",
        })

    # Upsert each ticker as owned and enrich with sector/industry from DB
    for h in holdings:
        db.upsert_ticker(h["ticker"], is_owned=True)
        # Look up sector/industry from tickers table
        row = db.conn.execute(
            "SELECT sector, industry FROM tickers WHERE ticker = ?", (h["ticker"],)
        ).fetchone()
        if row:
            h["sector"] = row[0] or ""
            h["industry"] = row[1] or ""

    # Fetch current prices to compute P&L immediately
    tickers = [h["ticker"] for h in holdings]
    prices = await _fetch_prices(tickers)

    # Drop tickers that don't exist (no price found from any source)
    invalid_tickers = [t for t in tickers if t not in prices]
    if invalid_tickers:
        holdings = [h for h in holdings if h["ticker"] not in invalid_tickers]

    total_value = 0
    total_cost_all = 0
    for h in holdings:
        price = prices.get(h["ticker"], h["cost_basis"])
        h["current_price"] = round(price, 2)
        h["market_value"] = round(h["shares"] * price, 2)
        cost_value = h["shares"] * h["cost_basis"]
        h["pnl"] = round(h["market_value"] - cost_value, 2)
        h["pnl_pct"] = round((h["pnl"] / cost_value * 100) if cost_value > 0 else 0, 1)
        total_value += h["market_value"]
        total_cost_all += cost_value

    # Include cash in total portfolio value for weight calculations
    cash = round(req.cash, 2) if req.cash is not None else None
    portfolio_total = total_value + (cash or 0)

    # Compute weights (as % of total portfolio including cash)
    for h in holdings:
        h["weight"] = round(h["market_value"] / portfolio_total * 100, 1) if portfolio_total > 0 else 0

    # Save snapshot
    db.record_portfolio_snapshot(
        snapshot_date=today,
        total_value=round(portfolio_total, 2),
        cash=cash,
        holdings=holdings,
        alerts=[],
        daily_pnl=round(total_value - total_cost_all, 2),
    )

    result = {
        "saved": len(holdings),
        "holdings": holdings,
        "total_value": round(portfolio_total, 2),
        "total_pnl": round(total_value - total_cost_all, 2),
        "cash": cash,
    }
    if invalid_tickers:
        result["removed_tickers"] = invalid_tickers
        result["removed_reason"] = "Ticker not found — no price data from any source"
    return result


@router.get("/portfolio/history")
async def get_portfolio_history():
    """Historical portfolio snapshots (last 30 days)."""
    import json as _json
    db = get_db()
    try:
        rows = db.conn.execute(
            "SELECT snapshot_date, total_value, cash, daily_pnl FROM portfolio_snapshots "
            "ORDER BY snapshot_date DESC LIMIT 30"
        ).fetchall()
        history = [
            {
                "date": row[0],
                "total_value": row[1],
                "cash": row[2],
                "daily_pnl": row[3],
            }
            for row in rows
        ]
        return {"history": history}
    except Exception:
        return {"history": []}


async def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of tickers. Best-effort, async."""
    prices = {}
    if not tickers:
        return prices

    # Try yfinance first (free, fast)
    try:
        from backend.api.deps import get_yfinance
        yf = get_yfinance()
        if yf:
            result = await yf.get_quotes(tickers)
            if result and hasattr(result, "data") and result.data:
                for q in (result.data if isinstance(result.data, list) else [result.data]):
                    t = q.get("symbol") or q.get("ticker", "")
                    p = q.get("price") or q.get("regularMarketPrice", 0)
                    if t and p:
                        prices[t] = float(p)
    except Exception as e:
        import logging
        logging.getLogger("fundops.portfolio").debug(f"yfinance price fetch failed: {e}")

    # FMP fallback for any missing
    if len(prices) < len(tickers):
        try:
            from backend.api.deps import get_fmp
            fmp = get_fmp()
            if fmp:
                missing = [t for t in tickers if t not in prices]
                result = await fmp.get_quotes(missing)
                if result and hasattr(result, "data") and result.data:
                    for q in (result.data if isinstance(result.data, list) else [result.data]):
                        t = q.get("symbol") or q.get("ticker", "")
                        p = q.get("price", 0)
                        if t and p:
                            prices[t] = float(p)
        except Exception as e:
            import logging
            logging.getLogger("fundops.portfolio").debug(f"FMP price fetch failed: {e}")

    return prices
