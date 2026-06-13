"""Beneficial ownership from Schedule 13D/13G filings (ADR-0059/0061).

13D/G filings name the 5%+ holders — the "largest owners" — and have been
filed as structured XML since December 2024. The daily index surfaces them for
known entities (the subject company's CIK row); this module fetches each
filing's primary XML, parses reporting persons tolerantly, and retains them as
ownership_records kind='beneficial_ownership'. Parsing is best-effort: a 13D/G
that cannot be parsed is still retained as a filings-index event.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET

from backend.core import opconfig

log = logging.getLogger("fundops.ingest.beneficial")

BENEFICIAL_FORMS = ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"]
FETCH_DELAY_S = 0.15

# Tolerant local-name matching across 13D/G XML schema variants.
_NAME_TAGS = {"reportingpersonname", "rptownername", "nameofreportingperson", "filingpersonname"}
_AMOUNT_TAGS = {"aggregateamountowned", "amountbeneficiallyowned",
                "aggregateamountbeneficiallyowned", "sharesbeneficiallyowned"}
_PCT_TAGS = {"percentofclass", "percentofclassrepresented", "classpercent"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _num(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[,%\s]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_schedule_xml(xml_text: str) -> list[dict]:
    """Extract reporting persons from a 13D/G primary XML document.

    Person blocks appear sequentially; a new name token starts a new record and
    subsequent amount/percent tokens attach to it. Returns
    [{owner_name, shares, percent}] — empty when nothing recognizable parses.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    records: list[dict] = []
    current: dict | None = None
    for el in root.iter():
        tag = _local(el.tag)
        text = (el.text or "").strip()
        if not text:
            continue
        if tag in _NAME_TAGS:
            current = {"owner_name": text, "shares": None, "percent": None}
            records.append(current)
        elif current is not None and tag in _AMOUNT_TAGS and current["shares"] is None:
            current["shares"] = _num(text)
        elif current is not None and tag in _PCT_TAGS and current["percent"] is None:
            current["percent"] = _num(text)
    return [r for r in records if r["owner_name"]]


def _filing_dir_url(cik: str, accession: str) -> str:
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}")


def _fetch_text(url: str, timeout: int = 30) -> str:
    import requests
    headers = {"User-Agent": opconfig.load()["providers"]["sec_user_agent"]}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _fetch_primary_xml(cik: str, accession: str) -> str | None:
    """Locate and fetch the filing's primary XML document via index.json."""
    base = _filing_dir_url(cik, accession)
    listing = json.loads(_fetch_text(f"{base}/index.json"))
    items = (listing.get("directory") or {}).get("item") or []
    xml_names = [i["name"] for i in items
                 if str(i.get("name", "")).lower().endswith(".xml")
                 and "xsl" not in str(i.get("name", "")).lower()]
    if not xml_names:
        return None
    # primary_doc.xml is the EDGAR convention; otherwise take the first XML.
    xml_names.sort(key=lambda n: (0 if "primary" in n.lower() else 1, n))
    return _fetch_text(f"{base}/{xml_names[0]}")


async def sync_beneficial(stores, limit: int = 50) -> dict:
    """Process unprocessed 13D/G filings into beneficial-ownership records.

    Live per-filing fetches are small and few (only universe tickers' 13D/G
    rows survive the index filter); offline failures leave the filing
    unprocessed for the next tick. Unparseable filings are marked processed —
    they remain retained as filings-index events.
    """
    parsed = 0
    skipped = 0
    done_ids: list[str] = []
    for f in stores.bulk.unprocessed_filings(forms=BENEFICIAL_FORMS, limit=limit):
        ticker, cik, accession = f.get("ticker"), f.get("cik"), f.get("accession")
        if not ticker or not cik or not accession:
            done_ids.append(f["id"])
            skipped += 1
            continue
        try:
            xml_text = await asyncio.wait_for(
                asyncio.to_thread(_fetch_primary_xml, cik, accession), timeout=45,
            )
        except Exception as exc:
            log.warning("13D/G fetch failed for %s %s: %s", ticker, accession, exc)
            continue  # stays unprocessed; retried next tick
        persons = parse_schedule_xml(xml_text) if xml_text else []
        if persons:
            src = stores.evidence.add_source(
                "filing", locator=_filing_dir_url(cik, accession),
                title=f"{ticker} {f['form']} {f['filed_at']}", publisher="SEC EDGAR",
            )
            ent = stores.identity.resolve_ticker(ticker)
            for p in persons:
                stores.bulk.add_ownership(
                    ticker, "beneficial_ownership", f["filed_at"], p["owner_name"],
                    shares=p.get("shares"), entity_id=ent["id"] if ent else None,
                    payload={"percent": p.get("percent"), "form": f["form"],
                             "accession": accession},
                    source_id=src,
                )
            parsed += 1
        else:
            skipped += 1
        done_ids.append(f["id"])
        await asyncio.sleep(FETCH_DELAY_S)
    stores.bulk.mark_filings_processed(done_ids)
    return {"parsed": parsed, "skipped": skipped}


def largest_holders(stores, ticker: str, top: int = 10) -> list[dict]:
    """Latest position per reporting person, largest first (percent, then shares)."""
    latest: dict[str, dict] = {}
    for r in stores.bulk.ownership_for(ticker, kind="beneficial_ownership", limit=500):
        key = r["owner_name"].strip().lower()
        if key not in latest:  # ownership_for is newest-first
            latest[key] = r
    rows = [
        {
            "owner_name": r["owner_name"],
            "as_of": r["as_of"],
            "shares": r.get("shares"),
            "percent": (r.get("payload") or {}).get("percent"),
            "form": (r.get("payload") or {}).get("form"),
        }
        for r in latest.values()
    ]
    rows.sort(key=lambda r: (-(r["percent"] or 0), -(r["shares"] or 0)))
    return rows[:top]
