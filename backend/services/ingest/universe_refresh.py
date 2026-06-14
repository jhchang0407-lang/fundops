"""Keep the Screened Universe current with index reconstitution (free sources).

Index membership drifts — the S&P 500 rebalances quarterly, the Russell indices
reconstitute every June — so the bundled ticker lists go stale. This refreshes
the LIVE universe from free public sources (a clean S&P 500 constituents CSV, the
iShares IWM holdings CSV for the Russell 2000), unions them with the bundled
curated lists, and stores the result as the active universe; a follow-up sync
ingests any newly-added names. Quarantine of genuinely-dataless names is handled
separately by IdentityStore.reconcile_phantom_status.

Hard safety rule: a failed or implausibly-small fetch must NEVER shrink the
universe — each source falls back to its bundled list, and the merged result is
rejected (kept as-is) unless it clears a sanity floor. Best-effort: every fetch
degrades to the bundled fallback, never raises.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import urllib.request
from datetime import datetime, timezone

from backend.core import opconfig
from backend.data.universes import load_preset

log = logging.getLogger("fundops.universe_refresh")

FETCH_TIMEOUT_S = 30
# Clean, maintained S&P 500 constituents (Symbol,Security,...). datahub mirror.
SP500_CSV_URL = ("https://raw.githubusercontent.com/datasets/"
                 "s-and-p-500-companies/main/data/constituents.csv")
# iShares Russell 2000 ETF (IWM) daily holdings CSV — the public free Russell set.
RUSSELL_IWM_URL = ("https://www.ishares.com/us/products/239710/"
                   "ishares-russell-2000-etf/1467271812596.ajax"
                   "?fileType=csv&fileName=IWM_holdings&dataType=fund")

# A refreshed component must retain at least this fraction of its bundled
# baseline, else the fetch is treated as broken and the bundled list is kept.
SANITY_FRACTION = 0.8
_COMPONENT_MIN = 50     # absolute floor for one accepted live component
_UNIVERSE_MIN = 100     # absolute floor for the merged universe
_CURRENT_KEY = "universe_current"      # JSON {name, tickers, at, sources}
_REFRESH_AT_KEY = "universe_refreshed_at"

_TICKER_OK = __import__("re").compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _http_text(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": opconfig.load()["providers"]["sec_user_agent"]})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean(symbols) -> list[str]:
    """Normalize + dedupe; drop anything that isn't a plausible ticker."""
    seen, out = set(), []
    for s in symbols:
        t = str(s or "").strip().upper().replace(" ", "")
        if t and _TICKER_OK.match(t) and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _csv_column(text: str, candidates: tuple[str, ...]) -> list[str]:
    """Pull the first matching column from CSV text, tolerating preamble rows
    (iShares prepends fund metadata before the real header)."""
    lines = text.splitlines()
    for start in range(min(len(lines), 12)):  # find the header row
        header = [h.strip().strip('"').lower() for h in next(csv.reader([lines[start]]))]
        col = next((i for i, h in enumerate(header) if h in candidates), None)
        if col is None:
            continue
        rows = csv.reader(io.StringIO("\n".join(lines[start + 1:])))
        return _clean(r[col] for r in rows if len(r) > col)
    return []


def fetch_sp500() -> list[str]:
    try:
        return _csv_column(_http_text(SP500_CSV_URL), ("symbol", "ticker"))
    except Exception as exc:  # noqa: BLE001 — best-effort, fall back to bundled
        log.warning("S&P 500 constituent fetch failed: %s", exc)
        return []


