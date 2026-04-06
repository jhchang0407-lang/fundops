"""Web Research Grounding Layer for FundOps.

Deterministic validation of web search results against known financial data.
No LLM calls — all validation uses regex, string matching, and arithmetic.

Pre-search:  build_fact_anchor() injects known SEC/FMP data into search prompts.
Post-search: ground_web_research() validates entity, recency, and numerical claims.

Usage:
    from backend.core.web_grounding import build_fact_anchor, ground_web_research

    anchor = build_fact_anchor(data, "PAYC", "Paycom Software")
    # ... inject anchor into search prompt, get results ...
    grounded = ground_web_research(result_text, data, "PAYC", "Paycom Software", anchor)
    if grounded.grounded:
        use(grounded.original_text)
    else:
        warn(grounded.warnings)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger("fundops.web_grounding")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class DateReference:
    """A date mention extracted from web research text."""
    text: str               # "Q3 2024 earnings call"
    parsed_date: date       # 2024-10-15
    age_days: int           # days from today
    context: str            # surrounding sentence


@dataclass
class NumericalClaim:
    """A numerical claim extracted from web research text."""
    raw_text: str           # "revenue grew 15%"
    value: float            # 15.0
    unit: str               # "percent" | "dollars" | "billions" | "millions" | "multiple" | "ratio"
    metric_hint: str        # "revenue_growth" — best-guess mapping to financial_data keys
    context: str            # surrounding sentence


@dataclass
class ClaimVerification:
    """Result of cross-referencing a claim against known financial data."""
    claim: NumericalClaim
    matched_metric: Optional[str]     # "revenue_growth" from financial_data
    actual_value: Optional[float]     # 8.2
    deviation_pct: Optional[float]    # 82.9% off
    status: str                       # "confirmed" | "contradicted" | "unmatched" | "stale"


@dataclass
class EntityCheck:
    """Result of verifying that web research is about the correct company."""
    ticker_found: bool
    company_name_found: bool
    confidence: float                 # 0.0-1.0
    wrong_entity_signals: list[str] = field(default_factory=list)


@dataclass
class GroundedResearch:
    """Fully grounded web research result with confidence and warnings."""
    original_text: str
    entity_check: EntityCheck
    date_references: list[DateReference]
    recency_score: float              # 0.0-1.0 (1.0 = all sources < 3 months old)
    claims: list[ClaimVerification]
    contradictions: list[str]         # human-readable warnings
    confidence: float                 # overall 0.0-1.0
    qualitative_confidence: float = 0.5  # confidence in qualitative claims (0.0-1.0)
    warnings: list[str] = field(default_factory=list)  # issues to surface to agent/user
    grounded: bool = False            # passes minimum thresholds
    fact_anchor_used: str = ""        # the anchor block that was injected


# ---------------------------------------------------------------------------
# Metric hint mapping — keyword proximity → financial_data key
# ---------------------------------------------------------------------------

METRIC_HINT_MAP: dict[str, list[str]] = {
    # Keywords (lowercase) near a number → candidate metric_hint values
    "revenue growth": ["revenue_growth"],
    "revenue grew": ["revenue_growth"],
    "sales growth": ["revenue_growth"],
    "top-line growth": ["revenue_growth"],
    "topline growth": ["revenue_growth"],
    "yoy growth": ["revenue_growth"],
    "year-over-year growth": ["revenue_growth"],
    "gross margin": ["gross_margin"],
    "gross profit margin": ["gross_margin"],
    "operating margin": ["operating_margin"],
    "op margin": ["operating_margin"],
    "ebitda margin": ["ebitda_margin"],
    "net margin": ["net_margin"],
    "profit margin": ["net_margin"],
    "net profit margin": ["net_margin"],
    "roic": ["roic"],
    "return on invested capital": ["roic"],
    "roe": ["roe"],
    "return on equity": ["roe"],
    "roa": ["roa"],
    "return on assets": ["roa"],
    "debt-to-equity": ["debt_equity"],
    "debt to equity": ["debt_equity"],
    "d/e": ["debt_equity"],
    "leverage ratio": ["debt_equity"],
    "fcf yield": ["fcf_yield"],
    "free cash flow yield": ["fcf_yield"],
    "dividend yield": ["dividend_yield"],
    "div yield": ["dividend_yield"],
    "pe ratio": ["pe"],
    "p/e ratio": ["pe"],
    "p/e": ["pe"],
    "price-to-earnings": ["pe"],
    "price to earnings": ["pe"],
    "earnings multiple": ["pe"],
    "earnings": ["pe"],
    "ev/ebitda": ["ev_ebitda"],
    "enterprise value": ["market_cap"],
    "price-to-sales": ["ps"],
    "p/s": ["ps"],
    "revenue": ["revenue"],
    "sales": ["revenue"],
    "market cap": ["market_cap"],
    "marketcap": ["market_cap"],
    "market capitalization": ["market_cap"],
    "eps": ["eps"],
    "earnings per share": ["eps"],
}

# Maps metric_hint → possible keys in financial_data dict
METRIC_DATA_MAP: dict[str, list[str]] = {
    "revenue_growth": ["revenue_growth", "revenueGrowth", "revenueGrowthTTM"],
    "gross_margin": ["gross_margin", "grossProfitMargin", "grossProfitMarginTTM"],
    "operating_margin": ["operating_margin", "operatingProfitMargin", "operatingProfitMarginTTM"],
    "ebitda_margin": ["ebitda_margin", "ebitdaMargin"],
    "net_margin": ["net_margin", "netProfitMargin", "netProfitMarginTTM"],
    "roic": ["roic", "returnOnInvestedCapital", "roicTTM", "returnOnInvestedCapitalTTM"],
    "roe": ["roe", "returnOnEquity", "roeTTM", "returnOnEquityTTM"],
    "roa": ["roa", "returnOnAssets", "roaTTM"],
    "debt_equity": ["debt_equity", "debtToEquity", "debtToEquityTTM"],
    "fcf_yield": ["fcf_yield", "freeCashFlowYield", "freeCashFlowYieldTTM"],
    "dividend_yield": ["dividend_yield", "dividendYield", "dividendYieldTTM"],
    "pe": ["pe", "priceEarningsRatio", "peRatio", "peRatioTTM"],
    "ev_ebitda": ["ev_ebitda", "evToEbitda", "enterpriseValueOverEBITDA"],
    "ps": ["ps", "priceToSalesRatio", "priceToSalesRatioTTM"],
    "revenue": ["revenue"],
    "market_cap": ["market_cap", "marketCap", "mktCap"],
    "eps": ["eps", "epsDiluted"],
}


# ---------------------------------------------------------------------------
# Pre-Search: Fact Anchor
# ---------------------------------------------------------------------------

def build_fact_anchor(financial_data: dict, ticker: str, company_name: str) -> str:
    """Build a deterministic fact block from known SEC/FMP data.

    Injected into web search prompts so the AI reconciles web findings
    against verified numbers. Handles missing fields gracefully — omits
    any line where the value is None, 0, or missing.

    Args:
        financial_data: Dict with keys like revenue, revenue_growth, gross_margin, etc.
        ticker: Stock ticker symbol.
        company_name: Full company name.

    Returns:
        Multi-line text block with verified financials and instructions.
    """
    lines = [f"VERIFIED FINANCIALS (SEC/FMP filings):"]
    lines.append(f"- Company: {company_name} ({ticker})")

    # Helper: add a line only if the value is present and non-zero
    def _add(label: str, keys: list[str], fmt: str = "raw",
             multiplier: float = 1.0, suffix: str = "") -> None:
        for key in keys:
            val = financial_data.get(key)
            if val is not None and val != 0 and val != "":
                if fmt == "pct":
                    # Convert decimal to percentage if value < 1
                    display_val = float(val) * 100 if abs(float(val)) < 1 else float(val)
                    lines.append(f"- {label}: {display_val:.1f}%{suffix}")
                elif fmt == "dollars_b":
                    display_val = float(val) / 1e9 if float(val) > 1e6 else float(val)
                    lines.append(f"- {label}: ${display_val:.2f}B{suffix}")
                elif fmt == "dollars":
                    lines.append(f"- {label}: ${float(val):.2f}{suffix}")
                elif fmt == "ratio":
                    lines.append(f"- {label}: {float(val):.2f}{suffix}")
                else:
                    lines.append(f"- {label}: {val}{suffix}")
                return

    _add("Revenue", ["revenue"], fmt="dollars_b")
    _add("Revenue growth (YoY)", ["revenue_growth", "revenueGrowth", "revenueGrowthTTM"], fmt="pct")
    _add("Gross margin", ["gross_margin", "grossProfitMargin", "grossProfitMarginTTM"], fmt="pct")
    _add("ROIC", ["roic", "roicTTM", "returnOnInvestedCapitalTTM"], fmt="pct")
    _add("D/E", ["debt_equity", "debtToEquity", "debtToEquityTTM"], fmt="ratio")
    _add("FCF yield", ["fcf_yield", "freeCashFlowYieldTTM"], fmt="pct")
    _add("Price", ["price"], fmt="dollars")
    _add("Market cap", ["market_cap", "marketCap", "mktCap"], fmt="dollars_b")

    lines.append("")
    lines.append(
        "CONTEXT: The numbers above are from audited SEC filings and serve as anchoring data. "
        "Write in third-person analytical tone as a research analyst. "
        "Do NOT address the reader as 'you' or reference 'the numbers you supplied'. "
        "Do NOT offer to do further analysis ('If you want, I can...'). "
        "Focus on qualitative context, catalysts, and risks beyond the filing data. "
        "Cite sources with inline markdown links."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-Processing: Clean web research prose for display
# ---------------------------------------------------------------------------

# Patterns that indicate conversational LLM chatter (not analytical prose)
_CHATTER_PATTERNS = [
    re.compile(r"^(?:Quick note on|Important note about|A note on) (?:the )?(?:verified |numbers |data ).*$", re.MULTILINE),
    re.compile(r"^-?\s*You told me.*$", re.MULTILINE),
    re.compile(r"^-?\s*I will treat (?:those|these|them).*$", re.MULTILINE),
    re.compile(r"^-?\s*I (?:won't|will not) repeat.*$", re.MULTILINE),
    re.compile(r"^(?:If you want,? I can|Which would you prefer|Would you like me to|Let me know if).*$", re.MULTILINE),
    re.compile(r"^-?\s*(?:Produce|Run|Build|Create) a (?:12|24|short|scenario).*(?:model|watchlist|table).*$", re.MULTILINE),
    re.compile(r"^(?:If you want|Want me to|I can also|Below I focus|Here's what).*?:?\s*$", re.MULTILINE),
]

# Sections that are meta-conversation, not analysis
_CHATTER_SECTIONS = [
    re.compile(r"^(?:Quick note|Important note|If you want next|References \(selected\)).*", re.MULTILINE | re.IGNORECASE),
]


def clean_web_research(text: str) -> str:
    """Clean conversational artifacts from web research text.

    Removes:
    - "You told me..." / "I will treat those as verified..." lines
    - "If you want, I can..." offers
    - Meta-conversation sections (notes about verified numbers, offers to do more)

    Preserves all analytical content, citations, and source links.
    """
    if not text or not isinstance(text, str):
        return text or ""

    lines = text.split("\n")
    cleaned: list[str] = []
    skip_section = False

    for line in lines:
        stripped = line.strip()

        # Check if this starts a chatter section
        if any(p.match(stripped) for p in _CHATTER_SECTIONS):
            skip_section = True
            continue

        # End chatter section on a new substantive heading
        if skip_section and stripped and not stripped.startswith("-") and not stripped.startswith("•"):
            # Check if this looks like a real section header
            if len(stripped) > 10 and not any(p.match(stripped) for p in _CHATTER_PATTERNS):
                skip_section = False

        if skip_section:
            continue

        # Check individual chatter lines
        if any(p.match(stripped) for p in _CHATTER_PATTERNS):
            continue

        cleaned.append(line)

    # Remove excessive blank lines
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Post-Search: Entity Verification
# ---------------------------------------------------------------------------

def verify_entity(text: str, ticker: str, company_name: str) -> EntityCheck:
    """Check if the web research text is about the correct company.

    Args:
        text: Raw web research text.
        ticker: Expected ticker symbol (e.g., "PAYC").
        company_name: Expected company name (e.g., "Paycom Software").

    Returns:
        EntityCheck with confidence score and any wrong-entity signals.
    """
    if not text or not text.strip():
        return EntityCheck(
            ticker_found=False,
            company_name_found=False,
            confidence=0.0,
            wrong_entity_signals=["Empty text"],
        )

    text_upper = text.upper()
    text_lower = text.lower()

    # Check ticker presence — require word boundary to avoid false positives
    ticker_upper = ticker.upper()
    ticker_pattern = re.compile(r'\b' + re.escape(ticker_upper) + r'\b')
    ticker_found = bool(ticker_pattern.search(text_upper))

    # Check company name presence — case-insensitive substring match
    # Use first significant word(s) of company name for fuzzy match
    company_lower = company_name.lower().strip()
    # Try full name first, then first word (for "Paycom Software" match "Paycom")
    company_name_found = company_lower in text_lower
    if not company_name_found and " " in company_lower:
        first_word = company_lower.split()[0]
        if len(first_word) >= 3:  # avoid matching tiny words
            company_name_found = first_word in text_lower

    # Detect wrong entity signals
    wrong_signals = []

    # Common confusion pairs — check if text mentions other companies more than ours
    # We detect this by looking for other ticker-like patterns in parentheses
    other_tickers = re.findall(r'\(([A-Z]{2,5})\)', text)
    for ot in set(other_tickers):
        if ot != ticker_upper and len(ot) >= 2:
            ot_count = text_upper.count(ot)
            our_count = text_upper.count(ticker_upper) if ticker_found else 0
            if ot_count > our_count and ot_count >= 3:
                wrong_signals.append(
                    f"Mentions '{ot}' ({ot_count} times) more than '{ticker_upper}' ({our_count} times)"
                )

    # Compute confidence
    if wrong_signals:
        confidence = 0.0
    elif ticker_found and company_name_found:
        confidence = 1.0
    elif ticker_found or company_name_found:
        confidence = 0.7
    else:
        confidence = 0.3

    return EntityCheck(
        ticker_found=ticker_found,
        company_name_found=company_name_found,
        confidence=confidence,
        wrong_entity_signals=wrong_signals,
    )


# ---------------------------------------------------------------------------
# Post-Search: Recency Check
# ---------------------------------------------------------------------------

# Date used for age calculations — can be overridden for testing
_TODAY: date | None = None


def _get_today() -> date:
    """Get today's date. Uses _TODAY override if set (for testing)."""
    return _TODAY if _TODAY is not None else date.today()


