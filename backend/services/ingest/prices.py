"""Batched price-history ingestion (ADR-0059).

Downloads daily bars for the whole universe in chunked yfinance calls instead
of per-ticker quote requests, and lands them in the `price_history` table via
`stores.bulk.upsert_prices`. Network work runs on worker threads with hard
timeouts; a failed chunk logs and continues so an offline run still returns
counts. Holdings get deeper history (`data.holdings_price_history_years`)
than the screening universe (`data.price_history_years`).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.core import opconfig

log = logging.getLogger("fundops.ingest.prices")

CHUNK_TIMEOUT_S = 120
CHUNK_SLEEP_S = 1.5
INCREMENTAL_FALLBACK_DAYS = 7
PRICE_FIELDS = ("Open", "High", "Low", "Close", "Volume")
RANGE_DAYS = {"1m": 31, "6m": 183, "1y": 366, "5y": 1827}

# Benchmark/context series (not universe members): ingested into the same
# price_history table so portfolio-vs-benchmark analytics and chart overlays
# are pure local reads. ^GSPC = S&P 500, ^RUT = Russell 2000.
BENCHMARKS = ("^GSPC", "^RUT")
BENCHMARK_LABELS = {"^GSPC": "S&P 500", "^RUT": "Russell 2000"}
BENCHMARK_YEARS = 5

# Module-level hooks so tests monkeypatch the network call and the pacing
# sleep without touching yfinance or slowing the suite.
_sleep = asyncio.sleep


def _download_chunk(tickers: list[str], start: str):
    """One batched yfinance download for a chunk of tickers (sync; runs on a
    worker thread). Returns the raw DataFrame."""
    import yfinance as yf  # lazy: keeps offline tests free of the import

    return yf.download(
        tickers=" ".join(tickers), start=start, interval="1d",
        group_by="ticker", auto_adjust=True, progress=False, threads=False,
    )


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN-safe


def _frame_to_rows(frame, tickers: list[str]) -> list[dict]:
    """Normalize a yfinance frame defensively: multi-ticker downloads return
    MultiIndex columns (ticker, field); single-ticker downloads return flat
    columns. Yields {ticker, date, open, high, low, close, volume} rows."""
    if frame is None or getattr(frame, "empty", True):
        return []
    multi = getattr(frame.columns, "nlevels", 1) > 1
    rows: list[dict] = []
    for ticker in tickers:
        if multi:
            if ticker not in set(frame.columns.get_level_values(0)):
                continue
            sub = frame[ticker]
        elif len(tickers) == 1:
            sub = frame
        else:
            continue  # flat frame can't be attributed across several tickers
        for idx, row in sub.iterrows():
            close = _num(row.get("Close"))
            if close is None:
                continue
            rows.append({
                "ticker": ticker, "date": str(idx)[:10],
                "open": _num(row.get("Open")), "high": _num(row.get("High")),
                "low": _num(row.get("Low")), "close": close,
                "volume": _num(row.get("Volume")),
            })
    return rows


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _chunk_start(stores, chunk: list[str], incremental: bool, default_start: str) -> str:
    if not incremental:
        return default_start
    dates = [s["date"] for t in chunk if (s := stores.bulk.latest_close(t))]
    if dates:
        return min(dates)
    return (_utc_today() - timedelta(days=INCREMENTAL_FALLBACK_DAYS)).isoformat()


async def sync_price_history(
    stores, tickers: list[str], years: float | None = None,
    incremental: bool = False, chunk_size: int = 150,
) -> dict:
    """Chunked daily-bar sync into price_history; marks the latest close per
    ticker so portfolio P&L stays current. Returns {tickers, rows}."""
    if years is None:
        years = opconfig.load()["data"]["price_history_years"]
    tickers = [t.upper() for t in tickers]
    default_start = (_utc_today() - timedelta(days=round(years * 365.25))).isoformat()
    # Tickers with no stored bars (new holding, universe addition) get a
    # full-depth backfill chunk of their own — the incremental fast path
    # would otherwise hand them a single day of history forever.
    fresh = [t for t in tickers if not stores.bulk.latest_close(t)] if incremental else []
    seasoned = [t for t in tickers if t not in set(fresh)]
    jobs = [(c, incremental) for c in _chunked(seasoned, chunk_size)]
    jobs += [(c, False) for c in _chunked(fresh, chunk_size)]
    synced: set[str] = set()
    total_rows = 0
    failed_chunks = 0
    for i, (chunk, inc) in enumerate(jobs):
        start = _chunk_start(stores, chunk, inc, default_start)
        try:
            frame = await asyncio.wait_for(
                asyncio.to_thread(_download_chunk, chunk, start),
                timeout=CHUNK_TIMEOUT_S,
            )
        except Exception as exc:  # offline / rate limit: keep going
            failed_chunks += 1
            log.warning("price chunk %d/%d failed (%s…): %s",
                        i + 1, len(jobs), chunk[0], exc)
            continue
        rows = _frame_to_rows(frame, chunk)
        total_rows += stores.bulk.upsert_prices(rows)
        latest: dict[str, dict] = {}
        for r in rows:
            if r["ticker"] not in latest or r["date"] > latest[r["ticker"]]["date"]:
                latest[r["ticker"]] = r
        for t, r in latest.items():
            stores.portfolio.mark_price(t, float(r["close"]))
            synced.add(t)
        if i < len(jobs) - 1:
            await _sleep(CHUNK_SLEEP_S)
    if synced:
        # Local recompute over the bars just landed — momentum/volatility/
        # dollar-volume observations stay current with every sync.
        from backend.services.ingest.price_metrics import refresh_price_metrics
        # Worker thread: at bootstrap scale this recompute takes minutes and
        # would otherwise freeze the event loop (and every API request).
        await asyncio.to_thread(refresh_price_metrics, stores, sorted(synced))
    return {"tickers": len(synced), "rows": total_rows, "failed_chunks": failed_chunks}


async def sync_benchmarks(stores, incremental: bool = False) -> dict:
    """Benchmark index bars (BENCHMARKS) into price_history. Index symbols
    are not entities — no identity rows, no derived metrics; just series."""
    return await sync_price_history(stores, list(BENCHMARKS),
                                    years=BENCHMARK_YEARS, incremental=incremental)


def benchmark_series(stores, symbol: str = "^GSPC", range_key: str = "1y") -> list[dict]:
    """Stored benchmark bars for overlays/analytics. Pure local read."""
    return price_chart(stores, symbol, range_key)


async def backfill_holdings_history(stores) -> dict:
    """Deeper price history for current holdings — charts and outcome windows
    need more than the universe default (data.holdings_price_history_years)."""
    tickers = [h["ticker"] for h in stores.portfolio.holdings()]
    if not tickers:
        return {"tickers": 0, "rows": 0}
    years = opconfig.load()["data"]["holdings_price_history_years"]
    return await sync_price_history(stores, tickers, years=years)


def price_chart(stores, ticker: str, range_key: str) -> list[dict]:
    """Stored daily bars for a chart range (1m|6m|1y|5y). Pure local read —
    name pinned, imported by the company routes."""
    days = RANGE_DAYS.get(range_key, RANGE_DAYS["1y"])
    start = (_utc_today() - timedelta(days=days)).isoformat()
    return stores.bulk.price_range(ticker, start=start)


def _utc_today():
    return datetime.now(timezone.utc).date()
