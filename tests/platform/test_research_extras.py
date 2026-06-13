"""News, EDGAR full-text search, peer deep-dive runs, decision attribution,
factor tilts — all offline-deterministic (network seams monkeypatched)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.services import fulltext_search, news
from backend.services.portfolio_service import PortfolioService

from tests.platform.conftest import FAKE_METRICS, _persist


@pytest.fixture
def client(stores, offline_ai):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def seeded(stores):
    return {t: _persist(stores, t, m) for t, m in FAKE_METRICS.items()}


# --- news (both yfinance shapes, offline degradation) ------------------------------

def test_news_normalizes_both_provider_shapes():
    legacy = {"title": "Old shape", "link": "https://x/1", "publisher": "Wire",
              "providerPublishTime": 1750000000}
    nested = {"content": {"title": "New shape", "pubDate": "2026-06-10T12:00:00Z",
                          "canonicalUrl": {"url": "https://x/2"},
                          "provider": {"displayName": "Feed"}}}
    junk = {"content": {"summary": "no title"}}
    a, b, c = news._normalize_item(legacy), news._normalize_item(nested), news._normalize_item(junk)
    assert a["title"] == "Old shape" and a["published"]
    assert b == {"title": "New shape", "url": "https://x/2", "publisher": "Feed",
                 "published": "2026-06-10"}
    assert c is None


def test_news_route_degrades_offline(client, stores, seeded, monkeypatch):
    def boom(t):
        raise OSError("offline")
    monkeypatch.setattr(news, "_fetch_news", boom)
    news._cache.clear()
    out = client.get("/api/company/AAA/news").json()
    assert out["live"] is False and out["items"] == []
    assert "unavailable" in out["note"]


def test_news_route_serves_and_caches(client, stores, seeded, monkeypatch):
    calls = {"n": 0}

    def fake(t):
        calls["n"] += 1
        return [{"title": "AAA wins contract", "url": "https://x/3",
                 "publisher": "Wire", "published": "2026-06-11"}]
    monkeypatch.setattr(news, "_fetch_news", fake)
    news._cache.clear()
    out = client.get("/api/company/AAA/news").json()
    assert out["live"] is True and out["items"][0]["title"] == "AAA wins contract"
    client.get("/api/company/AAA/news")
    assert calls["n"] == 1  # TTL cache absorbed the second view


# --- EDGAR full-text search ----------------------------------------------------------

EFTS_PAYLOAD = {
    "hits": {
        "total": {"value": 2},
        "hits": [
            {"_id": "0001-23-000045:doc.htm",
             "_source": {"cik": "1069183", "file_type": "10-K", "file_date": "2026-02-01",
                         "display_names": ["Alpha Corp  (AAA)  (CIK 0001069183)"]}},
            {"_id": "0009-23-000099:doc.htm",
             "_source": {"cik": "999999", "file_type": "8-K", "file_date": "2026-03-01",
                         "display_names": ["Unrelated Co  (ZZZT)  (CIK 0000999999)"]}},
        ],
    }
}


def test_fulltext_search_maps_tickers_and_universe(client, stores, seeded,
                                                   constitution, monkeypatch):
    monkeypatch.setattr(fulltext_search, "_fetch", lambda q, f: EFTS_PAYLOAD)
    out = client.get("/api/research/fulltext", params={"q": "drone"}).json()
    assert out["ok"] is True and out["total"] == 2
    aaa = next(h for h in out["hits"] if h["ticker"] == "AAA")
    assert aaa["known"] is True and aaa["in_universe"] is True  # AAA in test universe
    zzzt = next(h for h in out["hits"] if h["ticker"] == "ZZZT")
    assert zzzt["known"] is False and zzzt["in_universe"] is False


def test_fulltext_search_offline_is_graceful(client, stores, monkeypatch):
    def boom(q, f):
        raise OSError("offline")
    monkeypatch.setattr(fulltext_search, "_fetch", boom)
    out = client.get("/api/research/fulltext", params={"q": "tariffs"}).json()
    assert out["ok"] is False and out["hits"] == []


# --- peer deep-dive run ----------------------------------------------------------------

def test_peer_deep_dive_run_offline(client, stores, seeded):
    out = client.post("/api/research/runs",
                      json={"kind": "peer_deep_dive", "tickers": ["AAA", "BBB"]}).json()
    assert out["ok"] is True
    art = stores.artifacts.get(out["artifact_id"])
    assert art["kind"] == "industry_note"
    assert art["payload"]["body"]["kind"] == "peer_deep_dive"
    assert art["payload"]["body"]["tickers"] == ["AAA", "BBB"]


# --- decision attribution + factor tilts -------------------------------------------------

def _seed_bars(stores, ticker, start_price, gain, days=120):
    today = datetime.now(timezone.utc).date()
    rows, price = [], start_price
    for d in range(days, 0, -1):
        rows.append({"ticker": ticker, "date": (today - timedelta(days=d)).isoformat(),
                     "close": round(price, 4), "volume": 1e6})
        price *= 1 + gain
    stores.bulk.upsert_prices(rows)


def test_decision_attribution_measures_forward_returns(stores, seeded):
    from backend.core.workspace import now_iso
    from backend.services.portfolio_analytics import decision_attribution

    _seed_bars(stores, "AAA", 100.0, 0.002)   # riser
    _seed_bars(stores, "DDD", 100.0, -0.002)  # faller
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    with stores.ws.transaction() as conn:
        for ticker, action in (("AAA", "promote"), ("DDD", "dismiss")):
            conn.execute(
                "INSERT INTO selection_events (id, capability, run_id, ticker, action, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (f"sel_{ticker}", "screener", None, ticker, action, old))
        # too-young event must be excluded
        conn.execute(
            "INSERT INTO selection_events (id, capability, run_id, ticker, action, created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("sel_new", "screener", None, "AAA", "dismiss", now_iso()))
    out = decision_attribution(stores)
    assert out["events_measured"] == 2
    assert out["promoted_avg_return"] > 0
    assert out["dismissed_avg_return"] < 0


def test_factor_tilts_weighted_percentiles(stores, seeded):
    from backend.services.portfolio_analytics import factor_tilts

    # Hold the highest-ROIC name (AAA, 0.25) — quality tilt must be > p50.
    stores.portfolio.mark_price("AAA", 100.0)
    PortfolioService(stores).add_lot("AAA", 10, 90.0, "2026-01-02")
    tilts = {t["factor"]: t for t in factor_tilts(stores)}
    assert tilts["quality"]["percentile"] is not None
    assert tilts["quality"]["percentile"] > 50
