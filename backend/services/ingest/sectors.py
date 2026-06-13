"""Sector/industry identity backfill (Company Page peers + Markets tree).

The bulk products (companyfacts.zip, daily indexes) carry no industry
classification, so sector/industry come from each company's SEC submissions
JSON (`sic` + `sicDescription`), mapped to broad sectors via the SIC ranges
in core.sec.profile. Runs progressively from the scheduler tick — a bounded,
SEC-paced batch per pass — and is idempotent: an entity is only fetched while
its sector IS NULL (unclassifiable filers land as "Unknown", not NULL, so
they are never refetched).
"""

from __future__ import annotations

import asyncio
import logging

from backend.core.sec.profile import _sic_to_sector

log = logging.getLogger("fundops.ingest.sectors")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
PACING_S = 0.15  # SEC fair-use pacing between per-CIK calls
OFFLINE_BAIL_AFTER = 3  # consecutive failures with no successes → next tick


def _fetch_submissions(cik: str) -> dict:
    """One company's submissions metadata (sync; runs on a worker thread).
    Module-level hook so tests monkeypatch it."""
    from backend.services.ingest.sec_bulk import _fetch_json

    return _fetch_json(SUBMISSIONS_URL.format(cik=str(cik)), 30)


def pending_entities(stores, limit: int) -> list[dict]:
    rows = stores.ws.query(
        "SELECT e.id, e.cik, a.ticker FROM investment_entities e "
        "JOIN ticker_aliases a ON a.entity_id = e.id AND a.valid_to IS NULL "
        "WHERE e.cik IS NOT NULL AND e.sector IS NULL ORDER BY a.ticker LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


async def backfill_sectors(stores, limit: int = 150) -> dict:
    """Classify up to `limit` unclassified entities; returns counts."""
    done = failed = 0
    for row in pending_entities(stores, limit):
        try:
            subs = await asyncio.to_thread(_fetch_submissions, row["cik"])
        except Exception as exc:
            failed += 1
            log.warning("submissions fetch failed for %s: %s", row["ticker"], exc)
            if failed >= OFFLINE_BAIL_AFTER and done == 0:
                break  # likely offline — retry the whole batch next tick
            continue
        raw_sic = str(subs.get("sic") or "").strip()
        sector = _sic_to_sector(raw_sic or "")
        industry = (subs.get("sicDescription") or "").strip().title() or None
        # Zero-pad so prefix tiers can't collide (agriculture "0100" vs
        # metal mining "1040" share "10" unpadded).
        sic = raw_sic.zfill(4) if raw_sic.isdigit() else None
        stores.identity.ensure_entity(row["ticker"], sector=sector,
                                      industry=industry, sic=sic)
        done += 1
        await asyncio.sleep(PACING_S)
    return {"classified": done, "failed": failed}


def reclassify_from_stored_sic(stores) -> dict:
    """Re-derive sector from each entity's STORED sic — no network. Corrects
    entities classified under an older SIC->sector mapping (e.g. computer makers
    like Apple that landed under 'Industrial Machinery & Computers' before the
    tech-hardware override). Idempotent: writes only when the derived sector
    differs from the stored one."""
    rows = stores.ws.query(
        "SELECT id, sic, sector FROM investment_entities "
        "WHERE sic IS NOT NULL AND sic != ''"
    )
    changed = 0
    for r in rows:
        new_sector = _sic_to_sector(r["sic"])
        if new_sector and new_sector != "Unknown" and new_sector != r["sector"]:
            with stores.ws.transaction() as conn:
                conn.execute(
                    "UPDATE investment_entities SET sector = ? WHERE id = ?",
                    (new_sector, r["id"]),
                )
            changed += 1
    return {"reclassified": changed}
