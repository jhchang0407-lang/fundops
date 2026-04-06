"""FMP (Financial Modeling Prep) Data Connector.

Provides market data, financials, estimates, profiles, and peer comparisons
via the FMP API. Implements the DataConnector interface.

Rate limiting: configurable requests_per_batch and delay_between_batches_s
from workflow.yaml.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.connectors import ConnectorResult, DataConnector
from backend.core.cache import FileCache

log = logging.getLogger("fundops.fmp")

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPConnector(DataConnector):
    """FMP API connector with rate limiting and caching."""

    name = "fmp"
    capabilities = ["quotes", "financials", "estimates", "profile", "peers", "key_metrics"]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key", "")
        rate_limit = self.config.get("rate_limit", {})
        self.batch_size = rate_limit.get("requests_per_batch", 10)
        self.batch_delay = rate_limit.get("delay_between_batches_s", 2)
        self._request_count = 0
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _fetch(self, path: str, params: dict | None = None) -> Any:
        """Make a single FMP API request with rate limiting."""
        client = self._get_client()
        url = f"{FMP_BASE_URL}{path}"
        all_params = {"apikey": self.api_key}
        if params:
            all_params.update(params)

        # Rate limiting
        self._request_count += 1
        if self._request_count % self.batch_size == 0:
            log.debug(f"Rate limit pause: {self.batch_delay}s after {self._request_count} requests")
            await asyncio.sleep(self.batch_delay)

        resp = await client.get(url, params=all_params)
        resp.raise_for_status()
        return resp.json()

    async def get_quotes(self, tickers: list[str]) -> ConnectorResult:
        """Get current quotes for a list of tickers."""
        t0 = time.time()
        try:
            symbols = ",".join(tickers)
            data = await self._fetch("/quote", {"symbol": symbols})
            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=data if isinstance(data, list) else [data],
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="quotes",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_financials(self, ticker: str, years: int = 5) -> ConnectorResult:
        """Get income statement, balance sheet, cash flow."""
        t0 = time.time()
        try:
            income, balance, cashflow = await asyncio.gather(
                self._fetch("/income-statement", {"symbol": ticker, "period": "annual", "limit": str(years)}),
                self._fetch("/balance-sheet-statement", {"symbol": ticker, "period": "annual", "limit": str(years)}),
                self._fetch("/cash-flow-statement", {"symbol": ticker, "period": "annual", "limit": str(years)}),
            )
            return ConnectorResult(
                connector=self.name, capability="financials",
                data={
                    "income_statement": income if isinstance(income, list) else [],
                    "balance_sheet": balance if isinstance(balance, list) else [],
                    "cash_flow": cashflow if isinstance(cashflow, list) else [],
                },
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="financials",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_financials_quarterly(self, ticker: str, quarters: int = 8) -> ConnectorResult:
        """Get quarterly financials."""
        t0 = time.time()
        try:
            income, balance, cashflow = await asyncio.gather(
                self._fetch("/income-statement", {"symbol": ticker, "period": "quarter", "limit": str(quarters)}),
                self._fetch("/balance-sheet-statement", {"symbol": ticker, "period": "quarter", "limit": str(quarters)}),
                self._fetch("/cash-flow-statement", {"symbol": ticker, "period": "quarter", "limit": str(quarters)}),
            )
            return ConnectorResult(
                connector=self.name, capability="financials",
                data={
                    "income_statement": income if isinstance(income, list) else [],
                    "balance_sheet": balance if isinstance(balance, list) else [],
                    "cash_flow": cashflow if isinstance(cashflow, list) else [],
                },
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="financials",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_estimates(self, ticker: str) -> ConnectorResult:
        """Get analyst consensus estimates."""
        t0 = time.time()
        try:
            data = await self._fetch("/analyst-estimates", {"symbol": ticker, "period": "annual"})
            return ConnectorResult(
                connector=self.name, capability="estimates",
                data=data if isinstance(data, list) else [],
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="estimates",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_profile(self, ticker: str) -> ConnectorResult:
        """Get company profile with market data."""
        t0 = time.time()
        try:
            data = await self._fetch("/profile", {"symbol": ticker})
            profile = data[0] if isinstance(data, list) and data else data
            return ConnectorResult(
                connector=self.name, capability="profile",
                data=profile if isinstance(profile, dict) else {},
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="profile",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_peers(self, ticker: str) -> ConnectorResult:
        """Get peer companies with key metrics."""
        t0 = time.time()
        try:
            peer_list = await self._fetch("/stock-peers", {"symbol": ticker})
            if not peer_list:
                return ConnectorResult(connector=self.name, capability="peers", data=[],
                                       duration_s=time.time() - t0)

            peers = peer_list[0].get("peersList", []) if isinstance(peer_list, list) else []
            peer_data = []

            for peer_ticker in peers[:8]:
                try:
                    profile = await self._fetch("/profile", {"symbol": peer_ticker})
                    ratios = await self._fetch("/ratios", {"symbol": peer_ticker, "limit": "1"})

                    p = profile[0] if isinstance(profile, list) and profile else {}
                    r = ratios[0] if isinstance(ratios, list) and ratios else {}

                    peer_data.append({
                        "symbol": peer_ticker,
                        "companyName": p.get("companyName", ""),
                        "sector": p.get("sector", ""),
                        "industry": p.get("industry", ""),
                        "mktCap": p.get("mktCap"),
                        "price": p.get("price"),
                        "peRatio": r.get("priceEarningsRatio"),
                        "priceToBookRatio": r.get("priceToBookRatio"),
                        "priceToSalesRatio": r.get("priceToSalesRatio"),
                        "grossProfitMargin": r.get("grossProfitMargin"),
                        "operatingProfitMargin": r.get("operatingProfitMargin"),
                        "netProfitMargin": r.get("netProfitMargin"),
                        "returnOnEquity": r.get("returnOnEquity"),
                    })
                except Exception:
                    continue

            return ConnectorResult(
                connector=self.name, capability="peers",
                data=peer_data, duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="peers",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_key_metrics(self, ticker: str) -> ConnectorResult:
        """Get key financial metrics (ROIC, margins, etc.)."""
        t0 = time.time()
        try:
            data = await self._fetch("/key-metrics", {"symbol": ticker, "period": "annual", "limit": "5"})
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                data=data if isinstance(data, list) else [],
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_ratios(self, ticker: str) -> ConnectorResult:
        """Get financial ratios."""
        t0 = time.time()
        try:
            data = await self._fetch("/ratios", {"symbol": ticker, "period": "annual", "limit": "5"})
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                data=data if isinstance(data, list) else [],
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_bulk_quotes(self, tickers: list[str]) -> ConnectorResult:
        """Get quotes in batches with rate limiting."""
        t0 = time.time()
        all_quotes = []
        for i in range(0, len(tickers), self.batch_size):
            batch = tickers[i:i + self.batch_size]
            result = await self.get_quotes(batch)
            if result.ok:
                all_quotes.extend(result.data)
            if i + self.batch_size < len(tickers):
                await asyncio.sleep(self.batch_delay)

        return ConnectorResult(
            connector=self.name, capability="quotes",
            data=all_quotes, duration_s=time.time() - t0,
        )

    async def get_historical_prices(self, ticker: str, period: str = "6month") -> ConnectorResult:
        """Get historical daily prices for RS/momentum calculation.

        FMP endpoint: /historical-price-full/{ticker}
        Returns list of {date, close, open, high, low, volume, ...}
        """
        t0 = time.time()
        try:
            data = await self._fetch(f"/historical-price-full/{ticker}", {
                "from": "",  # FMP returns full history, we filter client-side
            })
            prices = data.get("historical", []) if isinstance(data, dict) else []
            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=prices,
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="quotes",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_historical_prices_batch(self, tickers: list[str]) -> ConnectorResult:
        """Get historical daily prices for multiple tickers.

        Uses FMP batch endpoint for efficiency.
        Returns dict of {ticker: [{date, close, ...}, ...]}
        """
        t0 = time.time()
        try:
            # FMP batch: /historical-price-full/AAPL,MSFT,GOOG
            batch_str = ",".join(tickers[:30])  # FMP limits batch size
            data = await self._fetch(f"/historical-price-full/{batch_str}", {})
            result = {}
            if isinstance(data, dict) and "historicalStockList" in data:
                for item in data["historicalStockList"]:
                    sym = item.get("symbol", "")
                    result[sym] = item.get("historical", [])
            elif isinstance(data, dict) and "historical" in data:
                # Single ticker response
                result[tickers[0]] = data.get("historical", [])
            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=result,
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="quotes",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_stock_screener(self, params: dict = None) -> ConnectorResult:
        """Bulk screener endpoint (single API call for universe filtering)."""
        t0 = time.time()
        try:
            data = await self._fetch("/stock-screener", params or {})
            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=data if isinstance(data, list) else [],
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="quotes",
                error=str(e), duration_s=time.time() - t0,
            )

    def validate_config(self) -> list[str]:
        errors = []
        if not self.api_key:
            errors.append("FMP API key not configured")
        return errors

    async def health_check(self) -> bool:
        try:
            result = await self.get_quotes(["AAPL"])
            return result.ok
        except Exception:
            return False

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
