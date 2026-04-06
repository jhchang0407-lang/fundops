"""SEC Filing Text Extraction.

Extracts key sections from 10-K and 10-Q filings using edgartools.
Returns structured text for feeding to research agents instead of web search.

Sections extracted from 10-K:
  - Item 1: Business
  - Item 1A: Risk Factors
  - Item 7: MD&A (Management's Discussion and Analysis)
  - Item 7A: Market Risk
  - Item 8: Financial Statements (footnotes)

Sections extracted from 10-Q:
  - Item 1: Financial Statements (footnotes)
  - Item 2: MD&A
  - Item 1A: Risk Factors (if updated)
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

import edgar

# Set identity for SEC API (required by fair use policy)
_USER_AGENT = os.getenv("SEC_USER_AGENT", "FundOps/1.0 research@fundops.dev")
edgar.set_identity(_USER_AGENT)

from edgar import Company


# Cache directory
CACHE_DIR = Path(os.getenv("FUNDOPS_CACHE_DIR", str(Path.home() / ".fundops" / "cache")))
FILINGS_CACHE = CACHE_DIR / "filings"


def _cache_path(ticker: str, form: str, accession: str) -> Path:
    """Generate cache file path for a filing."""
    safe_accession = accession.replace("-", "")
    return FILINGS_CACHE / f"{ticker}_{form}_{safe_accession}.json"


def _extract_section(markdown: str, start_item: str, end_items: list[str]) -> str:
    """Extract text between two Item headings in filing markdown."""
    start_pattern = re.compile(
        rf"^#+\s*{re.escape(start_item)}\s",
        re.MULTILINE | re.IGNORECASE,
    )

    start_match = start_pattern.search(markdown)
    if not start_match:
        return ""

    start_pos = start_match.end()

    end_pos = len(markdown)
    for end_item in end_items:
        end_pattern = re.compile(
            rf"^#+\s*{re.escape(end_item)}\s",
            re.MULTILINE | re.IGNORECASE,
        )
        end_match = end_pattern.search(markdown, start_pos)
        if end_match and end_match.start() < end_pos:
            end_pos = end_match.start()

    section_text = markdown[start_pos:end_pos].strip()
    section_text = re.sub(r"<[^>]+>", "", section_text)
    section_text = re.sub(r"\n{3,}", "\n\n", section_text)

    return section_text


def get_10k_sections(ticker: str, latest: bool = True) -> dict:
    """Extract key sections from the latest 10-K filing.

    Returns:
        Dictionary with keys: filing_date, period, accession_no,
        business, risk_factors, mda, market_risk, financial_statements_notes,
        full_text_length
    """
    ticker = ticker.upper()

    company = Company(ticker)
    filings = company.get_filings(form="10-K")

    if not filings or len(filings) == 0:
        return {"error": f"No 10-K filings found for {ticker}"}

    filing = filings[0] if latest else filings

    accession = filing.accession_no
    filing_date = str(filing.filing_date)

    cache_file = _cache_path(ticker, "10-K", accession)
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    md = filing.markdown()

    result = {
        "ticker": ticker,
        "form": "10-K",
        "filing_date": filing_date,
        "accession_no": accession,
        "period": str(getattr(filing, "report_date", filing_date)),
        "business": _extract_section(md, "Item 1.", ["Item 1A.", "Item 1B."]),
        "risk_factors": _extract_section(md, "Item 1A.", ["Item 1B.", "Item 1C.", "Item 2."]),
        "mda": _extract_section(md, "Item 7.", ["Item 7A.", "Item 8."]),
        "market_risk": _extract_section(md, "Item 7A.", ["Item 8."]),
        "financial_statements_notes": _extract_section(
            md, "Item 8.", ["Item 9.", "Item 9A."]
        )[:50000],
        "full_text_length": len(md),
    }

    FILINGS_CACHE.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(result, f)

    return result


def get_10q_sections(ticker: str, latest: bool = True) -> dict:
    """Extract key sections from the latest 10-Q filing.

    Returns:
        Dictionary with keys: filing_date, period, accession_no,
        mda, risk_factors, financial_statements_notes, full_text_length
    """
    ticker = ticker.upper()

    company = Company(ticker)
    filings = company.get_filings(form="10-Q")

    if not filings or len(filings) == 0:
        return {"error": f"No 10-Q filings found for {ticker}"}

    filing = filings[0] if latest else filings

    accession = filing.accession_no
    filing_date = str(filing.filing_date)

    cache_file = _cache_path(ticker, "10-Q", accession)
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    md = filing.markdown()

    mda_text = _extract_section(md, "Item 2.", ["Item 3.", "Item 4."])

    # If MD&A is too short, try finding "Management's Discussion"
    if len(mda_text) < 500:
        mda_pattern = re.compile(
            r"(?:Management.s Discussion and Analysis|MD&A)",
            re.IGNORECASE,
        )
        match = mda_pattern.search(md)
        if match:
            next_heading = re.search(r"^#+\s*Item\s+\d", md[match.end():], re.MULTILINE | re.IGNORECASE)
            end = match.end() + next_heading.start() if next_heading else match.end() + 50000
            mda_text = md[match.start():end].strip()
            mda_text = re.sub(r"<[^>]+>", "", mda_text)

    risk_text = _extract_section(md, "Item 1A.", ["Item 2.", "Item 3.", "Item 5.", "Item 6."])
    notes_text = _extract_section(md, "Item 1.", ["Item 2."])[:40000]

    result = {
        "ticker": ticker,
        "form": "10-Q",
        "filing_date": filing_date,
        "accession_no": accession,
        "period": str(getattr(filing, "report_date", filing_date)),
        "mda": mda_text,
        "risk_factors": risk_text,
        "financial_statements_notes": notes_text,
        "full_text_length": len(md),
    }

    FILINGS_CACHE.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(result, f)

    return result


def get_filing_text(ticker: str, form: str = "10-K", latest: bool = True) -> dict:
    """Unified interface to get filing text."""
    if form.upper() == "10-K":
        return get_10k_sections(ticker, latest=latest)
    elif form.upper() == "10-Q":
        return get_10q_sections(ticker, latest=latest)
    else:
        raise ValueError(f"Unsupported form type: {form}. Use '10-K' or '10-Q'.")


def build_agent_context(
    tenk: dict,
    tenq: Optional[dict] = None,
    max_chars: int = 120000,
) -> str:
    """Build a combined filing context string for research agents.

    Combines 10-K and 10-Q sections into a structured text block
    that can be injected into agent prompts.
    """
    parts = []

    if tenk and "error" not in tenk:
        parts.append(f"=== 10-K ANNUAL REPORT (Filed: {tenk.get('filing_date', 'N/A')}) ===\n")

        if tenk.get("business"):
            biz = tenk["business"][:30000]
            parts.append(f"--- BUSINESS DESCRIPTION (Item 1) ---\n{biz}\n")

        if tenk.get("mda"):
            mda = tenk["mda"][:35000]
            parts.append(f"--- MANAGEMENT DISCUSSION & ANALYSIS (Item 7) ---\n{mda}\n")

        if tenk.get("risk_factors"):
            rf = tenk["risk_factors"][:20000]
            parts.append(f"--- RISK FACTORS (Item 1A) ---\n{rf}\n")

    if tenq and "error" not in tenq:
        parts.append(f"\n=== 10-Q QUARTERLY REPORT (Filed: {tenq.get('filing_date', 'N/A')}) ===\n")

        if tenq.get("mda"):
            mda = tenq["mda"][:25000]
            parts.append(f"--- QUARTERLY MD&A (Item 2) ---\n{mda}\n")

        if tenq.get("risk_factors") and len(tenq["risk_factors"]) > 100:
            rf = tenq["risk_factors"][:10000]
            parts.append(f"--- UPDATED RISK FACTORS (Item 1A) ---\n{rf}\n")

    combined = "\n".join(parts)

    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[... truncated for context length ...]"

    return combined