def _quarter_to_date(quarter: int, year: int) -> date:
    """Convert a fiscal quarter to approximate mid-quarter date."""
    month_map = {1: 2, 2: 5, 3: 8, 4: 11}
    return date(year, month_map.get(quarter, 6), 15)


def _month_name_to_num(name: str) -> int | None:
    """Convert month name to number."""
    months = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    return months.get(name.lower())


def _date_age_to_score(age_days: int) -> float:
    """Convert age in days to a recency score."""
    if age_days < 0:
        # Future date — treat as very recent
        return 1.0
    if age_days <= 90:
        return 1.0
    if age_days <= 180:
        return 0.7
    if age_days <= 365:
        return 0.4
    return 0.1


def _get_context(text: str, match_start: int, match_end: int, window: int = 80) -> str:
    """Extract surrounding context for a regex match."""
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    ctx = text[start:end].strip()
    # Trim to sentence boundaries if possible
    if start > 0:
        first_space = ctx.find(" ")
        if first_space > 0:
            ctx = "..." + ctx[first_space:]
    if end < len(text):
        last_space = ctx.rfind(" ")
        if last_space > 0:
            ctx = ctx[:last_space] + "..."
    return ctx


def check_recency(text: str) -> tuple[list[DateReference], float]:
    """Extract date references from text and compute a recency score.

    Regex patterns recognized:
    - "Q3 2024", "Q1 2025"
    - "March 2025", "Jan 2024"
    - "FY2025", "FY 2024"
    - "2024", "2025" (standalone 4-digit years)
    - "last quarter", "last year", "this year"

    Returns:
        Tuple of (list of DateReference, recency_score 0.0-1.0).
        Score is 0.5 (neutral) if no dates found.
    """
    if not text or not text.strip():
        return ([], 0.5)

    today = _get_today()
    refs: list[DateReference] = []
    seen_dates: set[str] = set()  # avoid duplicates

    # Pattern 1: Q[1-4] 20XX
    for m in re.finditer(r'\bQ([1-4])\s*[\'\-]?\s*(20\d{2})\b', text, re.IGNORECASE):
        quarter = int(m.group(1))
        year = int(m.group(2))
        d = _quarter_to_date(quarter, year)
        key = f"Q{quarter}-{year}"
        if key not in seen_dates:
            seen_dates.add(key)
            age = (today - d).days
            refs.append(DateReference(
                text=m.group(0),
                parsed_date=d,
                age_days=age,
                context=_get_context(text, m.start(), m.end()),
            ))

    # Pattern 2: Month Year (e.g., "March 2025", "Jan 2024")
    month_pattern = (
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December'
        r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(20\d{2})\b'
    )
    for m in re.finditer(month_pattern, text, re.IGNORECASE):
        month_num = _month_name_to_num(m.group(1))
        year = int(m.group(2))
        if month_num:
            d = date(year, month_num, 15)
            key = f"{month_num}-{year}"
            if key not in seen_dates:
                seen_dates.add(key)
                age = (today - d).days
                refs.append(DateReference(
                    text=m.group(0),
                    parsed_date=d,
                    age_days=age,
                    context=_get_context(text, m.start(), m.end()),
                ))

    # Pattern 3: FY20XX or FY 20XX
    for m in re.finditer(r'\bFY\s*[\'\-]?\s*(20\d{2})\b', text, re.IGNORECASE):
        year = int(m.group(1))
        d = date(year, 6, 30)  # mid fiscal year
        key = f"FY-{year}"
        if key not in seen_dates:
            seen_dates.add(key)
            age = (today - d).days
            refs.append(DateReference(
                text=m.group(0),
                parsed_date=d,
                age_days=age,
                context=_get_context(text, m.start(), m.end()),
            ))

    # Pattern 4: Standalone year (20XX) — lower priority, only if not already captured
    for m in re.finditer(r'\b(20[1-3]\d)\b', text):
        year = int(m.group(1))
        key = f"year-{year}"
        if key not in seen_dates:
            seen_dates.add(key)
            d = date(year, 7, 1)  # mid year
            age = (today - d).days
            refs.append(DateReference(
                text=m.group(0),
                parsed_date=d,
                age_days=age,
                context=_get_context(text, m.start(), m.end()),
            ))

    # Pattern 5: Relative dates
    relative_patterns = [
        (r'\blast\s+quarter\b', timedelta(days=90)),
        (r'\bthis\s+quarter\b', timedelta(days=0)),
        (r'\blast\s+year\b', timedelta(days=365)),
        (r'\bthis\s+year\b', timedelta(days=0)),
        (r'\blast\s+month\b', timedelta(days=30)),
        (r'\brecently\b', timedelta(days=30)),
        (r'\bearlier\s+this\s+year\b', timedelta(days=90)),
    ]
    for pattern, delta in relative_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            d = today - delta
            key = f"rel-{pattern}"
            if key not in seen_dates:
                seen_dates.add(key)
                age = (today - d).days
                refs.append(DateReference(
                    text=m.group(0),
                    parsed_date=d,
                    age_days=age,
                    context=_get_context(text, m.start(), m.end()),
                ))

    # Compute recency score
    if not refs:
        return ([], 0.5)

    scores = [_date_age_to_score(r.age_days) for r in refs]
    # Weighted: more recent dates matter more
    recency = sum(scores) / len(scores)

    return (refs, round(recency, 3))


