"""Macro context from FRED's keyless CSV endpoint.

fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES serves public series with
no API key. A small fixed set is cached into macro_series on the daily tick;
the Dashboard strip and the chat `get_macro` tool read only the local cache,
so macro context costs one tiny CSV per series per day and works offline
after the first sync.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

log = logging.getLogger("fundops.macro")

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
FETCH_TIMEOUT_S = 15
HISTORY_YEARS = 6

# series id -> (label, kind). kind: 'pct_points' renders as-is with %,
# 'yoy_pct' derives the 12-month change from a level index.
MACRO_SERIES: dict[str, tuple[str, str]] = {
    "DGS10": ("10Y Treasury", "pct_points"),
    "DFF": ("Fed funds", "pct_points"),
    "UNRATE": ("Unemployment", "pct_points"),
    "CPIAUCSL": ("CPI YoY", "yoy_pct"),
}


def _fetch_csv(series: str, start: str) -> list[dict]:
    """Sync CSV fetch+parse (runs on a worker thread)."""
    url = FRED_CSV_URL.format(series=series, start=start)
    req = urllib.request.Request(url, headers={"User-Agent": "FundOps local workspace"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    points = []
    for line in text.splitlines()[1:]:
        parts = line.strip().split(",")
        if len(parts) != 2 or parts[1] in (".", ""):
            continue
        try:
            points.append({"date": parts[0], "value": float(parts[1])})
        except ValueError:
            continue
    return points


async def sync_macro(stores) -> dict:
    """Refresh the local macro cache. Best-effort per series, recording a
    per-series sync error/timestamp so a permanently-failing series (DGS10/DFF
    never caching) is distinguishable from "never attempted" rather than just
    silently absent (#24)."""
    from backend.core.workspace import now_iso

    start = (datetime.now(timezone.utc).date()
             - timedelta(days=round(HISTORY_YEARS * 365.25))).isoformat()
    stored: dict[str, int] = {}
    for series in MACRO_SERIES:
        try:
            points = await asyncio.wait_for(
                asyncio.to_thread(_fetch_csv, series, start), timeout=FETCH_TIMEOUT_S + 5)
        except Exception as exc:  # offline / persistent failure: record why
            log.warning("macro fetch failed for %s: %s", series, exc)
            stores.bulk.set_state(f"macro_sync_error_{series}", f"{now_iso()}: {exc}")
            continue
        stored[series] = stores.context.upsert_macro(series, points)
        stores.bulk.set_state(f"macro_sync_error_{series}", "")
        stores.bulk.set_state(f"macro_sync_at_{series}", now_iso())
    return {"series": stored}


def _yoy(stores, series: str) -> tuple[float | None, str | None]:
    points = stores.context.macro_points(series, limit=30)
    if not points:
        return None, None
    latest = points[-1]
    target = (datetime.fromisoformat(latest["date"]) - timedelta(days=365)).date().isoformat()
    base = None
    for p in stores.context.macro_points(series, limit=600):
        if p["date"] <= target:
            base = p["value"]
    if base in (None, 0):
        return None, latest["date"]
    return (latest["value"] / base - 1) * 100, latest["date"]


def macro_strip(stores) -> list[dict]:
    """Latest value per series for the Dashboard strip + chat. Local-only."""
    out = []
    for series, (label, kind) in MACRO_SERIES.items():
        if kind == "yoy_pct":
            value, as_of = _yoy(stores, series)
        else:
            latest = stores.context.macro_latest(series)
            value, as_of = (latest["value"], latest["date"]) if latest else (None, None)
        err = stores.bulk.get_state(f"macro_sync_error_{series}")
        out.append({
            "series": series, "label": label,
            "value": value,
            "display": f"{value:.2f}%" if value is not None else "—",
            "as_of": as_of,
            "last_sync_error": err or None,
            "last_sync_at": stores.bulk.get_state(f"macro_sync_at_{series}") or None,
        })
    return out


def macro_history(stores, series: str, limit: int = 260) -> list[dict]:
    return stores.context.macro_points(series, limit=limit)
