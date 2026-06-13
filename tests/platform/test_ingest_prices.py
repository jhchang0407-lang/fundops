"""Offline tests for bulk-first data ingestion (ADR-0059): batched price
history sync, chart range reads, Form 3/4/5 insider parsing + dedupe, and
local-first MarketDataService behavior. No network anywhere — the downloader
hooks are monkeypatched and fixture content is synthetic."""

from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.core import opconfig
from backend.services.ingest import ownership, prices
from backend.services.market_data import MarketDataService
from backend.services.portfolio_service import PortfolioService


# --- helpers ---------------------------------------------------------------------------

def _today():
    return datetime.now(timezone.utc).date()


def _iso(days_ago: int) -> str:
    return (_today() - timedelta(days=days_ago)).isoformat()


def _price_frame(tickers: list[str], dates: list[str], base: float = 100.0):
    """Synthetic yf.download result: MultiIndex (ticker, field) columns."""
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
    rows = []
    for i, _ in enumerate(dates):
        row = []
        for j, _t in enumerate(tickers):
            px = base + 10 * j + i
            row.extend([px - 1, px + 1, px - 2, px, 1000.0 + i])
        rows.append(row)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=cols)


def _flat_frame(dates: list[str], base: float = 50.0):
    """Single-ticker download shape: flat columns."""
    data = {
        "Open": [base - 1 + i for i in range(len(dates))],
        "High": [base + 1 + i for i in range(len(dates))],
        "Low": [base - 2 + i for i in range(len(dates))],
        "Close": [base + i for i in range(len(dates))],
        "Volume": [500.0] * len(dates),
    }
    return pd.DataFrame(data, index=pd.DatetimeIndex(dates))


@pytest.fixture
def no_sleep(monkeypatch):
    async def _noop(_seconds):
        return None
    monkeypatch.setattr(prices, "_sleep", _noop)


# --- price sync -----------------------------------------------------------------------

def test_sync_price_history_upserts_and_marks_prices(stores, monkeypatch, no_sleep):
    dates = [_iso(2), _iso(1)]
    calls = []

    def fake_download(chunk, start):
        calls.append((tuple(chunk), start))
        return _price_frame(chunk, dates)

    monkeypatch.setattr(prices, "_download_chunk", fake_download)
    res = asyncio.run(prices.sync_price_history(stores, ["aaa", "BBB"], years=1))
    assert res == {"tickers": 2, "rows": 4, "failed_chunks": 0}
    assert len(calls) == 1  # one chunk
    # Default (non-incremental) start derives from years.
    expected_start = (_today() - timedelta(days=365)).isoformat()
    assert calls[0][1] == expected_start

    bars = stores.bulk.price_range("AAA")
    assert [b["date"] for b in bars] == dates
    assert bars[-1]["close"] == 101.0 and bars[-1]["volume"] == 1001.0
    # Latest close marked for portfolio P&L.
    marks = stores.portfolio.prices()
    assert marks["AAA"] == 101.0 and marks["BBB"] == 111.0


def test_sync_price_history_chunks_and_survives_chunk_failure(stores, monkeypatch, no_sleep):
    dates = [_iso(1)]
    calls = []

    def fake_download(chunk, start):
        calls.append(tuple(chunk))
        if "AAA" in chunk:
            raise OSError("offline")
        return _price_frame(chunk, dates)

    monkeypatch.setattr(prices, "_download_chunk", fake_download)
    res = asyncio.run(prices.sync_price_history(stores, ["AAA", "BBB"], years=1, chunk_size=1))
    assert calls == [("AAA",), ("BBB",)]  # failure logged, sync continued
    assert res == {"tickers": 1, "rows": 1, "failed_chunks": 1}
    assert stores.bulk.latest_close("AAA") is None
    assert stores.bulk.latest_close("BBB") is not None


