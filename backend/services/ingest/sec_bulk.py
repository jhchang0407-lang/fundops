"""SEC bulk fundamentals ingestion (ADR-0059).

One companyfacts.zip download covers reported fundamentals for the whole
universe; the raw zip and the ticker→CIK map live in opconfig.cache_dir()
(rebuildable source material — never the workspace DB). Extraction lands
reported facts + periodized observations with lineage through the financial
store (ADR-0042/0043); restatements supersede via add_observation. Live
per-CIK top-ups are reserved for tickers the daily index shows just filed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import zipfile
from datetime import date
from pathlib import Path

from backend.core import opconfig

log = logging.getLogger("fundops.ingest.sec_bulk")

TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
COMPANYFACTS_API = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

CACHE_MAX_AGE_S = 7 * 86400  # bulk products refresh weekly (schedules.bulk_refresh)
ANNUAL_KEEP, QUARTERLY_KEEP = 5, 12  # retention targets (implementation map §2)

# XBRL tag → metric-catalog id. Several tags can feed one metric; the
# latest-filed value per (metric, period) wins via observation supersession.
GAAP_TAG_METRICS = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "NetIncomeLoss": "net_income",
    "GrossProfit": "gross_profit",
    "CostOfRevenue": "cost_of_revenue",
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "CostOfGoodsSold": "cost_of_revenue",
    "OperatingIncomeLoss": "operating_income",
    "IncomeTaxExpenseBenefit": "income_tax",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "pretax_income",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": "pretax_income",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    "EarningsPerShareDiluted": "eps",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": "operating_cash_flow",
    # capex: the base PP&E tag plus broad single-concept alternatives. NOT the
    # multi-line REIT real-estate components (PaymentsToAcquireRealEstate +
    # PaymentsForCapitalImprovements + …) — those must be SUMMED, and picking one
    # would understate capex and overstate derived FCF; full REIT capex/FFO is
    # deferred to the sector-aware pass.
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "PaymentsToAcquireProductiveAssets": "capex",
    "DepreciationDepletionAndAmortization": "depreciation_amortization",
    "DepreciationAmortizationAndAccretionNet": "depreciation_amortization",
    "ShareBasedCompensation": "sbc",
    "PaymentsOfDividendsCommonStock": "dividends_paid",
    "PaymentsOfDividends": "dividends_paid",
    "StockholdersEquity": "total_equity",
    "Assets": "total_assets",
    "LongTermDebt": "total_debt",
    "LongTermDebtNoncurrent": "total_debt",
    "LongTermDebtAndCapitalLeaseObligations": "total_debt",
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_outstanding",
}
DEI_TAG_METRICS = {"EntityCommonStockSharesOutstanding": "shares_outstanding"}

DEFAULT_TAX_RATE = 0.21  # US statutory; used when income-tax inputs aren't tagged

DERIVED_FORMULAS = {
    "free_cash_flow": "operating_cash_flow - capex",
    "gross_profit": "revenue - cost_of_revenue",
    "gross_margin": "gross_profit / revenue",
    "operating_margin": "operating_income / revenue",
    "net_margin": "net_income / revenue",
    "fcf_margin": "free_cash_flow / revenue",
    "debt_equity": "total_debt / total_equity",
    "roe": "net_income / total_equity",
    "roic": "operating_income * (1 - tax_rate) / (total_debt + total_equity)",
}
_DERIVED_INPUTS = {
    "free_cash_flow": ("operating_cash_flow", "capex"),
    "gross_profit": ("revenue", "cost_of_revenue"),
    "gross_margin": ("gross_profit", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
    "net_margin": ("net_income", "revenue"),
    "fcf_margin": ("free_cash_flow", "revenue"),
    "debt_equity": ("total_debt", "total_equity"),
    "roe": ("net_income", "total_equity"),
    "roic": ("operating_income", "total_equity"),
}


# --- network helpers (sync; run on worker threads, monkeypatched in tests) -------------

def _sec_headers() -> dict:
    cfg = opconfig.load()
    return {"User-Agent": cfg["providers"]["sec_user_agent"],
            "Accept-Encoding": "gzip, deflate"}


def _fetch_json(url: str, timeout: int) -> dict:
    import requests  # lazy: offline tests never import it

    resp = requests.get(url, headers=_sec_headers(), timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _stream_download(url: str, dest: Path, progress_cb=None) -> None:
    import requests  # lazy

    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=_sec_headers(), stream=True,
                      timeout=(30, 120)) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0) or None
        done = 0
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
    tmp.replace(dest)


def _fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_MAX_AGE_S


def _read_cached_json(path: Path) -> dict | None:
    """A partially-written or corrupt cache file must read as a miss, not
    poison every later attempt until the freshness window expires."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("discarding corrupt cache file %s: %s", path.name, exc)
        path.unlink(missing_ok=True)
        return None


