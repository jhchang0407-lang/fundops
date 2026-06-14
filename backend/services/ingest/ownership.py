"""Insider-ownership ingestion from SEC quarterly Form 3/4/5 data sets
(ADR-0059).

Baseline scope is insider transactions only. Institutional 13F data sets are
DEFERRED: those files key holdings by CUSIP, and FundOps has no reliable
local CUSIP<->ticker mapping, so rows could not be attributed to investment
entities without guessing — weak evidence for a provenance-first product.

Quarterly zips (`{yyyy}q{q}_form345.zip`) land in the cache directory (raw
bulk material, ADR-0027/0049 — never the workspace DB); only rows for known
universe tickers become `ownership_records`. Headers vary across quarters,
so parsing reads candidate column names defensively.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from datetime import datetime, timezone

from backend.core import opconfig

log = logging.getLogger("fundops.ingest.ownership")

DATASET_URL = ("https://www.sec.gov/files/structureddata/data/"
               "insider-transactions-data-sets/{yyyy}q{q}_form345.zip")
DOWNLOAD_TIMEOUT_S = 120


# --- quarterly file parsing -----------------------------------------------------------

def _get(row: dict, *names: str) -> str | None:
    """First non-empty value among candidate column names (headers vary
    across dataset quarters)."""
    for name in names:
        v = row.get(name)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value  # unknown format: keep raw rather than drop the record


def _read_tsv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    try:
        raw = zf.read(name)
    except KeyError:
        return []
    text = io.StringIO(raw.decode("utf-8", errors="replace"))
    return list(csv.DictReader(text, delimiter="\t"))


def parse_form345_zip(path, wanted_tickers: set[str] | list[str]) -> list[dict]:
    """Join SUBMISSION / REPORTINGOWNER / NONDERIV_TRANS on ACCESSION_NUMBER;
    return insider-transaction records for the wanted tickers only."""
    wanted = {t.upper() for t in wanted_tickers}
    with zipfile.ZipFile(path) as zf:
        submissions = _read_tsv(zf, "SUBMISSION.tsv")
        owners = _read_tsv(zf, "REPORTINGOWNER.tsv")
        transactions = _read_tsv(zf, "NONDERIV_TRANS.tsv")
    by_accession: dict[str, dict] = {}
    for s in submissions:
        acc = _get(s, "ACCESSION_NUMBER", "ACCESSION_NO")
        ticker = (_get(s, "ISSUERTRADINGSYMBOL", "ISSUER_TRADING_SYMBOL") or "").upper()
        if acc and ticker in wanted:
            by_accession[acc] = {"ticker": ticker,
                                 "period": _get(s, "PERIOD_OF_REPORT")}
    owner_by_accession: dict[str, dict] = {}
    for o in owners:
        acc = _get(o, "ACCESSION_NUMBER", "ACCESSION_NO")
        if acc in by_accession and acc not in owner_by_accession:
            owner_by_accession[acc] = {
                "owner_name": _get(o, "RPTOWNERNAME", "RPTOWNER_NAME", "REPORTING_OWNER_NAME"),
                "owner_role": _get(o, "RPTOWNER_RELATIONSHIP", "OFFICER_TITLE",
                                   "RPTOWNER_TITLE", "RPTOWNER_OFFICER_TITLE"),
            }
    records: list[dict] = []
    for t in transactions:
        acc = _get(t, "ACCESSION_NUMBER", "ACCESSION_NO")
        sub = by_accession.get(acc)
        if not sub:
            continue
        owner = owner_by_accession.get(acc, {})
        shares = _float(_get(t, "TRANS_SHARES", "TRANSACTION_SHARES"))
        price = _float(_get(t, "TRANS_PRICEPERSHARE", "TRANS_PRICE_PER_SHARE",
                            "TRANSACTION_PRICEPERSHARE"))
        ad_code = (_get(t, "TRANS_ACQUIRED_DISP_CD", "TRANS_ACQUIRED_DISP_CODE",
                        "TRANSACTION_ACQUIRED_DISP_CD") or "").upper()
        records.append({
            "ticker": sub["ticker"],
            "as_of": _iso_date(_get(t, "TRANS_DATE", "TRANSACTION_DATE")) or sub.get("period"),
            "owner_name": owner.get("owner_name") or "Unknown reporting owner",
            "owner_role": owner.get("owner_role"),
            "shares": shares,
            "value": shares * price if shares is not None and price is not None else None,
            "txn_type": {"A": "buy", "D": "sell"}.get(ad_code),
            "payload": {
                "accession": acc,
                "trans_code": _get(t, "TRANS_CODE", "TRANSACTION_CODE"),
                "price_per_share": price,
                "acquired_disp_cd": ad_code or None,
                "period_of_report": sub.get("period"),
            },
        })
    return records


# --- quarterly sync --------------------------------------------------------------------

def _recent_quarters(count: int) -> list[tuple[int, int]]:
    today = datetime.now(timezone.utc).date()
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(count):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out


def _download_quarter(url: str, dest) -> None:
    """Fetch one quarterly zip into the cache (sync; runs on a worker
    thread). Module-level hook so tests monkeypatch it."""
    import requests  # lazy: offline tests never import it

    cfg = opconfig.load()
    resp = requests.get(url, timeout=90,
                        headers={"User-Agent": cfg["providers"]["sec_user_agent"]})
    resp.raise_for_status()
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)


def _already_recorded(stores, ticker: str, as_of: str | None, owner_name: str,
                      shares: float | None, txn_type: str | None) -> bool:
    """Naive dedupe: identical (ticker, as_of, owner_name, shares, txn_type)
    already stored. Local to ingestion — BulkStore stays append-simple."""
    return stores.ws.query_one(
        "SELECT 1 FROM ownership_records WHERE ticker = ? AND kind = 'insider_transaction' "
        "AND as_of IS ? AND owner_name = ? AND shares IS ? AND txn_type IS ?",
        (ticker.upper(), as_of, owner_name, shares, txn_type),
    ) is not None


async def sync_ownership(stores, tickers: list[str], quarters: int = 2) -> dict:
    """Ingest the latest N quarterly insider data sets for the given tickers.
    The current quarter's file may not be published yet, so one extra older
    quarter is tried as fallback. Cached zips are reused; download failures
    log and continue (offline-safe). Returns {quarters, records}."""
    wanted = {t.upper() for t in tickers}
    cache = opconfig.cache_dir() / "ownership"
    cache.mkdir(parents=True, exist_ok=True)
    inserted = 0
    done = 0
    for yyyy, q in _recent_quarters(quarters + 1):
        if done >= quarters:
            break
        url = DATASET_URL.format(yyyy=yyyy, q=q)
        dest = cache / f"{yyyy}q{q}_form345.zip"
        if dest.exists() and not zipfile.is_zipfile(dest):
            # A corrupt cached zip would otherwise block this quarter forever.
            log.warning("discarding corrupt insider data set cache %s", dest.name)
            dest.unlink(missing_ok=True)
        if not dest.exists():
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_download_quarter, url, dest),
                    timeout=DOWNLOAD_TIMEOUT_S,
                )
            except Exception as exc:  # not published yet / offline
                log.warning("insider data set %sq%s unavailable: %s", yyyy, q, exc)
                continue
        try:
            records = parse_form345_zip(dest, wanted)
        except Exception as exc:
            log.warning("insider data set %s unparseable: %s", dest.name, exc)
            continue
        source_id = stores.evidence.add_source(
            "provider", locator=url,
            title=f"SEC insider transactions data set {yyyy} Q{q}",
            publisher="SEC", retention_tier="identity",
        )
        for r in records:
            if not r["as_of"]:  # ownership_records.as_of is NOT NULL
                continue
            if _already_recorded(stores, r["ticker"], r["as_of"], r["owner_name"],
                                 r["shares"], r["txn_type"]):
                continue
            ent = stores.identity.resolve_ticker(r["ticker"])
            stores.bulk.add_ownership(
                r["ticker"], kind="insider_transaction", as_of=r["as_of"],
                owner_name=r["owner_name"], owner_role=r["owner_role"],
                shares=r["shares"], value=r["value"], txn_type=r["txn_type"],
                entity_id=ent["id"] if ent else None,
                payload=r["payload"], source_id=source_id,
            )
            inserted += 1
        done += 1
    return {"quarters": done, "records": inserted}