def fetch_russell2000() -> list[str]:
    try:
        return _csv_column(_http_text(RUSSELL_IWM_URL), ("ticker", "symbol"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Russell 2000 (iShares IWM) fetch failed: %s", exc)
        return []


# Components of each refreshable universe → (live fetcher name | None, bundled
# preset). Fetchers are referenced by name so they resolve through the module at
# call time (monkeypatchable in tests). Curated lists with no public source
# (us_largecap_200) stay static via None.
_COMPONENTS = {
    "broad_market": [
        ("fetch_sp500", "sp500"),
        ("fetch_russell2000", "russell2000"),
        (None, "nasdaq100"),
        (None, "us_largecap_200"),
    ],
    "sp500": [("fetch_sp500", "sp500")],
    "russell2000": [("fetch_russell2000", "russell2000")],
}


def _component_list(fetcher, preset: str) -> tuple[list[str], bool]:
    """A component's tickers: the live fetch when it clears the sanity floor,
    else the bundled list. Returns (tickers, refreshed_from_source)."""
    bundled = _clean(load_preset(preset))
    if fetcher is None:
        return bundled, False
    fresh = fetcher()
    if len(fresh) >= max(_COMPONENT_MIN, int(len(bundled) * SANITY_FRACTION)):
        return fresh, True
    log.warning("%s live fetch returned %d (< %.0f%% of %d bundled) — keeping bundled",
                preset, len(fresh), SANITY_FRACTION * 100, len(bundled))
    return bundled, False


def refresh_universe(stores, name: str | None = None) -> dict:
    """Recompute the active universe from sources, store it as the live list, and
    diff against currently-ingested entities. Does NOT itself sync new names —
    the caller triggers ingest (the returned `added` says whether it's needed).
    Pure + degradation-safe: on total failure it keeps the bundled universe."""
    name = name or opconfig.load()["data"]["universe_default"]
    components = _COMPONENTS.get(name)
    if not components:  # universe has no refresh source — nothing to do
        return {"name": name, "refreshed": False, "reason": "no source configured",
                "added": [], "removed": [], "total": len(_clean(load_preset(name)))}

    merged: list[str] = []
    seen: set[str] = set()
    sources_live = []
    for fname, preset in components:
        fetcher = globals().get(fname) if fname else None
        tickers, live = _component_list(fetcher, preset)
        if live:
            sources_live.append(preset)
        for t in tickers:
            if t not in seen:
                seen.add(t)
                merged.append(t)
    merged.sort()

    # Sanity: never let a bad merge shrink the universe below the bundled floor.
    baseline = len(_clean(load_preset(name)))
    if len(merged) < max(_UNIVERSE_MIN, int(baseline * SANITY_FRACTION)):
        log.warning("refreshed %s universe (%d) below floor of %d — keeping current",
                    name, len(merged), baseline)
        return {"name": name, "refreshed": False, "reason": "below sanity floor",
                "added": [], "removed": [], "total": baseline}

    prev = set(t["ticker"] for t in stores.ws.query(
        "SELECT DISTINCT ticker FROM ticker_aliases WHERE valid_to IS NULL"))
    fresh_set = set(merged)
    added = sorted(fresh_set - prev)        # need ingest
    removed = sorted(prev - fresh_set)      # left the index — retained, not quarantined

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stores.bulk.set_state(_CURRENT_KEY, json.dumps(
        {"name": name, "tickers": merged, "at": now, "sources_live": sources_live}))
    stores.bulk.set_state(_REFRESH_AT_KEY, now)
    log.info("universe %s refreshed: %d tickers (live: %s); +%d new, %d dropped",
             name, len(merged), ",".join(sources_live) or "none", len(added), len(removed))
    return {"name": name, "refreshed": True, "total": len(merged),
            "added": added, "removed": removed, "sources_live": sources_live, "at": now}


def current_universe(name: str) -> list[str] | None:
    """The stored live universe for `name`, if one has been refreshed; else None
    (callers fall back to the bundled preset)."""
    try:
        from backend.stores import get_stores
        raw = get_stores().bulk.get_state(_CURRENT_KEY)
    except Exception:  # noqa: BLE001 — no workspace yet, etc.
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if data.get("name") != name or not data.get("tickers"):
        return None
    return [str(t).upper() for t in data["tickers"]]