def test_sync_price_history_incremental_start(stores, monkeypatch, no_sleep):
    stores.bulk.upsert_prices([
        {"ticker": "AAA", "date": _iso(3), "close": 10.0},
        {"ticker": "BBB", "date": _iso(9), "close": 20.0},
    ])
    starts = []

    def fake_download(chunk, start):
        starts.append(start)
        return _price_frame(chunk, [_iso(1)])

    monkeypatch.setattr(prices, "_download_chunk", fake_download)
    # Chunk with stored data: start = min(last stored date) across the chunk.
    asyncio.run(prices.sync_price_history(stores, ["AAA", "BBB"], incremental=True))
    assert starts == [_iso(9)]
    # Ticker with no stored bars: full-depth backfill, not the incremental
    # fast path — otherwise a new holding gets one day of history forever.
    asyncio.run(prices.sync_price_history(stores, ["CCC"], years=1, incremental=True))
    assert starts[-1] == _iso(round(365.25))
    # Mixed chunk: seasoned tickers sync incrementally, the new ticker still
    # gets its own full-depth chunk.
    starts.clear()
    asyncio.run(prices.sync_price_history(stores, ["AAA", "DDD"], years=1, incremental=True))
    assert starts == [_iso(1), _iso(round(365.25))]


def test_sync_price_history_single_ticker_flat_frame(stores, monkeypatch, no_sleep):
    monkeypatch.setattr(prices, "_download_chunk",
                        lambda chunk, start: _flat_frame([_iso(1)]))
    res = asyncio.run(prices.sync_price_history(stores, ["solo"], years=1))
    assert res == {"tickers": 1, "rows": 1, "failed_chunks": 0}
    assert stores.bulk.latest_close("SOLO")["close"] == 50.0


def test_backfill_holdings_history_uses_holdings_depth(stores, monkeypatch, no_sleep):
    stores.portfolio.add_lot("AAA", 10, 50.0, "2025-01-02")
    stores.portfolio.rebuild_holdings()
    captured = {}

    async def fake_sync(s, tickers, years=None, **kw):
        captured["tickers"], captured["years"] = tickers, years
        return {"tickers": len(tickers), "rows": 0}

    monkeypatch.setattr(prices, "sync_price_history", fake_sync)
    asyncio.run(prices.backfill_holdings_history(stores))
    assert captured["tickers"] == ["AAA"]
    # Depth comes from config, not the universe default.
    assert captured["years"] == opconfig.load()["data"]["holdings_price_history_years"]


def test_price_chart_ranges(stores):
    stores.bulk.upsert_prices([
        {"ticker": "AAA", "date": _iso(5), "close": 11.0, "volume": 100},
        {"ticker": "AAA", "date": _iso(100), "close": 10.0, "volume": 90},
        {"ticker": "AAA", "date": _iso(300), "close": 9.0, "volume": 80},
        {"ticker": "AAA", "date": _iso(900), "close": 8.0, "volume": 70},
    ])
    assert [r["close"] for r in prices.price_chart(stores, "AAA", "1m")] == [11.0]
    assert [r["close"] for r in prices.price_chart(stores, "AAA", "6m")] == [10.0, 11.0]
    assert [r["close"] for r in prices.price_chart(stores, "AAA", "1y")] == [9.0, 10.0, 11.0]
    assert len(prices.price_chart(stores, "AAA", "5y")) == 4
    row = prices.price_chart(stores, "AAA", "1m")[0]
    assert row["date"] == _iso(5) and row["volume"] == 100


# --- insider ownership ------------------------------------------------------------------

SUBMISSION_TSV = (
    "ACCESSION_NUMBER\tISSUERTRADINGSYMBOL\tPERIOD_OF_REPORT\n"
    "0001-23-000001\tAAA\t31-MAR-2026\n"
    "0001-23-000002\tZZZ\t31-MAR-2026\n"
)
OWNER_TSV = (
    "ACCESSION_NUMBER\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\n"
    "0001-23-000001\tDOE JANE\tOfficer\n"
    "0001-23-000002\tROE RICHARD\tDirector\n"
)
TRANS_TSV = (
    "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\t"
    "TRANS_ACQUIRED_DISP_CD\n"
    "0001-23-000001\t15-FEB-2026\tP\t100\t12.50\tA\n"
    "0001-23-000001\t20-FEB-2026\tS\t40\t\tD\n"
    "0001-23-000002\t10-FEB-2026\tP\t999\t1.00\tA\n"
)


