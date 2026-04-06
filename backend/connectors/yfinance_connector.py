"""Yahoo Finance Data Connector (Free Default).

Provides real-time quotes, market data, and basic company info via yfinance.
No API key required. Rate limited but sufficient for 50-100 tickers.

This is the FREE default connector. FMP is the paid upgrade for estimates/peers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.connectors import ConnectorResult, DataConnector

log = logging.getLogger("fundops.yfinance")


class YFinanceConnector(DataConnector):
    """Yahoo Finance connector (free, no API key)."""

    name = "yfinance"
    capabilities = ["quotes", "profile"]

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def get_quotes(self, tickers: list[str]) -> ConnectorResult:
        """Get current quotes for a list of tickers — batched async fetching.

        Fetches in batches of 10 with 1s delay between batches to avoid
        Yahoo Finance rate limiting. For 500 tickers ~50 batches = ~2-3 min.
        """
        t0 = time.time()
        try:
            import yfinance as yf
            semaphore = asyncio.Semaphore(10)  # 10 concurrent yfinance calls (was 30 — caused rate limiting)

            async def fetch_one(ticker: str) -> dict | None:
                async with semaphore:
                    try:
                        info = await asyncio.wait_for(
                            asyncio.to_thread(lambda t=ticker: yf.Ticker(t).info),
                            timeout=12.0,
                        )
                        if not info:
                            return None
                        price = (
                            info.get("regularMarketPrice")
                            or info.get("currentPrice")
                            or info.get("previousClose")
                        )
                        if not price:
                            return None
                        year_high = info.get("fiftyTwoWeekHigh") or 0
                        year_low = info.get("fiftyTwoWeekLow") or 0
                        return {
                            "symbol": ticker.upper(),
                            "price": price,
                            "changesPercentage": info.get("regularMarketChangePercent"),
                            "change": info.get("regularMarketChange"),
                            "marketCap": info.get("marketCap"),
                            "volume": info.get("regularMarketVolume"),
                            "avgVolume": info.get("averageDailyVolume10Day"),
                            "yearHigh": year_high,
                            "yearLow": year_low,
                            "pe": info.get("trailingPE") or info.get("forwardPE"),
                            "eps": info.get("trailingEps"),
                            "beta": info.get("beta"),
                            "name": info.get("shortName") or info.get("longName"),
                            "sector": info.get("sector"),
                            "industry": info.get("industry"),
                            "companyName": info.get("shortName") or info.get("longName"),
                        }
                    except asyncio.TimeoutError:
                        log.debug(f"yfinance timeout for {ticker}")
                        return None
                    except Exception as e:
                        log.debug(f"yfinance quote failed for {ticker}: {e}")
                        return None

            # Batch fetching: 10 tickers at a time with 1s pause between batches
            # to respect Yahoo Finance rate limits
            BATCH_SIZE = 10
            BATCH_DELAY = 1.0  # seconds between batches
            data = []
            for i in range(0, len(tickers), BATCH_SIZE):
                batch = tickers[i:i + BATCH_SIZE]
                batch_results = await asyncio.gather(*[fetch_one(t) for t in batch])
                data.extend([r for r in batch_results if r is not None])
                # Progress log every 50 tickers
                if (i + BATCH_SIZE) % 50 == 0 or i + BATCH_SIZE >= len(tickers):
                    log.info(f"yfinance: {len(data)}/{len(tickers)} quotes fetched so far ({time.time()-t0:.0f}s)")
                # Delay between batches (skip after last batch)
                if i + BATCH_SIZE < len(tickers):
                    await asyncio.sleep(BATCH_DELAY)
            log.info(f"yfinance: {len(data)}/{len(tickers)} quotes fetched in {time.time()-t0:.1f}s")
            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=data, duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="quotes",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_financials(self, ticker: str, years: int = 5) -> ConnectorResult:
        """Not the primary source for financials. Use SEC EDGAR."""
        return ConnectorResult(
            connector=self.name, capability="financials",
            error="Use SEC EDGAR for financials. yfinance is for quotes/market data only.",
        )

    async def get_profile(self, ticker: str) -> ConnectorResult:
        """Get basic company profile."""
        t0 = time.time()
        try:
            import yfinance as yf
            info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
            if not info:
                return ConnectorResult(
                    connector=self.name, capability="profile",
                    error=f"No data for {ticker}",
                    duration_s=time.time() - t0,
                )
            return ConnectorResult(
                connector=self.name, capability="profile",
                data={
                    "symbol": ticker.upper(),
                    "companyName": info.get("longName") or info.get("shortName"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "country": info.get("country"),
                    "exchange": info.get("exchange"),
                    "mktCap": info.get("marketCap"),
                    "price": info.get("regularMarketPrice") or info.get("currentPrice"),
                    "beta": info.get("beta"),
                    "employees": info.get("fullTimeEmployees"),
                    "description": (info.get("longBusinessSummary") or "")[:500],
                },
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return ConnectorResult(
                connector=self.name, capability="profile",
                error=str(e), duration_s=time.time() - t0,
            )

    def validate_config(self) -> list[str]:
        return []  # No API key needed

    async def health_check(self) -> bool:
        try:
            result = await self.get_quotes(["AAPL"])
            return result.ok
        except Exception:
            return False