# ---------------------------------------------------------------------------
# Post-Search: Numerical Claim Extraction
# ---------------------------------------------------------------------------

def _infer_metric_hint(context: str) -> str:
    """Infer a metric hint from surrounding context using keyword proximity."""
    ctx_lower = context.lower()
    best_hint = ""
    best_pos = len(ctx_lower) + 1

    for keyword, hints in METRIC_HINT_MAP.items():
        pos = ctx_lower.find(keyword)
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_hint = hints[0]

    return best_hint


def extract_numerical_claims(text: str) -> list[NumericalClaim]:
    """Extract numerical claims from web research text.

    Recognizes patterns like:
    - "15%", "grew 15%", "margin of 45%"
    - "$1.8 billion", "$500 million", "$45.2B"
    - "12x earnings", "trading at 15x"
    - "45% margin"

    Returns:
        List of NumericalClaim with value, unit, and metric hint.
    """
    if not text or not text.strip():
        return []

    claims: list[NumericalClaim] = []
    seen: set[str] = set()

    # Pattern 1: Percentage patterns — "15%", "grew 15%", "15 percent"
    for m in re.finditer(
        r'(\d[\d,.]*)\s*(%|percent)',
        text, re.IGNORECASE,
    ):
        raw = m.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        context = _get_context(text, m.start(), m.end())
        hint = _infer_metric_hint(context)
        claims.append(NumericalClaim(
            raw_text=raw,
            value=value,
            unit="percent",
            metric_hint=hint,
            context=context,
        ))

    # Pattern 2: Dollar amounts — "$1.8 billion", "$500 million", "$1.8B", "$500M"
    for m in re.finditer(
        r'\$\s*(\d[\d,.]*)\s*(billion|billion|million|trillion|[BMTbmt])\b',
        text, re.IGNORECASE,
    ):
        raw = m.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit_raw = m.group(2).lower()
        if unit_raw in ("b", "billion"):
            unit = "billions"
        elif unit_raw in ("m", "million"):
            unit = "millions"
        elif unit_raw in ("t", "trillion"):
            unit = "trillions"
        else:
            unit = "dollars"
        context = _get_context(text, m.start(), m.end())
        hint = _infer_metric_hint(context)
        claims.append(NumericalClaim(
            raw_text=raw,
            value=value,
            unit=unit,
            metric_hint=hint,
            context=context,
        ))

    # Pattern 3: Multiples — "12x earnings", "trading at 15x", "10x revenue"
    for m in re.finditer(
        r'(\d[\d,.]*)\s*[xX]\s*(\w*)',
        text,
    ):
        raw = m.group(0).strip()
        if raw in seen:
            continue
        seen.add(raw)
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        context = _get_context(text, m.start(), m.end())
        hint = _infer_metric_hint(context)
        # Default multiple hint to P/E if near "earnings"
        if not hint and m.group(2).lower() in ("earnings", "earning", "eps", "e"):
            hint = "pe"
        elif not hint and m.group(2).lower() in ("revenue", "sales", "rev"):
            hint = "ps"
        claims.append(NumericalClaim(
            raw_text=raw,
            value=value,
            unit="multiple",
            metric_hint=hint,
            context=context,
        ))

    return claims