def _form345_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SUBMISSION.tsv", SUBMISSION_TSV)
        zf.writestr("REPORTINGOWNER.tsv", OWNER_TSV)
        zf.writestr("NONDERIV_TRANS.tsv", TRANS_TSV)
    return buf.getvalue()


def test_parse_form345_zip_joins_and_filters(tmp_path):
    path = tmp_path / "2026q1_form345.zip"
    path.write_bytes(_form345_zip_bytes())
    records = ownership.parse_form345_zip(path, {"AAA"})
    assert len(records) == 2  # ZZZ filtered out
    buy, sell = records
    assert buy["ticker"] == "AAA" and buy["as_of"] == "2026-02-15"
    assert buy["owner_name"] == "DOE JANE" and buy["owner_role"] == "Officer"
    assert buy["txn_type"] == "buy" and buy["shares"] == 100.0
    assert buy["value"] == pytest.approx(1250.0)
    assert buy["payload"]["accession"] == "0001-23-000001"
    assert sell["txn_type"] == "sell" and sell["shares"] == 40.0
    assert sell["value"] is None  # no price → no value


def test_sync_ownership_inserts_and_dedupes(stores, monkeypatch, tmp_path):
    monkeypatch.setattr(opconfig, "cache_dir", lambda: tmp_path / "cache")
    downloads = []

    def fake_download(url, dest):
        downloads.append(url)
        dest.write_bytes(_form345_zip_bytes())

    monkeypatch.setattr(ownership, "_download_quarter", fake_download)
    res = asyncio.run(ownership.sync_ownership(stores, ["AAA"], quarters=2))
    assert res["quarters"] == 2
    assert res["records"] == 2  # identical quarter fixtures dedupe to one set
    rows = stores.bulk.ownership_for("AAA", kind="insider_transaction")
    assert len(rows) == 2
    assert {r["txn_type"] for r in rows} == {"buy", "sell"}
    assert all(r["source_id"] for r in rows)  # evidence source per quarter file

    # Second sync: cached zips reused (no new downloads), rows deduped.
    res2 = asyncio.run(ownership.sync_ownership(stores, ["AAA"], quarters=2))
    assert res2["records"] == 0
    assert len(downloads) == 2
    assert len(stores.bulk.ownership_for("AAA", kind="insider_transaction")) == 2


def test_sync_ownership_falls_back_when_current_quarter_missing(stores, monkeypatch, tmp_path):
    monkeypatch.setattr(opconfig, "cache_dir", lambda: tmp_path / "cache")
    attempts = []

    def fake_download(url, dest):
        attempts.append(url)
        if len(attempts) == 1:  # current quarter not published yet
            raise OSError("404")
        dest.write_bytes(_form345_zip_bytes())

    monkeypatch.setattr(ownership, "_download_quarter", fake_download)
    res = asyncio.run(ownership.sync_ownership(stores, ["AAA"], quarters=1))
    assert res["quarters"] == 1 and len(attempts) == 2


# --- market data: local-first (ADR-0059) -------------------------------------------------

def _no_network(monkeypatch):
    def boom(self, *a, **kw):
        raise AssertionError("live provider call attempted in local-first path")
    monkeypatch.setattr(MarketDataService, "_yfinance", boom)
    monkeypatch.setattr(MarketDataService, "_edgar", boom)


def _seed_metrics(stores, ticker: str) -> None:
    ent = stores.identity.ensure_entity(ticker, name=f"{ticker} Corp")
    stores.financial.store_metrics_snapshot(
        ent["id"], {"roic": 0.2, "revenue": 1e9}, "2026-03-31", "annual",
        {"source": "test-fixture"},
    )


