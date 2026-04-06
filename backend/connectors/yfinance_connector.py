"""Yahoo Finance Data Connector (Free Default).

Provides real-time quotes, market data, and basic company info via yfinance.
No API key required. Rate limited but sufficient for large universes (2000+).

This is the FREE default connector. FMP is the paid upgrade for estimates/peers.

Rate limit strategy (empirical, Yahoo doesn't publish limits):
  - Phase 1: yf.download() for prices — single bulk request, very fast
  - Phase 2: yf.Ticker().info for fundamentals — batched with delays
  - Batch size 20, 2-3s random delay between batches
  - Exponential backoff on errors (likely rate limit)
  - ~5-8 min for Russell 2000 (~1900 tickers)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable

from backend.connectors import ConnectorResult, DataConnector

log = logging.getLogger("fundops.yfinance")

# Tuning knobs — adjust if Yahoo tightens/loosens limits
BATCH_SIZE = 20          # tickers per info batch
BATCH_DELAY_MIN = 1.5    # min seconds between batches
BATCH_DELAY_MAX = 3.0    # max seconds between batches (randomized)
CONCURRENCY = 10         # max parallel yf.Ticker().info calls within a batch
TICKER_TIMEOUT = 12.0    # seconds per single ticker .info call
MAX_BACKOFF = 30.0       # max backoff delay on repeated errors


class YFinanceConnector(DataConnector):
    """Yahoo Finance connector (free, no API key)."""

    name = "yfinance"
    capabilities = ["quotes", "profile"]

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def get_quotes(
        self,
        tickers: list[str],
        progress_cb: Callable[[str], None] | None = None,
    ) -> ConnectorResult:
        """Get current quotes for a list of tickers — optimized two-phase fetch.

        Phase 1: yf.download() for prices + basic market data (fast bulk).
        Phase 2: yf.Ticker().info for fundamentals (batched with rate limiting).

        Args:
            tickers: List of ticker symbols
            progress_cb: Optional callback for progress updates

        Returns:
            ConnectorResult with list of stock dicts
        """
        t0 = time.time()
        _progress = progress_cb or (lambda msg: None)

        try:
            import yfinance as yf
            import pandas as pd

            total = len(tickers)
            _progress(f"Fetching {total} tickers from Yahoo Finance...")

            # ── Phase 1: Bulk price download ──
            # yf.download() fetches OHLCV for all tickers in one HTTP call
            price_map: dict[str, dict] = {}
            try:
                _progress(f"Phase 1: Bulk price download ({total} tickers)...")
                df = await asyncio.to_thread(
                    lambda: yf.download(
                        tickers=" ".join(tickers),
                        period="5d",
                        group_by="ticker",
                        auto_adjust=True,
                        threads=True,
                        progress=False,
                    )
                )
                if df is not None and not df.empty:
                    for ticker in tickers:
                        try:
                            if len(tickers) == 1:
                                ticker_df = df
                            else:
                                ticker_df = df[ticker] if ticker in df.columns.get_level_values(0) else None
                            if ticker_df is not None and not ticker_df.empty:
                                last = ticker_df.dropna(how="all").iloc[-1]
                                price_map[ticker.upper()] = {
                                    "price": float(last.get("Close", 0)) if pd.notna(last.get("Close")) else None,
                                    "volume": int(last.get("Volume", 0)) if pd.notna(last.get("Volume")) else None,
                                }
                        except Exception:
                            pass
                log.info(f"Phase 1: got prices for {len(price_map)}/{total} tickers in {time.time()-t0:.1f}s")
                _progress(f"Phase 1 done: {len(price_map)} prices in {time.time()-t0:.0f}s")
            except Exception as e:
                log.warning(f"Phase 1 (bulk download) failed: {e} — falling back to per-ticker")
                _progress("Phase 1 failed, falling back to per-ticker fetch...")

            # ── Phase 2: Fundamental data via .info (batched) ──
            # Only fetch .info for tickers that had a valid price in Phase 1
            # This filters out delisted tickers and saves API calls
            if price_map:
                live_tickers = [t for t in tickers if t.upper() in price_map]
                skipped = total - len(live_tickers)
                if skipped > 0:
                    log.info(f"Phase 2: skipping {skipped} tickers with no price data (likely delisted)")
            else:
                live_tickers = tickers  # Phase 1 failed, try all

            semaphore = asyncio.Semaphore(CONCURRENCY)
            consecutive_errors = 0
            rate_limited = False

            async def fetch_info(ticker: str) -> dict | None:
                nonlocal consecutive_errors, rate_limited
                if rate_limited:
                    return None  # Skip remaining tickers after persistent rate limit
                async with semaphore:
                    try:
                        info = await asyncio.wait_for(
                            asyncio.to_thread(lambda t=ticker: yf.Ticker(t).info),
                            timeout=TICKER_TIMEOUT,
                        )
                        if not info:
                            return None
                        consecutive_errors = 0  # Reset on success

                        price = (
                            info.get("regularMarketPrice")
                            or info.get("currentPrice")
                            or info.get("previousClose")
                        )
                        # Fall back to Phase 1 price if .info didn't give one
                        bulk_data = price_map.get(ticker.upper(), {})
                        if not price:
                            price = bulk_data.get("price")
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
                            "volume": info.get("regularMarketVolume") or bulk_data.get("volume"),
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
                        consecutive_errors += 1
                        err_str = str(e).lower()
                        if "rate" in err_str or "429" in err_str or "too many" in err_str:
                            if consecutive_errors >= 8:
                                rate_limited = True
                                log.warning(f"yfinance: persistent rate limiting after {consecutive_errors} errors — stopping Phase 2")
                        if consecutive_errors <= 3:
                            log.debug(f"yfinance quote failed for {ticker}: {e}")
                        elif consecutive_errors == 4:
                            log.warning(f"yfinance: {consecutive_errors} consecutive errors — possible rate limit")
                        return None

            # Batch fetching with adaptive delays
            live_total = len(live_tickers)
            _progress(f"Phase 2: Fetching fundamentals ({live_total} live tickers, ~{live_total // BATCH_SIZE} batches)...")
            data = []
            for i in range(0, live_total, BATCH_SIZE):
                if rate_limited:
                    log.warning(f"yfinance: aborting Phase 2 at batch {i // BATCH_SIZE} due to rate limiting")
                    _progress(f"Rate limited — got {len(data)} stocks before limit hit")
                    break

                batch = live_tickers[i:i + BATCH_SIZE]
                batch_results = await asyncio.gather(*[fetch_info(t) for t in batch])
                data.extend([r for r in batch_results if r is not None])

                # Progress log every 5 batches or at the end
                batch_num = i // BATCH_SIZE + 1
                total_batches = (live_total + BATCH_SIZE - 1) // BATCH_SIZE
                if batch_num % 5 == 0 or i + BATCH_SIZE >= live_total:
                    elapsed = time.time() - t0
                    rate = len(data) / elapsed if elapsed > 0 else 0
                    eta = (live_total - i) / rate if rate > 0 else 0
                    _progress(f"Phase 2: {len(data)}/{live_total} fetched ({elapsed:.0f}s, ~{eta:.0f}s remaining)")
                    log.info(f"yfinance: {len(data)}/{live_total} quotes ({elapsed:.0f}s)")

                # Adaptive delay: longer if seeing errors
                if i + BATCH_SIZE < live_total:
                    if consecutive_errors >= 3:
                        # Back off: 5-10s when hitting errors
                        delay = min(MAX_BACKOFF, 5.0 + consecutive_errors * 2)
                        log.info(f"yfinance: backing off {delay:.1f}s (consecutive errors: {consecutive_errors})")
                        _progress(f"Rate limited — backing off {delay:.0f}s...")
                    else:
                        delay = random.uniform(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
                    await asyncio.sleep(delay)

            elapsed = time.time() - t0
            success_rate = len(data) / total * 100 if total > 0 else 0
            log.info(f"yfinance: {len(data)}/{total} quotes ({success_rate:.0f}%) in {elapsed:.1f}s")
            _progress(f"Done: {len(data)} quotes in {elapsed:.0f}s")

            return ConnectorResult(
                connector=self.name, capability="quotes",
                data=data, duration_s=elapsed,
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