# ---------------------------------------------------------------------------
# Post-Search: Cross-Reference Claims
# ---------------------------------------------------------------------------

def _normalize_value(claim_value: float, claim_unit: str, actual_value: float) -> tuple[float, float]:
    """Normalize claim and actual values to the same scale for comparison.

    Handles percent (15 vs 0.15), billions ($1.8B vs 1800000000), etc.

    Returns:
        (normalized_claim, normalized_actual) on comparable scales.
    """
    c = claim_value
    a = actual_value

    if claim_unit == "percent":
        # Claim is "15%" (value=15.0). Actual might be 0.15 or 15.0.
        if abs(a) < 1.0 and abs(c) >= 1.0:
            # Actual is decimal (0.15), claim is percentage (15)
            a = a * 100.0
        elif abs(a) >= 1.0 and abs(c) < 1.0:
            # Unlikely but handle: claim is decimal, actual is percentage
            c = c * 100.0

    elif claim_unit == "billions":
        # Claim is "$1.8B" (value=1.8). Actual might be 1800000000 or 1.8.
        if abs(a) > 1e6 and abs(c) < 1e3:
            a = a / 1e9

    elif claim_unit == "millions":
        if abs(a) > 1e6 and abs(c) < 1e6:
            a = a / 1e6

    elif claim_unit == "multiple":
        # Both should be raw numbers (12x vs 12.5)
        pass

    elif claim_unit == "ratio":
        pass

    return (c, a)