# --- ticker → CIK map -------------------------------------------------------------------

async def sync_cik_map(stores, tickers: list[str]) -> dict[str, int]:
    """Resolve tickers to CIKs from the SEC company_tickers.json bulk file
    (cached a week); ensures entity identity (name + CIK) for matches."""
    path = opconfig.cache_dir() / "company_tickers.json"
    data = _read_cached_json(path) if _fresh(path) else None
    if data is None:
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(_fetch_json, TICKER_CIK_URL, 60), timeout=60)
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps(data))
            tmp.replace(path)  # atomic: a crash can't leave a half-written cache
        except Exception as exc:  # offline: stale cache beats nothing
            log.warning("company_tickers.json fetch failed: %s", exc)
            data = _read_cached_json(path)
    if not data:
        return {}
    by_ticker = {str(row.get("ticker") or "").upper(): row
                 for row in data.values() if isinstance(row, dict)}
    out: dict[str, int] = {}
    for t in (x.upper() for x in tickers):
        row = by_ticker.get(t)
        if not row or row.get("cik_str") in (None, ""):
            continue
        cik = int(row["cik_str"])
        stores.identity.ensure_entity(t, name=row.get("title"), cik=str(cik))
        out[t] = cik
    return out


# --- companyfacts bulk download + extraction ---------------------------------------------

async def download_companyfacts(progress_cb=None) -> Path:
    """Stream companyfacts.zip into the cache (chunked, progress bytes via
    callback); reuse a file younger than a week. A stale file beats an
    offline failure."""
    dest = opconfig.cache_dir() / "companyfacts.zip"
    if _fresh(dest) and zipfile.is_zipfile(dest):
        return dest
    try:
        await asyncio.to_thread(_stream_download, COMPANYFACTS_URL, dest, progress_cb)
    except Exception as exc:
        if dest.exists() and zipfile.is_zipfile(dest):
            log.warning("companyfacts download failed (%s); reusing stale file", exc)
            return dest
        raise
    if not zipfile.is_zipfile(dest):  # truncated body: don't let it stick for a week
        dest.unlink(missing_ok=True)
        raise RuntimeError("companyfacts.zip downloaded corrupt; retry will re-download")
    return dest


async def sync_companyfacts(stores, tickers: list[str], progress_cb=None) -> dict:
    """CIK map → local zip → extract_company_facts per universe member.
    Extraction is local computation; it runs on a worker thread so the
    server loop stays responsive across ~1,900 members."""
    cik_map = await sync_cik_map(stores, tickers)
    path = await download_companyfacts(progress_cb)

    def _extract_all() -> dict:
        matched = done = 0
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for t, cik in cik_map.items():
                done += 1
                member = f"CIK{cik:010d}.json"
                if member not in names:
                    continue
                ent = stores.identity.resolve_ticker(t)
                if not ent:
                    continue
                try:
                    extract_company_facts(stores, ent, json.loads(zf.read(member)))
                    matched += 1
                except Exception as exc:  # one bad member never sinks the run
                    log.warning("companyfacts extract failed for %s: %s", t, exc)
                if progress_cb and (done % 25 == 0 or done == len(cik_map)):
                    progress_cb(done, len(cik_map))
        return {"companies": matched, "universe": len(cik_map)}

    return await asyncio.to_thread(_extract_all)


