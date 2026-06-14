"""Universe auto-refresh (universe_refresh.py): CSV parsing, source merge + diff,
the sanity floor (a broken fetch must never shrink the universe), the live-list
preference in universe_tickers, and the quarterly-due check. No network — the
constituent fetchers are monkeypatched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.core import opconfig
from backend.services.ingest import scheduler
from backend.services.ingest import sync as ingest_sync
from backend.services.ingest import universe_refresh as ur


def test_clean_normalizes_and_dedupes():
    assert ur._clean(["aapl", "MSFT", " nvda ", "AAPL", "", "BAD TICKER!!", "BRK.B"]) == \
        ["AAPL", "MSFT", "NVDA", "BRK.B"]


def test_csv_column_skips_preamble():
    # iShares-style metadata preamble before the real header row.
    text = ("IShares Russell 2000 ETF,\nInception Date,2000\n\n"
            "Ticker,Name,Weight (%)\nAAA,Alpha,1.2\nBBB,Beta,0.9\n,Cash,0.1\n")
    assert ur._csv_column(text, ("ticker", "symbol")) == ["AAA", "BBB"]


def test_refresh_merges_sources_diffs_and_stores(stores, monkeypatch):
    monkeypatch.setattr(ur, "_UNIVERSE_MIN", 3)
    monkeypatch.setattr(ur, "_COMPONENT_MIN", 2)
    monkeypatch.setattr(ur, "load_preset", lambda n: ["AAA", "BBB", "OLD"])
    monkeypatch.setattr(ur, "fetch_sp500", lambda: ["AAA", "BBB", "NEW"])  # OLD dropped, NEW added
    stores.identity.ensure_entity("OLD")   # ingested but no longer in the index
    stores.identity.ensure_entity("AAA")   # ingested and still in the index

    res = ur.refresh_universe(stores, name="sp500")
    assert res["refreshed"] is True and res["sources_live"] == ["sp500"]
    assert "NEW" in res["added"] and "AAA" not in res["added"]   # NEW needs ingest; AAA exists
    assert res["removed"] == ["OLD"]                              # left the index (kept, not quarantined)
    assert ur.current_universe("sp500") == ["AAA", "BBB", "NEW"]
    # universe_tickers now prefers the stored live list.
    monkeypatch.setattr(opconfig, "load", lambda refresh=False: {"data": {"universe_default": "sp500"}})
    assert sorted(ingest_sync.universe_tickers()) == ["AAA", "BBB", "NEW"]


def test_broken_component_falls_back_to_bundled(stores, monkeypatch):
    monkeypatch.setattr(ur, "load_preset", lambda n: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(ur, "fetch_sp500", lambda: [])      # fetch failed
    monkeypatch.setattr(ur, "_COMPONENT_MIN", 2)
    monkeypatch.setattr(ur, "_UNIVERSE_MIN", 2)
    res = ur.refresh_universe(stores, name="sp500")
    assert res["refreshed"] is True and res["sources_live"] == []  # kept bundled
    assert res["total"] == 3


def test_below_floor_keeps_current_and_stores_nothing(stores, monkeypatch):
    monkeypatch.setattr(ur, "load_preset", lambda n: ["A", "B"])
    monkeypatch.setattr(ur, "fetch_sp500", lambda: ["A", "B"])
    monkeypatch.setattr(ur, "_COMPONENT_MIN", 1)
    monkeypatch.setattr(ur, "_UNIVERSE_MIN", 5)             # merged (2) below the floor
    res = ur.refresh_universe(stores, name="sp500")
    assert res["refreshed"] is False and "floor" in res["reason"]
    assert ur.current_universe("sp500") is None              # nothing was overwritten


def test_universe_with_no_source_is_noop(stores):
    res = ur.refresh_universe(stores, name="starter_30")
    assert res["refreshed"] is False and res["added"] == []


def test_universe_refresh_due(stores):
    assert scheduler._universe_refresh_due(stores) is True          # never refreshed
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    stores.bulk.set_state("universe_refreshed_at", recent)
    assert scheduler._universe_refresh_due(stores) is False
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    stores.bulk.set_state("universe_refreshed_at", old)
    assert scheduler._universe_refresh_due(stores) is True
