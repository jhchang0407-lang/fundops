"""On-demand company news via yfinance.

News is the one Company Page section served live: headlines are context, not
evidence, so they are NOT retained as workspace records — the response says
so. A short in-process TTL cache keeps repeated page views from hammering
the provider; offline the section simply reports unavailability.

yfinance has shipped two news shapes (flat pre-0.2.50, nested 'content'
after); both are handled.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

log = logging.getLogger("fundops.news")

FETCH_TIMEOUT_S = 15
CACHE_TTL_S = 900
MAX_ITEMS = 12
_cache: dict[str, tuple[float, list[dict]]] = {}


def _normalize_item(raw: dict) -> dict | None:
    """Tolerate both yfinance news shapes; return None for unusable rows."""
    content = raw.get("content") if isinstance(raw.get("content"), dict) else None
    if content:  # yfinance >= 0.2.50
        title = content.get("title")
        url = ((content.get("canonicalUrl") or {}).get("url")
               or (content.get("clickThroughUrl") or {}).get("url"))
        publisher = (content.get("provider") or {}).get("displayName")
        published = content.get("pubDate") or content.get("displayTime")
        if published:
            published = str(published)[:10]
    else:  # legacy flat shape
        title = raw.get("title")
        url = raw.get("link")
        publisher = raw.get("publisher")
        ts = raw.get("providerPublishTime")
        published = (datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                     if isinstance(ts, (int, float)) else None)
    if not title or not url:
        return None
    return {"title": title, "url": url, "publisher": publisher, "published": published}


def _fetch_news(ticker: str) -> list[dict]:
    """Sync provider call (runs on a worker thread)."""
    import yfinance as yf

    raw = yf.Ticker(ticker).news or []
    items = [n for r in raw if (n := _normalize_item(r))]
    return items[:MAX_ITEMS]


async def company_news(ticker: str) -> dict:
    """{items, live, note} — cached for CACHE_TTL_S, empty+note offline."""
    ticker = ticker.upper()
    now = time.monotonic()
    cached = _cache.get(ticker)
    if cached and now - cached[0] < CACHE_TTL_S:
        return {"items": cached[1], "live": True,
                "note": "Live headlines (cached briefly) — context only, not retained evidence."}
    try:
        items = await asyncio.wait_for(
            asyncio.to_thread(_fetch_news, ticker), timeout=FETCH_TIMEOUT_S + 5)
    except Exception as exc:
        log.debug("news fetch failed for %s: %s", ticker, exc)
        return {"items": cached[1] if cached else [], "live": False,
                "note": "News unavailable right now (offline or rate-limited)."}
    _cache[ticker] = (now, items)
    return {"items": items, "live": True,
            "note": "Live headlines — context only, not retained evidence."}