def _period_type(entry: dict) -> str | None:
    """Annual = 10-K (fp FY), quarterly = 10-Q; duration-guarded so YTD
    spans in 10-Qs and quarterly comparatives in 10-Ks never mislabel."""
    form, fp = entry.get("form"), entry.get("fp")
    days = _duration_days(entry)
    if form in ("10-K", "10-K/A") and fp == "FY":
        return "annual" if days is None or days > 300 else None
    if form in ("10-Q", "10-Q/A"):
        return "quarterly" if days is None or days < 120 else None
    return None


def _duration_days(entry: dict) -> int | None:
    start, end = entry.get("start"), entry.get("end")
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(str(end)[:10]) - date.fromisoformat(str(start)[:10])).days
    except ValueError:
        return None


def extract_company_facts(stores, entity: dict, facts_json: dict) -> dict:
    """Map XBRL companyfacts to reported facts + observations for one company.

    Window: last 5 annual + 12 quarterly periods per metric. Every reported
    entry lands as a fact; observations dedupe per (metric, period) keeping
    the latest filed value, so a restatement arriving in a later extract or
    top-up supersedes through add_observation while an unchanged re-extract
    stays a no-op. Derived metrics carry formula + input lineage; the latest
    projection refreshes once at the end."""
    eid = entity["id"]
    groups = (facts_json or {}).get("facts") or {}
    selected: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for taxonomy, mapping in (("us-gaap", GAAP_TAG_METRICS), ("dei", DEI_TAG_METRICS)):
        tags = groups.get(taxonomy) or {}
        for tag, metric in mapping.items():
            for unit, entries in ((tags.get(tag) or {}).get("units") or {}).items():
                for e in entries or []:
                    ptype = _period_type(e)
                    if ptype is None or e.get("val") is None or not e.get("end"):
                        continue
                    end = str(e["end"])[:10]
                    selected.setdefault((metric, ptype), {}).setdefault(end, []).append(
                        {**e, "tag": tag, "taxonomy": taxonomy, "unit": unit})
    if not selected:
        return {"facts": 0, "observations": 0}

    ticker = stores.identity.current_ticker(eid) or entity.get("name") or ""
    src = stores.evidence.add_source(
        "filing", locator=COMPANYFACTS_URL, title=f"{ticker} SEC companyfacts",
        publisher="SEC EDGAR", retention_tier="identity",
    )
    live = {(r["metric"], r["period_type"], r["period_end"]): r["value"]
            for r in stores.financial.observations(eid, limit=100_000)}
    known_facts = {(r["concept"], r["period_type"], r["period_end"], r["accession"] or "")
                   for r in stores.ws.query(
                       "SELECT concept, period_type, period_end, accession "
                       "FROM reported_financial_facts WHERE entity_id = ?", (eid,))}

    n_facts = n_obs = 0
    finals: dict[tuple[str, str], dict[str, float]] = {}  # (ptype, end) -> {metric: value}
    for (metric, ptype), by_end in selected.items():
        keep = ANNUAL_KEEP if ptype == "annual" else QUARTERLY_KEEP
        for end in sorted(by_end, reverse=True)[:keep]:
            latest = None  # latest-filed valid entry wins the observation
            for e in sorted(by_end[end],
                            key=lambda x: (str(x.get("filed") or ""), str(x.get("accn") or ""))):
                try:
                    val = float(e["val"])
                except (TypeError, ValueError):
                    continue
                fkey = (e["tag"], ptype, end, str(e.get("accn") or ""))
                if fkey not in known_facts:
                    stores.financial.add_fact(
                        eid, e["tag"], end, ptype, val, unit=e.get("unit"),
                        taxonomy=e["taxonomy"], source_id=src, accession=e.get("accn"),
                        filed_at=e.get("filed"), mapped_concept=metric)
                    known_facts.add(fkey)
                    n_facts += 1
                latest = (e, val)
            if latest is None:
                continue
            e, val = latest
            okey = (metric, ptype, end)
            if live.get(okey) != val:
                stores.financial.add_observation(
                    eid, metric, end, ptype, val, unit=e.get("unit"),
                    is_calculated=False,
                    lineage={"source": "sec_companyfacts", "tag": e["tag"],
                             "accession": e.get("accn"), "filed": e.get("filed")},
                    refresh_latest=False)
                live[okey] = val
                n_obs += 1
            finals.setdefault((ptype, end), {})[metric] = val

    for (ptype, end), vals in finals.items():
        derived = _derive(vals)
        merged = {**vals, **derived}
        for m, v in derived.items():
            if live.get((m, ptype, end)) == v:
                continue
            stores.financial.add_observation(
                eid, m, end, ptype, v, is_calculated=True,
                lineage={"source": "sec_companyfacts", "formula": DERIVED_FORMULAS[m],
                         "inputs": {k: merged.get(k) for k in _DERIVED_INPUTS[m]}},
                refresh_latest=False)
            live[(m, ptype, end)] = v
            n_obs += 1
    stores.financial.refresh_latest(eid)
    return {"facts": n_facts, "observations": n_obs}


