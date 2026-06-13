"""Company events ingestion + the merged events view.

Two halves:
- sync_company_events: best-effort yfinance calendar pulls (earnings dates,
  ex-dividend dates) for a SMALL ticker scope — holdings and watchlists, not
  the whole universe (one network call per ticker). Failures skip quietly;
  events land in company_events via the context store.
- events_view / upcoming_view: pure local reads merging stored calendar
  events with the retained filings index (10-K/Q, 8-K, S-3/S-4 dilution/M&A
  flags) and insider-transaction clusters, so the Company Page Events tab and
  the Dashboard upcoming strip never trigger network work.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

log = logging.getLogger("fundops.ingest.events")

EVENT_FETCH_TIMEOUT_S = 20
EVENT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "S-3", "S-4",
               "SC 13D", "SC 13G", "DEF 14A")
FORM_LABELS = {
    "10-K": "Annual report filed", "10-K/A": "Annual report amended",
    "10-Q": "Quarterly report filed", "10-Q/A": "Quarterly report amended",
    "8-K": "Material event reported", "S-3": "Shelf registration (dilution watch)",
    "S-4": "Registration for M&A/exchange", "DEF 14A": "Proxy statement",
    "SC 13D": "Activist/large holder filing", "SC 13G": "Large holder filing",
}


def _calendar_rows(ticker: str) -> list[dict]:
    """Sync yfinance calendar fetch (runs on a worker thread)."""
    import yfinance as yf

    cal = yf.Ticker(ticker).calendar
    if not isinstance(cal, dict):  # older yfinance returned a DataFrame
        cal = {}
    rows: list[dict] = []
    for d in cal.get("Earnings Date") or []:
        rows.append({"kind": "earnings", "date": str(d)[:10], "label": "Earnings"})
    exdiv = cal.get("Ex-Dividend Date")
    if exdiv:
        rows.append({"kind": "dividend", "date": str(exdiv)[:10], "label": "Ex-dividend"})
    return rows


async def sync_company_events(stores, tickers: list[str]) -> dict:
    """Pull calendar events for a small scope of tickers. Returns counts.
    A successful pull replaces the ticker's FUTURE rows of the same kind, so
    a shifted earnings estimate never leaves a phantom date behind."""
    today = datetime.now(timezone.utc).date().isoformat()
    stored = 0
    fetched = 0
    for t in dict.fromkeys(x.upper() for x in tickers):
        try:
            rows = await asyncio.wait_for(
                asyncio.to_thread(_calendar_rows, t), timeout=EVENT_FETCH_TIMEOUT_S)
            fetched += 1
        except Exception as exc:  # offline / rate limited: skip quietly
            log.debug("calendar fetch failed for %s: %s", t, exc)
            continue
        for kind in {r["kind"] for r in rows}:
            stores.context.clear_future_events(t, kind, today)
        for r in rows:
            stores.context.upsert_event(t, r["kind"], r["date"], label=r["label"])
            stored += 1
        await asyncio.sleep(0.1)
    return {"tickers": fetched, "events": stored}


def event_scope(stores) -> list[str]:
    """Holdings + watchlist tickers: the small set worth per-ticker calls.
    With data.events_full_universe enabled, widen to the configured universe so
    screened/research names also get calendar coverage — OPT-IN, because it makes
    sync_company_events fan out one network call per universe ticker."""
    tickers = {h["ticker"] for h in stores.portfolio.holdings()}
    for wl in stores.context.list_watchlists():
        tickers.update(wl["tickers"])
    try:
        from backend.core import opconfig
        if opconfig.load()["data"].get("events_full_universe"):
            from backend.services.ingest.sync import universe_tickers
            tickers.update(universe_tickers())
    except Exception as exc:  # config/universe load issues must not break the read
        log.debug("events_full_universe scope widening skipped: %s", exc)
    return sorted(tickers)


def events_empty_reason(stores, ticker: str) -> str:
    """Why a ticker's Events tab is empty: in-scope names are awaiting the next
    sync; out-of-scope names aren't tracked until watchlisted."""
    ticker = ticker.upper()
    if ticker in set(event_scope(stores)):
        return (f"No events retained yet for {ticker} — calendar, filing, and insider "
                "events arrive with the next daily sync.")
    return ("Calendar events are tracked for holdings and watchlisted tickers; add "
            f"{ticker} to a watchlist to begin tracking its earnings/dividend dates.")


# --- merged read views -----------------------------------------------------------------

def events_view(stores, ticker: str, limit: int = 60) -> list[dict]:
    """All known events for one ticker, newest first:
    {date, kind, label, detail?} — calendar events, filings, insider clusters."""
    ticker = ticker.upper()
    out: list[dict] = []
    for e in stores.context.events_for(ticker, limit=20):
        out.append({"date": e["event_date"], "kind": e["kind"],
                    "label": e["label"] or e["kind"].capitalize(), "source": e["source"]})
    for f in stores.bulk.filings_for(ticker, forms=list(EVENT_FORMS), limit=40):
        out.append({"date": str(f["filed_at"])[:10], "kind": "filing",
                    "label": FORM_LABELS.get(f["form"], f"{f['form']} filed"),
                    "detail": f["form"], "source": "sec_index"})
    monthly: dict[tuple[str, str], float] = defaultdict(float)
    for r in stores.bulk.ownership_for(ticker, kind="insider_transaction", limit=200):
        txn = (r.get("txn_type") or "").lower()
        if txn not in ("buy", "sell"):
            continue  # unknown transaction codes must not masquerade as sells
        month = str(r["as_of"])[:7]
        sign = 1 if txn == "buy" else -1
        monthly[(month, "insider")] += sign * (r.get("shares") or 0)
    for (month, _), net in sorted(monthly.items(), reverse=True)[:12]:
        if net == 0:
            continue
        side = "buying" if net > 0 else "selling"
        out.append({"date": f"{month}-01", "kind": "insider_cluster",
                    "label": f"Net insider {side} ({abs(net):,.0f} shares)",
                    "source": "forms_345"})
    out.sort(key=lambda e: e["date"], reverse=True)
    return out[:limit]


def upcoming_view(stores, days_ahead: int = 45, limit: int = 20) -> list[dict]:
    """Future calendar events for holdings + watchlists (Dashboard strip).
    The horizon bounds the query itself so far-future rows can never crowd
    near-term ones out of the LIMIT."""
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=days_ahead)).isoformat()
    scope = event_scope(stores)
    if not scope:
        return []
    rows = stores.context.upcoming_events(today.isoformat(), tickers=scope,
                                          before=horizon, limit=limit)
    return [{"ticker": r["ticker"], "date": r["event_date"], "kind": r["kind"],
             "label": r["label"] or r["kind"].capitalize()}
            for r in rows]
