"""Parse revenue segmentation (product + geographic) from XBRL filing instance."""

from __future__ import annotations

import re
import time

import httpx

from backend.core.sec.client import get_submissions, HEADERS


def _get_latest_filing_url(ticker: str, form_type: str = "10-K") -> str | None:
    """Get the XBRL instance document URL for the latest filing."""
    subs = get_submissions(ticker)

    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    cik = str(subs.get("cik", "")).lstrip("0")

    for i, form in enumerate(forms):
        if form == form_type:
            accn = accessions[i].replace("-", "")
            primary = primary_docs[i]
            # XBRL instance is usually {primary_without_ext}_htm.xml
            base_name = primary.rsplit(".", 1)[0]
            instance_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{base_name}_htm.xml"
            )
            return instance_url

    return None


def _parse_xbrl_instance(url: str) -> tuple[dict, list]:
    """Parse XBRL instance document and return (contexts, facts).

    Returns:
        contexts: dict mapping context_id -> {id, dimensions, end/instant, start}
        facts: list of (concept, context_id, value) tuples
    """
    time.sleep(0.15)  # rate limit
    r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
    r.raise_for_status()
    text = r.text

    # Parse contexts
    contexts = {}
    for match in re.finditer(
        r'<context[^>]*id="([^"]+)">(.*?)</context>', text, re.DOTALL
    ):
        cid = match.group(1)
        body = match.group(2)

        period_match = re.search(
            r"<startDate>([^<]+)</startDate>\s*<endDate>([^<]+)</endDate>", body
        )
        instant_match = re.search(r"<instant>([^<]+)</instant>", body)
        members = re.findall(
            r'<xbrldi:explicitMember[^>]*dimension="([^"]+)">([^<]+)</xbrldi:explicitMember>',
            body,
        )

        ctx = {"id": cid, "dimensions": dict(members)}
        if period_match:
            ctx["start"] = period_match.group(1)
            ctx["end"] = period_match.group(2)
        elif instant_match:
            ctx["instant"] = instant_match.group(1)

        contexts[cid] = ctx

    # Parse all numeric facts (us-gaap namespace)
    facts = []
    for match in re.finditer(
        r'<(?:us-gaap|[a-z]+):(\w+)[^>]*contextRef="([^"]+)"[^>]*>([^<]+)<',
        text,
    ):
        concept = match.group(1)
        ctx_id = match.group(2)
        value = match.group(3).strip()
        try:
            val = float(value)
            facts.append((concept, ctx_id, val))
        except (ValueError, TypeError):
            pass

    return contexts, facts


def _clean_segment_name(name: str) -> str:
    """Clean XBRL segment member name to human-readable."""
    # Remove namespace prefixes
    name = re.sub(r"^[a-z]+:", "", name)
    # Remove common suffixes
    name = name.replace("SegmentMember", "")
    name = name.replace("Member", "")
    # CamelCase to spaces (but keep consecutive capitals together like "IPad")
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    # Fix common product names
    name = name.replace("I Phone", "iPhone")
    name = name.replace("I Pad", "iPad")
    name = name.replace("I Mac", "iMac")
    name = name.replace("Homeand", "Home and")
    return name.strip()


def get_segments(ticker: str) -> dict:
    """Get revenue segmentation data (product + geographic) from SEC filings.

    Returns dict with product_segments and geographic_segments, each containing
    yearly breakdowns.
    """
    url = _get_latest_filing_url(ticker, "10-K")
    if url is None:
        return {"product_segments": {}, "geographic_segments": {}, "error": "No 10-K filing found"}

    try:
        contexts, facts = _parse_xbrl_instance(url)
    except Exception as e:
        return {"product_segments": {}, "geographic_segments": {}, "error": str(e)}

    # Revenue concept names to look for
    revenue_concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    }

    # Product/Service axis dimension
    product_axis = "srt:ProductOrServiceAxis"
    # Geographic axis dimension
    geo_axis = "srt:StatementGeographicalAxis"
    # Business segment axis
    biz_axis = "us-gaap:StatementBusinessSegmentsAxis"

    product_data: dict[str, dict[str, float]] = {}  # {year: {segment: value}}
    geo_data: dict[str, dict[str, float]] = {}

    for concept, ctx_id, value in facts:
        if concept not in revenue_concepts:
            continue

        ctx = contexts.get(ctx_id, {})
        dims = ctx.get("dimensions", {})
        end_date = ctx.get("end", "")
        year = end_date[:4] if end_date else ""
        if not year:
            continue

        # Product segments — skip aggregate categories (Product/Service)
        # to avoid double-counting with detailed breakdowns (iPhone/Mac/iPad)
        if product_axis in dims:
            raw_member = dims[product_axis]
            # Skip us-gaap aggregate members
            if raw_member.startswith("us-gaap:"):
                continue
            segment_name = _clean_segment_name(raw_member)
            if year not in product_data:
                product_data[year] = {}
            product_data[year][segment_name] = value

        # Geographic segments (from StatementGeographicalAxis)
        if geo_axis in dims and biz_axis not in dims:
            segment_name = _clean_segment_name(dims[geo_axis])
            if year not in geo_data:
                geo_data[year] = {}
            geo_data[year][segment_name] = value

        # Also capture business segments as geographic if no geo_axis data
        if biz_axis in dims and geo_axis not in dims and product_axis not in dims:
            segment_name = _clean_segment_name(dims[biz_axis])
            # Only use if we don't have geographic data yet
            if not geo_data.get(year):
                if year not in geo_data:
                    geo_data[year] = {}
                geo_data[year][segment_name] = value

    # Convert to sorted lists for output
    def _format_segments(data: dict) -> list[dict]:
        result = []
        for year in sorted(data.keys(), reverse=True):
            segments = data[year]
            total = sum(segments.values())
            entry = {"year": year, "total": total, "segments": {}}
            for seg_name, seg_val in sorted(segments.items(), key=lambda x: -x[1]):
                entry["segments"][seg_name] = {
                    "value": seg_val,
                    "percentage": round(seg_val / total * 100, 1) if total else 0,
                }
            result.append(entry)
        return result

    return {
        "product_segments": _format_segments(product_data),
        "geographic_segments": _format_segments(geo_data),
    }
