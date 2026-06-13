"""Portfolio application service (ADR-0033, ADR-0035, ADR-0041).

Wraps the ledger store with explicit command intents (add lot, record sale,
price refresh) and owns Automatic Portfolio Thesis Coverage: a held ticker
without Fresh Portfolio Thesis Coverage (thesis-health-ready memo ≤90 days)
gets a coverage memo queued on save/sync — never on page load. The price
refresh is strictly a Portfolio Price and P&L Refresh: it never touches
memo-backed thesis health.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

COVERAGE_FRESH_DAYS = 90
COVERAGE_WORK_KIND = "coverage_memo"
COVERAGE_PRIORITY = 4
DEFAULT_CONCENTRATION_FLAG_PCT = 20.0
DRAWDOWN_FLAG_FRACTION = -0.25


def _age_days(ts: str) -> float:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _reject_future_date(date_str: str, what: str) -> None:
    """The ledger records what happened — a future-dated entry would also
    corrupt flow-adjusted return math (flows attach to future price bars)."""
    from backend.domain.ledger import LedgerError

    today = datetime.now(timezone.utc).date().isoformat()
    if str(date_str)[:10] > today:
        raise LedgerError(f"{what} date {str(date_str)[:10]} is in the future")


class PortfolioService:
    def __init__(self, stores):
        self.stores = stores

    # --- ledger commands ----------------------------------------------------------
    def add_lot(self, ticker: str, shares: float, cost_basis: float, purchase_date: str,
                position_type: str | None = None, note: str | None = None) -> dict:
        """Portfolio Entry Intent = buy. Saving a lot is the explicit action
        that triggers a coverage check (never page load)."""
        _reject_future_date(purchase_date, "purchase")
        ticker = ticker.upper()
        ent = self.stores.identity.ensure_entity(ticker)
        lot_id = self.stores.portfolio.add_lot(
            ticker, shares, cost_basis, purchase_date,
            entity_id=ent["id"], position_type=position_type, note=note,
        )
        coverage_state = self.ensure_coverage_for(ticker)
        return {"lot_id": lot_id, "coverage_state": coverage_state}

    def record_sale(self, ticker: str, shares: float, price: float, sale_date: str,
                    note: str | None = None) -> dict:
        """Portfolio Entry Intent = sell. The sale row IS portfolio history;
        a full exit additionally lands in the Decision Register."""
        _reject_future_date(sale_date, "sale")
        ticker = ticker.upper()
        ent = self.stores.identity.ensure_entity(ticker)
        res = self.stores.portfolio.record_sale(
            ticker, shares, price, sale_date, entity_id=ent["id"], note=note,
        )
        holding = self.stores.portfolio.holding(ticker)
        if holding is None or holding["shares"] <= 1e-9:
            self.stores.learning.add_decision(
                "portfolio_exit",
                f"Exited {ticker}: sold {shares:g} @ {price:g} on {sale_date}",
                rationale=note,
                links={"sale_id": res["id"], "ticker": ticker},
            )
        return {"sale_id": res["id"], "realized_pnl": res["realized_pnl"]}

    # --- price refresh (price-only, never thesis health) -----------------------------
    async def refresh_prices(self) -> int:
        """Portfolio Price and P&L Refresh: live quotes for holdings only
        (the interactive path live calls are reserved for, ADR-0059) → price
        marks → holdings projection, plus today's closes into price_history
        so the chart stays current. NEVER touches thesis health or
        user-entered fields."""
        tickers = [h["ticker"] for h in self.stores.portfolio.holdings()]
        if not tickers:
            return 0
        from backend.services.market_data import MarketDataService
        quotes = await MarketDataService(self.stores).refresh_quotes(tickers, live=True)
        today = datetime.now(timezone.utc).date()
        if today.weekday() < 5:
            # Markets don't trade weekends — a Saturday-stamped "bar" would
            # sit in price_history forever (no exchange data ever lands on
            # that date to replace it) and zigzag through every chart that
            # reads the series. Quote marks below still update regardless.
            self.stores.bulk.upsert_prices([
                {"ticker": t, "date": today.isoformat(), "close": float(price)}
                for t, q in quotes.items()
                if (price := q.get("price") or q.get("currentPrice")) and not q.get("stale")
            ])
        self.stores.portfolio.rebuild_holdings()
        return len([t for t in tickers if t in quotes])

    # --- holdings view ----------------------------------------------------------------
    def holdings_view(self) -> list[dict]:
        """Contract HoldingRow list with thesis-health labels and Portfolio
        Factual Flags (factual, non-prescriptive)."""
        holdings = self.stores.portfolio.holdings()
        if not holdings:
            return []
        prices = self.stores.portfolio.prices()
        proj = self.stores.constitution.projection("portfolio_review")
        settings = (proj or {}).get("settings") or {}
        conc_pct = float(settings.get("concentration_flag_pct", DEFAULT_CONCENTRATION_FLAG_PCT))
        from backend.workflows import thesis_health  # lazy: avoids import cycles
        rows = []
        for h in holdings:
            cost = (h["avg_cost"] or 0) * h["shares"]
            price = prices.get(h["ticker"])
            if price is None and h["market_value"] and h["shares"]:
                price = h["market_value"] / h["shares"]
            flags = []
            if h["weight"] is not None and h["weight"] * 100 > conc_pct:
                flags.append({
                    "kind": "concentration",
                    "detail": (f"{h['weight'] * 100:.1f}% of portfolio market value; "
                               f"concentration flag threshold is {conc_pct:.0f}%"),
                })
            if cost > 0 and h["unrealized_pnl"] is not None \
                    and h["unrealized_pnl"] / cost < DRAWDOWN_FLAG_FRACTION:
                flags.append({
                    "kind": "drawdown",
                    "detail": (f"Unrealized P&L is {h['unrealized_pnl'] / cost * 100:.1f}% "
                               f"of cost basis"),
                })
            rows.append({
                "ticker": h["ticker"],
                "shares": h["shares"],
                "avg_cost": h["avg_cost"],
                "price": price,
                "market_value": h["market_value"],
                "unrealized_pnl": h["unrealized_pnl"],
                "weight": h["weight"],
                "position_type": h["position_type"],
                "coverage_state": h["coverage_state"],
                "thesis_health_label": thesis_health.summary_for(self.stores, h["ticker"]),
                "flags": flags,
            })
        return rows

    # --- coverage ---------------------------------------------------------------------
    def ensure_coverage_for(self, ticker: str) -> str:
        """Check Fresh Portfolio Thesis Coverage for one held ticker; queue a
        coverage memo when missing or stale. Returns the coverage state."""
        ticker = ticker.upper()
        holding = self.stores.portfolio.holding(ticker)
        if not holding:
            return "none"
        from backend.workflows import thesis_health  # lazy
        plan = thesis_health.active_plan(self.stores, ticker)
        if plan and thesis_health.plan_ready(self.stores, plan["id"]):
            memo = self.stores.artifacts.get(plan["memo_artifact_id"])
            if memo and _age_days(memo["created_at"]) <= COVERAGE_FRESH_DAYS:
                self.stores.portfolio.set_coverage_state(ticker, "covered", memo["id"])
                return "covered"
        if holding["coverage_state"] in ("queued", "running"):
            return holding["coverage_state"]
        if not self._coverage_work_pending(ticker):
            self.stores.ops.enqueue(COVERAGE_WORK_KIND, {"ticker": ticker},
                                    priority=COVERAGE_PRIORITY)
        self.stores.portfolio.set_coverage_state(ticker, "queued")
        return "queued"

    def _coverage_work_pending(self, ticker: str) -> bool:
        return any(
            w["kind"] == COVERAGE_WORK_KIND and w["status"] in ("queued", "running")
            and (w["payload"] or {}).get("ticker") == ticker
            for w in self.stores.ops.queue_state(limit=200)
        )

    async def ensure_coverage(self) -> list[str]:
        """Coverage sweep across all holdings (sync/save action, not page
        load). Returns tickers newly or still queued."""
        queued = []
        for h in self.stores.portfolio.holdings():
            if self.ensure_coverage_for(h["ticker"]) == "queued":
                queued.append(h["ticker"])
        return queued


async def process_coverage_queue(stores) -> list[dict]:
    """Drain queued coverage-memo work: run the memo workflow with
    portfolio_coverage provenance, then activate its thesis-health plan.
    Failed coverage surfaces as a Dashboard Attention Item; routine progress
    stays on the holding row (CONTEXT)."""
    results: list[dict] = []
    while True:
        work = stores.ops.claim_next(kind=COVERAGE_WORK_KIND)
        if not work:
            break
        ticker = ((work.get("payload") or {}).get("ticker") or "").upper()
        if not ticker:
            stores.ops.fail_work(work["id"], "coverage work item missing ticker")
            continue
        stores.portfolio.set_coverage_state(ticker, "running")
        try:
            from backend.workflows.memo import run_memo  # lazy: built in parallel
        except Exception as exc:
            _coverage_failed(stores, work, ticker, f"memo workflow unavailable: {exc}")
            results.append({"ticker": ticker, "state": "failed"})
            continue
        try:
            await run_memo(stores, ticker=ticker, trigger="coverage",
                           provenance="portfolio_coverage")
            memo = stores.artifacts.latest_for_ticker(ticker, "investment_memo")
            if not memo:
                raise RuntimeError("coverage memo run produced no memo artifact")
            from backend.workflows import thesis_health
            plan = thesis_health.active_plan(stores, ticker)
            if not plan or plan["memo_artifact_id"] != memo["id"]:
                thesis_health.create_plan_for_memo(stores, memo["id"])
            stores.portfolio.set_coverage_state(ticker, "covered", memo["id"])
            stores.ops.complete_work(work["id"])
            stores.dashboard.resolve_source("coverage_failure", ticker)
            results.append({"ticker": ticker, "state": "covered"})
        except asyncio.CancelledError:  # shutdown mid-memo: give the attempt back
            stores.ops.fail_work(work["id"], "interrupted by shutdown")
            stores.portfolio.set_coverage_state(ticker, "queued")
            raise
        except Exception as exc:
            _coverage_failed(stores, work, ticker, str(exc))
            results.append({"ticker": ticker, "state": "failed"})
    return results


def _coverage_failed(stores, work: dict, ticker: str, error: str) -> None:
    stores.ops.fail_work(work["id"], error)
    stores.portfolio.set_coverage_state(ticker, "failed")
    stores.dashboard.upsert_item(
        "attention", "needs_attention", "coverage_failure", ticker, work["id"],
        ticker=ticker,
        title=f"Coverage memo failed — {ticker}",
        body=f"Automatic portfolio thesis coverage could not complete: {error}",
        severity="normal",
        evidence_refs=[{"kind": "work_item", "id": work["id"]}],
    )
