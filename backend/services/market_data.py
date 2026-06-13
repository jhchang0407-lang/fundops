"""Market & financial data service.

Adapts the retained PoC connectors (yfinance for market data, SEC EDGAR for
reported fundamentals — ADR-0017 roles) into the new platform stores:
quotes become price marks + market-data evidence; SEC fundamentals become
periodized financial observations with lineage (ADR-0042/0043).

Local-first since ADR-0059: bulk ingestion fills price_history and the
observation tables, so reads serve stored data and live provider calls are
reserved for interactive paths (live quotes on request, targeted per-ticker
fundamentals top-ups). Once the bootstrap has run, screening-scale reads
never trigger network calls — missing tickers enqueue fact_topup work.

All methods degrade gracefully offline: stored observations and price marks
serve as the fallback so workflows report stale data instead of crashing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from backend.core import opconfig
from backend.stores import Stores

log = logging.getLogger("fundops.market_data")

FRESH_OBS_DAYS = 100          # observation recency that skips the SEC top-up
FACT_TOPUP_KIND = "fact_topup"
FACT_TOPUP_PRIORITY = 6


class MarketDataService:
    def __init__(self, stores: Stores):
        self.stores = stores
        self._yf = None
        self._sec = None

    def _yfinance(self):
        if self._yf is None:
            from backend.connectors.yfinance_connector import YFinanceConnector
            self._yf = YFinanceConnector({})
        return self._yf

    def _edgar(self):
        if self._sec is None:
            from backend.connectors.sec_edgar import SECEdgarConnector
            cfg = opconfig.load()
            self._sec = SECEdgarConnector({"user_agent": cfg["providers"]["sec_user_agent"]})
        return self._sec

    # --- quotes ---------------------------------------------------------------
    async def refresh_quotes(self, tickers: list[str], live: bool = False) -> dict[str, dict]:
        """Quotes, local-first (ADR-0059): stored bulk closes serve every
        ticker (stale unless dated today); the live yfinance call only runs
        for tickers with no stored price at all, or for everything when
        live=True (interactive refresh). Live rows persist price marks,
        entity identity, and market evidence. Returns {ticker: quote dict}."""
        tickers = [t.upper() for t in tickers]
        quotes: dict[str, dict] = {}
        today = _today()
        for t in tickers:
            stored = self.stores.bulk.latest_close(t)
            if stored:
                quotes[t] = {"symbol": t, "price": stored["close"],
                             "stale": stored["date"] != today}
        to_fetch = tickers if live else [t for t in tickers if t not in quotes]
        rows = []
        if to_fetch:
            try:
                # Connectors do sync I/O internally; run them on a worker thread with
                # their own event loop so the server loop never blocks.
                result = await asyncio.wait_for(
                    asyncio.to_thread(asyncio.run, self._yfinance().get_quotes(to_fetch)),
                    timeout=max(60, 3 * len(to_fetch)),
                )
                rows = result.data if result.ok else []
            except Exception as exc:
                log.warning("quote fetch failed: %s", exc)
                rows = []
        for row in rows or []:
            ticker = (row.get("symbol") or row.get("ticker") or "").upper()
            if not ticker:
                continue
            quotes[ticker] = row
            price = row.get("price") or row.get("currentPrice")
            ent = self.stores.identity.ensure_entity(
                ticker, name=row.get("company_name") or row.get("name"),
                sector=row.get("sector"), industry=row.get("industry"),
            )
            if price:
                self.stores.portfolio.mark_price(ticker, float(price))
                for metric in ("price", "market_cap"):
                    value = row.get(metric) or (row.get("marketCap") if metric == "market_cap" else None)
                    if value:
                        self.stores.financial.add_observation(
                            ent["id"], metric, _today(), "quarterly", float(value),
                            is_calculated=False, lineage={"source": "yfinance"},
                        )
        # Fallback for anything not fetched.
        stored = self.stores.portfolio.prices()
        for t in tickers:
            if t not in quotes and t in stored:
                quotes[t] = {"symbol": t, "price": stored[t], "stale": True}
        return quotes

    # --- fundamentals ------------------------------------------------------------
    async def fetch_fundamentals(self, ticker: str) -> dict | None:
        """Fetch SEC fundamentals; persist reported-period observations
        (5y annual + quarterly history when available) and refresh the latest
        projection. Returns the flat metric dict or None when unavailable.
        This is the targeted live top-up path (ADR-0059) — but fresh local
        observations (period_end within 100 days) skip the SEC fetch and
        return stored metrics instead."""
        ticker = ticker.upper()
        ent = self.stores.identity.ensure_entity(ticker)

        recent = self.stores.financial.observations(ent["id"], limit=1)
        if recent and _days_since(recent[0]["period_end"]) <= FRESH_OBS_DAYS:
            stored = self.stores.financial.latest(ent["id"])
            if stored:
                return {**stored, "entity_id": ent["id"]}

        async def _fetch_all(edgar):
            return (
                await edgar.get_financials(ticker, years=5),
                await edgar.get_profile(ticker),
                await edgar.get_ratios(ticker),
            )

        try:
            # SEC client uses sync requests internally — isolate on a worker
            # thread with a hard timeout so one ticker can't stall a run.
            fin_res, prof_res, ratio_res = await asyncio.wait_for(
                asyncio.to_thread(asyncio.run, _fetch_all(self._edgar())),
                timeout=60,
            )
        except Exception as exc:
            log.warning("SEC fetch failed for %s: %s", ticker, exc)
            return self._stored_metrics(ent["id"])
        if not fin_res.ok:
            return self._stored_metrics(ent["id"])

        try:
            fd = self._edgar().to_financial_data(
                ticker,
                prof_res.data if prof_res.ok else {},
                fin_res.data,
                ratio_res.data if ratio_res.ok else {},
            )
        except Exception as exc:
            log.warning("financial-data assembly failed for %s: %s", ticker, exc)
            return self._stored_metrics(ent["id"])

        src = self.stores.evidence.add_source(
            "filing", locator=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}",
            title=f"{ticker} SEC company facts", publisher="SEC EDGAR",
            retention_tier="identity",
        )
        if fd.profile:
            self.stores.identity.ensure_entity(
                ticker, name=fd.profile.name, sector=fd.profile.sector, industry=fd.profile.industry,
            )

        live_price = self.stores.portfolio.prices().get(ticker)
        flat = fd.to_flat_metrics(live_price=live_price)
        period_end = _latest_period_end(fd) or _today()
        lineage = {"source": "sec_edgar", "evidence_source_id": src, "method": "to_flat_metrics"}
        numeric = {k: v for k, v in flat.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)}
        self.stores.financial.store_metrics_snapshot(ent["id"], numeric, period_end, "annual", lineage)

        # Retain multi-period history for thesis health (12 quarters / 5 years).
        self._store_period_history(ent["id"], fd, src)
        return {**flat, "entity_id": ent["id"]}

    def _store_period_history(self, entity_id: str, fd, source_id: str) -> None:
        for period_type, statements in (("annual", fd.financials_annual or []),
                                        ("quarterly", fd.financials_quarterly or [])):
            limit = 5 if period_type == "annual" else 12
            for stmt in statements[:limit]:
                period_end = stmt.get("date") or stmt.get("period_end")
                if not period_end:
                    continue
                values = {
                    "revenue": stmt.get("revenue"),
                    "net_income": stmt.get("netIncome"),
                    "gross_profit": stmt.get("grossProfit"),
                    "operating_income": stmt.get("operatingIncome"),
                    "free_cash_flow": stmt.get("freeCashFlow"),
                    "operating_cash_flow": stmt.get("operatingCashFlow"),
                    "eps": stmt.get("eps"),
                    "shares_outstanding": stmt.get("weightedAverageShsOutDil"),
                }
                rev = values.get("revenue")
                if rev:
                    gp, oi = values.get("gross_profit"), values.get("operating_income")
                    if gp is not None:
                        values["gross_margin"] = gp / rev
                    if oi is not None:
                        values["operating_margin"] = oi / rev
                    if values.get("net_income") is not None:
                        values["net_margin"] = values["net_income"] / rev
                    if values.get("free_cash_flow") is not None:
                        values["fcf_margin"] = values["free_cash_flow"] / rev
                clean = {k: float(v) for k, v in values.items()
                         if isinstance(v, (int, float)) and not isinstance(v, bool)}
                if clean:
                    for metric, value in clean.items():
                        self.stores.financial.add_observation(
                            entity_id, metric, str(period_end)[:10], period_type, value,
                            is_calculated=metric.endswith("_margin"),
                            lineage={"source": "sec_edgar", "evidence_source_id": source_id},
                            refresh_latest=False,
                        )
        self.stores.financial.refresh_latest(entity_id)

    def _stored_metrics(self, entity_id: str) -> dict | None:
        stored = self.stores.financial.latest(entity_id)
        return {**stored, "entity_id": entity_id, "stale": True} if stored else None

    # --- combined view ---------------------------------------------------------------
    async def metrics_for(self, tickers: list[str], allow_fetch: bool = True,
                          concurrency: int = 4) -> dict[str, dict]:
        """Metric dicts for a set of tickers from retained observations.
        Local-first (ADR-0059): once the bulk bootstrap has run, this NEVER
        live-fetches — uncovered tickers are returned absent (callers treat
        them as unevaluable) and enqueue fact_topup work for the next sync.
        allow_fetch means "may live-fetch when the bootstrap has NOT run"."""
        bootstrapped = self.stores.bulk.get_state("bootstrap_done") == "1"
        out: dict[str, dict] = {}
        to_fetch: list[str] = []
        missing: list[str] = []
        for t in (x.upper() for x in tickers):
            ent = self.stores.identity.resolve_ticker(t)
            stored = self.stores.financial.latest(ent["id"]) if ent else {}
            if stored and ("roic" in stored or "revenue" in stored):
                out[t] = {**stored, "entity_id": ent["id"], "ticker": t,
                          "sector": ent.get("sector"), "company_name": ent.get("name")}
            elif bootstrapped:
                missing.append(t)
            elif allow_fetch:
                to_fetch.append(t)
        if missing:
            self._enqueue_fact_topups(missing)
        if to_fetch:
            sem = asyncio.Semaphore(concurrency)

            async def fetch(t: str):
                async with sem:
                    m = await self.fetch_fundamentals(t)
                    if m:
                        out[t] = {**m, "ticker": t}
            await asyncio.gather(*(fetch(t) for t in to_fetch))
        prices = self.stores.portfolio.prices()
        for t, m in out.items():
            m.setdefault("price", prices.get(t))
        return out

    def _enqueue_fact_topups(self, tickers: list[str]) -> None:
        """Queue targeted fundamentals top-ups for uncovered tickers, deduped
        against work already queued or running (ADR-0048)."""
        pending = {
            ((w.get("payload") or {}).get("ticker") or "").upper()
            for w in self.stores.ops.queue_state(limit=500)
            if w["kind"] == FACT_TOPUP_KIND and w["status"] in ("queued", "running")
        }
        for t in tickers:
            if t not in pending:
                self.stores.ops.enqueue(FACT_TOPUP_KIND, {"ticker": t},
                                        priority=FACT_TOPUP_PRIORITY)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _days_since(date_str: str) -> float:
    try:
        d = datetime.fromisoformat(str(date_str)[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400


def _latest_period_end(fd) -> str | None:
    annual = fd.financials_annual or []
    if annual and annual[0].get("date"):
        return str(annual[0]["date"])[:10]
    return None