def cross_reference_claims(
    claims: list[NumericalClaim],
    financial_data: dict,
) -> list[ClaimVerification]:
    """Match extracted claims against known financial data.

    For each claim with a metric_hint, look up the actual value in
    financial_data and compare. Tolerance: +/-10% relative deviation
    for "confirmed", >10% for "contradicted".

    Args:
        claims: Extracted numerical claims from web research.
        financial_data: Dict with keys like revenue_growth, gross_margin, etc.

    Returns:
        List of ClaimVerification results.
    """
    verified: list[ClaimVerification] = []

    for claim in claims:
        if not claim.metric_hint:
            verified.append(ClaimVerification(
                claim=claim,
                matched_metric=None,
                actual_value=None,
                deviation_pct=None,
                status="unmatched",
            ))
            continue

        # Look up actual value using METRIC_DATA_MAP
        data_keys = METRIC_DATA_MAP.get(claim.metric_hint, [claim.metric_hint])
        actual = None
        matched_key = None
        for key in data_keys:
            val = financial_data.get(key)
            if val is not None and val != "" and val != 0:
                try:
                    actual = float(val)
                    matched_key = key
                    break
                except (ValueError, TypeError):
                    continue

        if actual is None:
            verified.append(ClaimVerification(
                claim=claim,
                matched_metric=claim.metric_hint,
                actual_value=None,
                deviation_pct=None,
                status="unmatched",
            ))
            continue

        # Normalize units
        norm_claim, norm_actual = _normalize_value(claim.value, claim.unit, actual)

        # Compute relative deviation
        if abs(norm_actual) > 1e-9:
            deviation = abs(norm_claim - norm_actual) / abs(norm_actual) * 100.0
        elif abs(norm_claim) > 1e-9:
            deviation = 100.0  # actual is ~0 but claim is not
        else:
            deviation = 0.0  # both ~0

        status = "confirmed" if deviation <= 10.0 else "contradicted"

        verified.append(ClaimVerification(
            claim=claim,
            matched_metric=matched_key,
            actual_value=actual,
            deviation_pct=round(deviation, 1),
            status=status,
        ))

    return verified