def _derive(vals: dict[str, float]) -> dict[str, float]:
    """Calculated observations per period — only when every input is present
    (missing data stays a data gap, never an invented zero)."""
    out: dict[str, float] = {}
    ocf, capex = vals.get("operating_cash_flow"), vals.get("capex")
    if ocf is not None and capex is not None:
        out["free_cash_flow"] = ocf - capex
    rev = vals.get("revenue")
    # Gross profit fallback: many filers tag CostOfRevenue but not GrossProfit.
    gross_profit = vals.get("gross_profit")
    if gross_profit is None and rev and vals.get("cost_of_revenue") is not None:
        gross_profit = rev - vals["cost_of_revenue"]
        out["gross_profit"] = gross_profit
    if rev:
        for m, num in (("gross_margin", gross_profit),
                       ("operating_margin", vals.get("operating_income")),
                       ("net_margin", vals.get("net_income")),
                       ("fcf_margin", out.get("free_cash_flow"))):
            if num is not None:
                out[m] = num / rev
    eq = vals.get("total_equity")
    if eq:
        if (debt := vals.get("total_debt")) is not None:
            out["debt_equity"] = debt / eq
        if (ni := vals.get("net_income")) is not None:
            out["roe"] = ni / eq
    # ROIC = NOPAT / invested capital. Invested capital = total debt + equity
    # (debt defaults to 0 when untagged); NOPAT uses the company's effective
    # tax rate when income-tax inputs exist, else the statutory default.
    oi = vals.get("operating_income")
    if oi is not None and eq:
        invested = eq + (vals.get("total_debt") or 0.0)
        if invested > 0:
            tax_rate = DEFAULT_TAX_RATE
            tax, pretax = vals.get("income_tax"), vals.get("pretax_income")
            if tax is not None and pretax and pretax > 0:
                tax_rate = min(max(tax / pretax, 0.0), 0.5)
            out["roic"] = oi * (1 - tax_rate) / invested
    return out


# --- targeted live top-up ----------------------------------------------------------------

async def topup_company(stores, ticker: str) -> dict | None:
    """Live per-CIK companyfacts fetch for a ticker the daily index shows
    just filed — the one sanctioned per-company call (ADR-0059). Degrades
    to None offline; the filing stays unprocessed for the next tick."""
    ent = stores.identity.resolve_ticker(ticker)
    if not ent or not str(ent.get("cik") or "").strip().isdigit():
        return None
    url = COMPANYFACTS_API.format(cik=int(ent["cik"]))
    try:
        facts = await asyncio.wait_for(
            asyncio.to_thread(_fetch_json, url, 30), timeout=30)
    except Exception as exc:
        log.warning("companyfacts top-up failed for %s: %s", ticker, exc)
        return None
    # Extraction is pure local computation but heavy enough to stall the
    # event loop when many tickers filed; keep it on a worker thread.
    return await asyncio.to_thread(extract_company_facts, stores, ent, facts)
