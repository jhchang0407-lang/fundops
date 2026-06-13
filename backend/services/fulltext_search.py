"""Thematic SEC full-text search via the keyless EDGAR EFTS endpoint.

"Who mentions X" across recent filings: one bounded request to
efts.sec.gov/LATEST/search-index, results mapped back to tickers (EFTS
display names carry them) and flagged when the company is in the active
universe. Read-only, on-demand — results are shown, not retained; a research
run on the surfaced companies is the retention path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request

from backend.core import opconfig

log = logging.getLogger("fundops.fulltext")

EFTS_URL = "https://efts.sec.gov/LATEST/search-index?q={query}{forms}"
FETCH_TIMEOUT_S = 20
MAX_HITS = 25
DEFAULT_FORMS = ("10-K", "10-Q", "8-K")
# EFTS display_names look like 'Axon Enterprise, Inc.  (AXON)  (CIK 0001069183)'
_TICKER_IN_NAME = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)")


def _fetch(query: str, forms: list[str] | None) -> dict:
    """Sync EFTS call (runs on a worker thread)."""
    quoted = urllib.parse.quote(f'"{query}"' if " " in query else query)
    forms_param = ""
    if forms:
        forms_param = "&forms=" + urllib.parse.quote(",".join(forms))
    url = EFTS_URL.format(query=quoted, forms=forms_param)
    req = urllib.request.Request(
        url, headers={"User-Agent": opconfig.load()["providers"]["sec_user_agent"]})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def parse_hits(payload: dict) -> list[dict]:
    """EFTS hits -> {company, ticker?, cik, form, filed, accession}."""
    out = []
    for h in ((payload.get("hits") or {}).get("hits") or [])[:MAX_HITS]:
        src = h.get("_source") or {}
        names = src.get("display_names") or []
        company = str(names[0]).split("(")[0].strip() if names else None
        ticker = None
        if names:
            m = _TICKER_IN_NAME.search(str(names[0]))
            if m and m.group(1) != "CIK":
                ticker = m.group(1)
        accession = str(h.get("_id") or "").split(":")[0] or None
        # EFTS uses a plural `ciks` list (one per co-filer); singular `cik`
        # appears in other EDGAR APIs but never here.
        ciks = src.get("ciks") or ([src["cik"]] if src.get("cik") else [])
        out.append({
            "company": company,
            "ticker": ticker,
            "cik": str(ciks[0]).lstrip("0") if ciks else None,
            "form": src.get("file_type") or src.get("root_form"),
            "filed": src.get("file_date"),
            "accession": accession,
        })
    return out


async def search_filings(stores, query: str, forms: list[str] | None = None) -> dict:
    """Run one thematic search; mark hits inside the active universe."""
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    forms = forms or list(DEFAULT_FORMS)
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_fetch, query, forms), timeout=FETCH_TIMEOUT_S + 5)
    except Exception as exc:
        log.warning("full-text search failed for %r: %s", query, exc)
        return {"query": query, "forms": forms, "hits": [], "ok": False,
                "note": "EDGAR full-text search unavailable (offline or rate-limited)."}
    hits = parse_hits(payload)
    universe = stores.constitution.active_universe()
    in_universe = set(universe["tickers"]) if universe else set()
    known = set(stores.identity.all_tickers())
    for h in hits:
        t = h.get("ticker")
        h["in_universe"] = bool(t and t in in_universe)
        h["known"] = bool(t and t in known)
    total = ((payload.get("hits") or {}).get("total") or {}).get("value")
    return {"query": query, "forms": forms, "hits": hits, "ok": True,
            "total": total,
            "note": ("Live EDGAR full-text results — shown, not retained. Run an "
                     "industry note on the surfaced companies to keep cited research.")}
