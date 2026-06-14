"""Filing full-text intake: fetch primary 10-K/10-Q documents from EDGAR,
extract the research-bearing sections (Business, Risk Factors, MD&A), and
cache them in filing_sections.

This is the on-demand research path (README: "live APIs are reserved for
on-demand research — full filing text for memos"). Reads check the cache
first, so a section is fetched from EDGAR at most once per filing; offline
runs serve whatever is cached and report gaps honestly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request

from backend.core import opconfig

log = logging.getLogger("fundops.ingest.filing_text")

FETCH_TIMEOUT_S = 30
SECTION_CHAR_CAP = 60_000
SECTIONS = ("business", "risk_factors", "mdna")
# Item boundaries. Start regexes match both 10-K and 10-Q numbering; end
# regexes include the 10-Q Part II successors (Item 2 "Unregistered Sales",
# Item 6 "Exhibits") so a 10-Q risk-factors section doesn't swallow the rest
# of the filing.
_SECTION_STARTS = {
    "business": re.compile(r"item\s*1\s*[\.\:\-—]\s*business", re.I),
    "risk_factors": re.compile(r"item\s*1a\s*[\.\:\-—]\s*risk\s*factors", re.I),
    "mdna": re.compile(
        r"item\s*[27]\s*[\.\:\-—]\s*management[’']?s?\s+discussion", re.I),
}
_SECTION_ENDS = {
    "business": re.compile(r"item\s*1a\s*[\.\:\-—]\s*risk\s*factors", re.I),
    "risk_factors": re.compile(
        r"item\s*1b\s*[\.\:\-—]|item\s*2\s*[\.\:\-—]\s*(propert|unregistered)"
        r"|item\s*6\s*[\.\:\-—]\s*exhibit", re.I),
    "mdna": re.compile(r"item\s*[38]\s*[\.\:\-—]|quantitative\s+and\s+qualitative\s+disclosures", re.I),
}


def _user_agent() -> str:
    return opconfig.load()["providers"]["sec_user_agent"]


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/tr|/li|/h[1-6])[^>]*>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#160;", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def extract_sections(html: str) -> dict[str, str]:
    """Best-effort Item extraction from a filing's flattened text. The last
    match of a start marker wins (early matches are usually the TOC)."""
    text = _strip_html(html)
    out: dict[str, str] = {}
    for name in SECTIONS:
        starts = list(_SECTION_STARTS[name].finditer(text))
        if not starts:
            continue
        start = starts[-1].start()
        end_match = _SECTION_ENDS[name].search(text, starts[-1].end())
        end = end_match.start() if end_match else min(len(text), start + SECTION_CHAR_CAP)
        section = text[start:end].strip()
        if len(section) > 500:  # ignore TOC-only fragments
            if len(section) > SECTION_CHAR_CAP:
                section = (section[:SECTION_CHAR_CAP]
                           + "\n\n[section truncated at cache limit]")
            out[name] = section
    return out


def _primary_document_url(cik: str, accession: str) -> str | None:
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}"
    try:
        index = json.loads(_fetch(f"{base}/index.json"))
    except Exception as exc:
        log.debug("filing index fetch failed %s: %s", accession, exc)
        return None
    # Exclude EDGAR XBRL viewer artifacts (R1.htm, R2.htm …) and exhibits —
    # but never legitimate documents that merely start with the letter r.
    viewer_re = re.compile(r"^r\d+\.html?$", re.I)
    candidates = [
        item["name"] for item in (index.get("directory") or {}).get("item", [])
        if str(item.get("name", "")).lower().endswith((".htm", ".html"))
        and not viewer_re.match(str(item.get("name", "")))
        and not str(item.get("name", "")).lower().startswith(("exhibit", "ex-", "ex_"))
    ]
    if not candidates:
        return None
    # Heuristic: the primary document is usually the largest top-level htm.
    primary = max(candidates, key=lambda n: next(
        (int(i.get("size") or 0) for i in index["directory"]["item"] if i["name"] == n), 0))
    return f"{base}/{primary}"


async def fetch_and_cache_sections(stores, filing: dict) -> dict[str, str]:
    """Sections for one filings-index row (needs cik + accession),
    cache-first. EDGAR I/O runs on a worker thread — never the event loop.
    When the row carries `primary_doc` (EDGAR submissions JSON), the document
    URL is built directly instead of probing the archive index."""
    accession = filing.get("accession")
    if not accession:
        return {}
    cached = {
        name: row["content"]
        for name in SECTIONS
        if (row := stores.context.filing_section(accession, name))
    }
    if cached:
        return cached
    cik = filing.get("cik")
    if not cik:
        return {}
    try:
        if filing.get("primary_doc"):
            acc_nodash = accession.replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{acc_nodash}/{filing['primary_doc']}")
        else:
            url = await asyncio.to_thread(_primary_document_url, cik, accession)
        if not url:
            return {}
        html = await asyncio.to_thread(_fetch, url)
    except Exception as exc:
        log.warning("filing fetch failed %s: %s", accession, exc)
        return {}
    sections = extract_sections(html)
    for name, content in sections.items():
        stores.context.upsert_filing_section(
            accession, name, content, ticker=filing.get("ticker"),
            form=filing.get("form"), filed_at=filing.get("filed_at"),
        )
    return sections


async def sections_for_ticker(stores, ticker: str, section: str, count: int = 2,
                              forms: tuple[str, ...] = ("10-K", "10-K/A"),
                              allow_fetch: bool = True) -> list[dict]:
    """The latest `count` filings' worth of one section for a ticker:
    [{accession, form, filed_at, content}], newest first. Cache-first; at
    most `count` EDGAR fetches (worker threads) when allow_fetch."""
    out: list[dict] = []
    seen: set[str] = set()
    for row in stores.context.filing_sections_for(ticker, section, limit=count):
        out.append({k: row[k] for k in ("accession", "form", "filed_at")}
                   | {"content": row["content"]})
        seen.add(row["accession"])
    if len(out) >= count or not allow_fetch:
        return out[:count]
    candidates = list(stores.bulk.filings_for(ticker, forms=list(forms), limit=8))
    if len(candidates) + len(out) < count:
        # The local filings index only holds entries since bootstrap; for any
        # known company the keyless EDGAR submissions list completes the set.
        ent = stores.identity.resolve_ticker(ticker)
        cik = (ent or {}).get("cik")
        if not cik:
            try:
                cik = await asyncio.to_thread(cik_for_ticker, ticker)
            except Exception as exc:
                log.warning("ticker→CIK mapping failed for %s: %s", ticker, exc)
        if cik:
            try:
                fetched = await asyncio.to_thread(
                    latest_filings_by_cik, cik, tuple(forms), count + 2)
                known = {c.get("accession") for c in candidates}
                candidates += [f for f in fetched if f["accession"] not in known]
            except Exception as exc:
                log.warning("submissions fallback failed for %s: %s", ticker, exc)
    for filing in candidates:
        if len(out) >= count:
            break
        if not filing.get("accession") or filing["accession"] in seen:
            continue
        sections = await fetch_and_cache_sections(stores, filing)
        if section in sections:
            out.append({"accession": filing["accession"], "form": filing["form"],
                        "filed_at": filing["filed_at"], "content": sections[section]})
            seen.add(filing["accession"])
    out.sort(key=lambda r: r["filed_at"] or "", reverse=True)
    return out[:count]


_TICKER_CIK_CACHE: dict[str, str] = {}


def cik_for_ticker(ticker: str) -> str | None:
    """Ticker → CIK via SEC's keyless registrant mapping (fetched once per
    process). Covers ANY US registrant — holdings and research targets outside
    the configured universe included."""
    global _TICKER_CIK_CACHE
    if not _TICKER_CIK_CACHE:
        data = json.loads(_fetch("https://www.sec.gov/files/company_tickers.json"))
        _TICKER_CIK_CACHE = {str(row["ticker"]).upper(): str(row["cik_str"])
                             for row in data.values()}
    return _TICKER_CIK_CACHE.get(ticker.upper())


def latest_filings_by_cik(cik: str, forms: tuple[str, ...] = ("10-K", "10-K/A"),
                          count: int = 1) -> list[dict]:
    """Latest filings for ANY CIK straight from EDGAR's keyless submissions
    JSON — no retained filings index needed. Lets research read companies
    outside the configured universe. Returns filings-index-shaped rows
    (cik, accession, form, filed_at, ticker, primary_doc), newest first."""
    padded = str(int(cik)).zfill(10)
    data = json.loads(_fetch(f"https://data.sec.gov/submissions/CIK{padded}.json"))
    recent = (data.get("filings") or {}).get("recent") or {}
    tickers = data.get("tickers") or []
    ticker = str(tickers[0]).upper() if tickers else None
    out = []
    for acc, form, date, doc in zip(recent.get("accessionNumber") or [],
                                    recent.get("form") or [],
                                    recent.get("filingDate") or [],
                                    recent.get("primaryDocument") or []):
        if form not in forms:
            continue
        out.append({"cik": str(int(cik)), "accession": acc, "form": form,
                    "filed_at": date, "ticker": ticker, "primary_doc": doc or None})
        if len(out) >= count:
            break
    return out


async def sections_for_cik(stores, cik: str, ticker: str | None, section: str,
                           count: int = 1) -> list[dict]:
    """Like sections_for_ticker, but resolved through EDGAR submissions by CIK
    — works for companies with no retained identity or filings index. Falls
    back from 10-K to the latest 10-Q when a company has no 10-K on file."""
    out: list[dict] = []
    for forms in (("10-K", "10-K/A"), ("10-Q",)):
        try:
            filings = await asyncio.to_thread(latest_filings_by_cik, cik, forms, count)
        except Exception as exc:
            log.warning("submissions lookup failed for CIK %s: %s", cik, exc)
            return out
        for filing in filings:
            filing.setdefault("ticker", ticker)
            sections = await fetch_and_cache_sections(stores, filing)
            if section in sections:
                out.append({"accession": filing["accession"], "form": filing["form"],
                            "filed_at": filing["filed_at"], "content": sections[section]})
        if out:
            break
    return out[:count]