def test_metrics_for_never_fetches_after_bootstrap(stores, monkeypatch):
    _no_network(monkeypatch)

    async def boom_fetch(self, ticker):
        raise AssertionError(f"live fundamentals fetch for {ticker}")

    monkeypatch.setattr(MarketDataService, "fetch_fundamentals", boom_fetch)
    stores.bulk.set_state("bootstrap_done", "1")
    _seed_metrics(stores, "AAA")

    svc = MarketDataService(stores)
    out = asyncio.run(svc.metrics_for(["AAA", "MISS"], allow_fetch=True))
    assert out["AAA"]["roic"] == 0.2
    assert "MISS" not in out  # absent = unevaluable, never live-fetched

    # Missing ticker enqueued for later top-up — deduped on repeat calls.
    queued = [w for w in stores.ops.queue_state(limit=50) if w["kind"] == "fact_topup"]
    assert [w["payload"]["ticker"] for w in queued] == ["MISS"]
    asyncio.run(svc.metrics_for(["MISS"], allow_fetch=True))
    queued = [w for w in stores.ops.queue_state(limit=50) if w["kind"] == "fact_topup"]
    assert len(queued) == 1


def test_refresh_quotes_serves_stored_closes_without_network(stores, monkeypatch):
    _no_network(monkeypatch)
    today = _today().isoformat()
    stores.bulk.upsert_prices([
        {"ticker": "AAA", "date": today, "close": 42.0},
        {"ticker": "BBB", "date": _iso(4), "close": 17.0},
    ])
    quotes = asyncio.run(MarketDataService(stores).refresh_quotes(["AAA", "BBB"]))
    assert quotes["AAA"] == {"symbol": "AAA", "price": 42.0, "stale": False}
    assert quotes["BBB"] == {"symbol": "BBB", "price": 17.0, "stale": True}


def test_refresh_quotes_live_fetch_only_for_uncovered_or_on_request(stores, monkeypatch):
    fetched = []

    class FakeConnector:
        async def get_quotes(self, tickers):
            fetched.append(tuple(tickers))

            class R:
                ok = True
                data = [{"symbol": t, "price": 99.0} for t in tickers]
            return R()

    monkeypatch.setattr(MarketDataService, "_yfinance", lambda self: FakeConnector())
    stores.bulk.upsert_prices([{"ticker": "AAA", "date": _iso(1), "close": 41.0}])

    svc = MarketDataService(stores)
    quotes = asyncio.run(svc.refresh_quotes(["AAA", "NEW"]))
    assert fetched == [("NEW",)]  # only the ticker with no stored price
    assert quotes["AAA"]["price"] == 41.0 and quotes["AAA"]["stale"] is True
    assert quotes["NEW"]["price"] == 99.0

    quotes = asyncio.run(svc.refresh_quotes(["AAA"], live=True))
    assert fetched[-1] == ("AAA",)  # explicit live refresh fetches everything
    assert quotes["AAA"]["price"] == 99.0


def test_fetch_fundamentals_skips_sec_when_observations_fresh(stores, monkeypatch):
    _no_network(monkeypatch)
    ent = stores.identity.ensure_entity("AAA")
    stores.financial.add_observation(
        ent["id"], "revenue", _iso(30), "quarterly", 5e8)
    out = asyncio.run(MarketDataService(stores).fetch_fundamentals("AAA"))
    assert out["revenue"] == 5e8 and out["entity_id"] == ent["id"]


def test_portfolio_refresh_prices_upserts_todays_close(stores, monkeypatch):
    class FakeConnector:
        async def get_quotes(self, tickers):
            class R:
                ok = True
                data = [{"symbol": t, "price": 60.0} for t in tickers]
            return R()

    monkeypatch.setattr(MarketDataService, "_yfinance", lambda self: FakeConnector())
    stores.portfolio.add_lot("AAA", 10, 50.0, "2025-01-02")
    stores.portfolio.rebuild_holdings()

    n = asyncio.run(PortfolioService(stores).refresh_prices())
    assert n == 1
    latest = stores.bulk.latest_close("AAA")
    assert latest == {"date": _today().isoformat(), "close": 60.0}
    assert stores.portfolio.prices()["AAA"] == 60.0