# ---------------------------------------------------------------------------
# Post-Search: Contradiction Detection
# ---------------------------------------------------------------------------

def detect_contradictions(
    verified: list[ClaimVerification],
    financial_data: dict,
) -> list[str]:
    """Build human-readable contradiction strings from contradicted claims.

    Args:
        verified: List of ClaimVerification results.
        financial_data: Original financial data dict (for context).

    Returns:
        List of human-readable warning strings.
    """
    warnings: list[str] = []

    for v in verified:
        if v.status != "contradicted":
            continue

        claim = v.claim
        # Format actual value for display
        if claim.unit == "percent":
            actual_display = f"{v.actual_value * 100:.1f}%" if v.actual_value is not None and abs(v.actual_value) < 1.0 else f"{v.actual_value:.1f}%"
        elif claim.unit in ("billions", "millions"):
            actual_display = f"${v.actual_value:,.0f}" if v.actual_value is not None else "N/A"
        else:
            actual_display = f"{v.actual_value:.1f}" if v.actual_value is not None else "N/A"

        metric_name = (v.matched_metric or claim.metric_hint).replace("_", " ")
        warnings.append(
            f"Web research claims {metric_name} of {claim.raw_text}, "
            f"but SEC/FMP data shows {actual_display} "
            f"({v.deviation_pct:.0f}% deviation). "
            f"The web source may be using a different time period or methodology."
        )

    return warnings


