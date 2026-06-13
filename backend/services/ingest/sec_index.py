"""SEC daily form-index ingestion (ADR-0059).

The ~1-3MB daily form.idx files tell FundOps exactly who filed, which drives
targeted fundamentals top-ups and thesis-health recalculation for precisely
the affected tickers. Only rows for CIKs of known investment entities land
in the filings table (idempotent on accession); everything else is noise.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone

from backend.services.ingest.sec_bulk import _sec_headers

log = logging.getLogger("fundops.ingest.sec_index")

DAILY_INDEX_URL = ("https://www.sec.gov/Archives/edgar/daily-index/"
                   "{year}/QTR{q}/form.{yyyymmdd}.idx")
KEEP_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "3", "4", "5", "13F-HR",
    # 5%+ beneficial-ownership schedules — parsed into largest-holder records
    # by ingest.beneficial (structured XML since Dec 2024).
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
    # Registration statements: retained as dilution/M&A event records only;
    # they carry no ownership tables.
    "S-3", "S-3/A", "S-4", "S-4/A",
}
MAX_BACKFILL_DAYS = 30

_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")


def parse_form_index(text: str) -> list[dict]:
    """Rows of a daily form index, KEEP_FORMS only.

    Lines are 'Form Type / Company Name / CIK / Date Filed / File Name';
    header junk self-filters because real rows end in an edgar/data path
    with numeric CIK + date in the trailing columns."""
    rows: list[dict] = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 5 or "edgar/data/" not in tokens[-1]:
            continue
        file_name, date_tok, cik = tokens[-1], tokens[-2], tokens[-3]
        if not cik.isdigit():
            continue
        # Form types may span two tokens ("SC 13D", "SC 13G/A") — try the
        # longest match first so the company name doesn't absorb the schedule.
        two_token = " ".join(tokens[:2])
        if two_token in KEEP_FORMS:
            form, name_start = two_token, 2
        elif tokens[0] in KEEP_FORMS:
            form, name_start = tokens[0], 1
        else:
            continue
        if re.fullmatch(r"\d{8}", date_tok):
            filed_at = f"{date_tok[:4]}-{date_tok[4:6]}-{date_tok[6:8]}"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_tok):
            filed_at = date_tok
        else:
            continue
        accession = m.group(1) if (m := _ACCESSION_RE.search(file_name)) else None
        rows.append({"form": form, "company": " ".join(tokens[name_start:-3]), "cik": cik,
                     "filed_at": filed_at, "file_name": file_name,
                     "accession": accession})
    return rows


def _fetch_index_text(day: date) -> str | None:
    """One day's form index (sync; runs on a worker thread). 404 — weekends,
    holidays, not-yet-published — returns None. Monkeypatched in tests."""
    import requests  # lazy: offline tests never import it

    url = DAILY_INDEX_URL.format(year=day.year, q=(day.month - 1) // 3 + 1,
                                 yyyymmdd=day.strftime("%Y%m%d"))
    resp = requests.get(url, headers=_sec_headers(), timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def _known_ciks(stores) -> dict[int, dict]:
    rows = stores.ws.query(
        "SELECT e.id AS entity_id, e.cik, a.ticker FROM investment_entities e "
        "JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL "
        "WHERE e.cik IS NOT NULL")
    return {int(r["cik"]): {"ticker": r["ticker"], "entity_id": r["entity_id"]}
            for r in rows if str(r["cik"]).strip().isdigit()}


async def sync_daily_indexes(stores, since_date) -> dict:
    """Fetch each business day's form index since `since_date` (inclusive,
    capped at 30 days back), keep rows for known entities, record
    last_index_date. Missing days skip silently; fully offline runs simply
    add nothing."""
    since = since_date if isinstance(since_date, date) \
        else date.fromisoformat(str(since_date)[:10])
    today = datetime.now(timezone.utc).date()
    day = max(since, today - timedelta(days=MAX_BACKFILL_DAYS))
    cik_map = _known_ciks(stores)
    days_checked = added = 0
    first_failure: date | None = None
    while day <= today:
        if day.weekday() < 5:
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_index_text, day), timeout=45)
            except Exception as exc:  # offline / transient: retry next tick
                log.warning("daily index %s unavailable: %s", day, exc)
                text = None
                if first_failure is None:
                    first_failure = day
            if text:
                days_checked += 1
                for row in parse_form_index(text):
                    known = cik_map.get(int(row["cik"]))
                    if not known:
                        continue
                    fid = stores.bulk.add_filing(
                        row["form"], row["filed_at"], accession=row["accession"],
                        cik=row["cik"], ticker=known["ticker"],
                        entity_id=known["entity_id"], title=row["company"],
                        source="daily_index")
                    if fid:
                        added += 1
        day += timedelta(days=1)
    # Advance the watermark only through days that were actually checked — a
    # failed fetch must not permanently skip that day's filings (since is
    # inclusive, so the failed day is retried on the next tick).
    watermark = first_failure or today
    stores.bulk.set_state("last_index_date", watermark.isoformat())
    return {"days_checked": days_checked, "filings_added": added}