# ---------------------------------------------------------------------------
# Top-Level Orchestrator
# ---------------------------------------------------------------------------

def ground_web_research(
    raw_text: str,
    financial_data: dict,
    ticker: str,
    company_name: str,
    fact_anchor: str = "",
) -> GroundedResearch:
    """Validate web research against deterministic financial data.

    Called after web search returns, before results are consumed by agents.
    ALL validation is deterministic — no LLM calls.

    Returns GroundedResearch with confidence score and warnings.
    Agent decides how to use results based on confidence:
      - confidence >= 0.7: use as-is
      - confidence 0.4-0.7: use with warnings injected
      - confidence < 0.4: discard, optionally re-search with tighter query

    Args:
        raw_text: Raw text from web search result.
        financial_data: Dict with financial metrics (from SEC/FMP).
        ticker: Expected ticker symbol.
        company_name: Expected company name.
        fact_anchor: The fact anchor block injected into the search prompt.

    Returns:
        GroundedResearch with confidence, warnings, and grounded flag.
    """
    if not raw_text or not raw_text.strip():
        entity = EntityCheck(
            ticker_found=False,
            company_name_found=False,
            confidence=0.0,
            wrong_entity_signals=["Empty text"],
        )
        return GroundedResearch(
            original_text=raw_text or "",
            entity_check=entity,
            date_references=[],
            recency_score=0.0,
            claims=[],
            contradictions=[],
            confidence=0.0,
            warnings=["Web research returned empty text"],
            grounded=False,
            fact_anchor_used=fact_anchor,
        )

    # Run all validation steps
    entity = verify_entity(raw_text, ticker, company_name)
    dates, recency = check_recency(raw_text)
    claims = extract_numerical_claims(raw_text)
    verified = cross_reference_claims(claims, financial_data)
    contradictions = detect_contradictions(verified, financial_data)

    # Compute claim accuracy
    contradicted_count = sum(1 for v in verified if v.status == "contradicted")
    confirmed_count = sum(1 for v in verified if v.status == "confirmed")
    total_matched = contradicted_count + confirmed_count
    claim_accuracy = confirmed_count / total_matched if total_matched > 0 else 0.5

    # Overall confidence: weighted combination
    confidence = (
        entity.confidence * 0.4
        + recency * 0.3
        + claim_accuracy * 0.3
    )

    # Build warnings
    warnings: list[str] = []
    if entity.confidence < 0.5:
        warnings.append(
            f"Low entity confidence ({entity.confidence:.1f}) — results may be about wrong company"
        )
    if entity.wrong_entity_signals:
        for sig in entity.wrong_entity_signals:
            warnings.append(f"Wrong entity signal: {sig}")
    if recency < 0.3:
        warnings.append("Most web sources are >12 months old — research may be stale")
    if contradicted_count > 0:
        warnings.extend(contradictions)
    if len(dates) == 0:
        warnings.append("No dates found in web research — temporal grounding unclear")

    grounded = confidence >= 0.4

    if not grounded:
        log.warning(
            f"Web research for {ticker} grounding FAILED (confidence={confidence:.2f}): "
            f"entity={entity.confidence:.1f}, recency={recency:.2f}, "
            f"claims={confirmed_count}/{total_matched} confirmed"
        )
    else:
        log.info(
            f"Web research for {ticker} grounded (confidence={confidence:.2f}): "
            f"entity={entity.confidence:.1f}, recency={recency:.2f}, "
            f"claims={confirmed_count}/{total_matched} confirmed"
        )

    # Qualitative confidence scoring (Phase 4)
    qual_confidence = _score_qualitative_confidence(
        raw_text, verified, recency, contradicted_count
    )

    return GroundedResearch(
        original_text=raw_text,
        entity_check=entity,
        date_references=dates,
        recency_score=recency,
        claims=verified,
        contradictions=contradictions,
        confidence=round(confidence, 3),
        qualitative_confidence=round(qual_confidence, 3),
        warnings=warnings,
        grounded=grounded,
        fact_anchor_used=fact_anchor,
    )


# ---------------------------------------------------------------------------
# Qualitative confidence scoring (Phase 4)
# ---------------------------------------------------------------------------

# Hedging language patterns that reduce confidence
_HEDGING_PATTERNS = re.compile(
    r"\b(reportedly|allegedly|sources say|unconfirmed|rumored|speculation|"
    r"according to unnamed|believed to|might be|could potentially)\b",
    re.IGNORECASE,
)

# Named source patterns that increase confidence
_NAMED_SOURCE_PATTERNS = re.compile(
    r"\b(according to \w+ \w+|CEO \w+|CFO \w+|analyst at|"
    r"SEC filing|10-K|10-Q|8-K|earnings call|conference call|"
    r"annual report|investor presentation|Goldman|Morgan Stanley|"
    r"JP Morgan|Citi|Barclays|Credit Suisse|Bank of America)\b",
    re.IGNORECASE,
)


def _score_qualitative_confidence(
    text: str,
    verified_claims: list,
    recency_score: float,
    contradicted_count: int,
) -> float:
    """Score confidence in qualitative (non-numerical) claims.

    Factors:
    - Named source attribution: +0.05 per named source (max +0.3)
    - Hedging language: -0.05 per instance (max -0.25)
    - Recency: +0.1 if recent sources
    - Contradictions: -0.1 per contradicted numerical claim
    - Baseline: 0.5

    Returns:
        Float between 0.0 and 1.0
    """
    score = 0.5  # baseline

    # Named sources boost confidence
    named_sources = _NAMED_SOURCE_PATTERNS.findall(text)
    score += min(len(named_sources) * 0.05, 0.3)

    # Hedging language reduces confidence
    hedging = _HEDGING_PATTERNS.findall(text)
    score -= min(len(hedging) * 0.05, 0.25)

    # Recency bonus
    if recency_score > 0.7:
        score += 0.1

    # Contradiction penalty
    score -= contradicted_count * 0.1

    return max(0.0, min(1.0, score))
