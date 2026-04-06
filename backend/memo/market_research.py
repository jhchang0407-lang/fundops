"""Memo Market Intelligence Research.

Runs 3 parallel web searches using the platform's WebSearchProvider
to gather current market context that SEC filings can't provide.

Results feed into memo sections as market_intel context.

E4: Integrates web grounding layer (A4) for pre-search fact anchoring
and post-search validation of web research results.
"""

import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger("fundops.memo.market_research")


def _opportunity_risk_prompt(
    ticker: str, company_name: str, sector: str, fact_anchor: str = "",
) -> str:
    base = f"""You are a sell-side research analyst. Research {company_name} ({ticker}):

1. WHY DOES THE DISCOUNT EXIST?
   - What drove the stock lower recently (past 3-12 months)?
   - Company-specific issues, sector rotation, or temporary fear?
   - Recent earnings misses, guidance cuts, or management changes?

2. CATALYSTS (0-12 months)
   - Product launches, contract wins, regulatory approvals?
   - Upcoming earnings events or investor days?

3. CURRENT RISKS (not in 10-K)
   - Active lawsuits, regulatory scrutiny?
   - Tariff or supply chain risks specific to {sector}?
   - Short seller reports or activist pressure?

Be specific with dates and numbers. Focus on LAST 12 MONTHS."""
    if fact_anchor:
        return fact_anchor + "\n\n" + base
    return base


def _competitive_products_prompt(
    ticker: str, company_name: str, sector: str, fact_anchor: str = "",
) -> str:
    base = f"""Research {company_name} ({ticker}):

1. TAM: Estimated total addressable market and CAGR?
2. COMPETITORS: Top 3-5 competitors in 2025-2026? Who's gaining share?
3. RECENT DEVELOPMENTS: New products, acquisitions, pivots in last 12 months?

Focus on developments NOT in their most recent 10-K filing."""
    if fact_anchor:
        return fact_anchor + "\n\n" + base
    return base


def _capital_analyst_prompt(
    ticker: str, company_name: str, fact_anchor: str = "",
) -> str:
    base = f"""Research {company_name} ({ticker}):

1. ANALYST CONSENSUS: Buy/hold/sell breakdown? Price target range?
2. CAPITAL ALLOCATION: Buybacks, dividends, debt changes in last 12 months?
3. INSTITUTIONAL ACTIVITY: Insider buying/selling? Short interest?

Be specific with numbers and dates. Focus on 2024-2026."""
    if fact_anchor:
        return fact_anchor + "\n\n" + base
    return base


def _grounding_dict(grounded) -> dict:
    """Extract a lightweight grounding summary dict from a GroundedResearch object."""
    return {
        "confidence": grounded.confidence,
        "recency_score": grounded.recency_score,
        "contradictions": grounded.contradictions,
        "warnings": grounded.warnings,
        "claims_confirmed": sum(1 for c in grounded.claims if c.status == "confirmed"),
        "claims_contradicted": sum(1 for c in grounded.claims if c.status == "contradicted"),
    }


async def fetch_market_intelligence(
    ticker: str,
    company_name: str,
    sector: str = "",
    web_search=None,
    financial_data: Optional[dict] = None,
) -> dict:
    """Run 3 parallel web searches and return structured market intelligence.

    Args:
        web_search: WebSearchProvider instance from platform.
        financial_data: Optional dict from data_fetcher with SEC/FMP metrics.
            When provided, enables pre-search fact anchoring and post-search
            grounding validation via the web grounding layer (A4).
    """
    empty = {
        "opportunity_risk": "",
        "competitive_products": "",
        "capital_analyst": "",
        "errors": [],
        "elapsed": 0.0,
        "_available": False,
    }

    if not web_search:
        return {**empty, "errors": ["No web search provider configured"]}

    t_start = time.time()
    context = {"agent": "memo_research", "ticker": ticker}

    # --- Pre-search anchoring (E4) ---
    fact_anchor = ""
    if financial_data:
        try:
            from backend.core.web_grounding import build_fact_anchor
            fact_anchor = build_fact_anchor(financial_data, ticker, company_name)
        except Exception as e:
            log.warning(f"Failed to build fact anchor for {ticker}: {e}")

    try:
        results = await asyncio.gather(
            web_search.search(
                _opportunity_risk_prompt(ticker, company_name, sector, fact_anchor),
                context,
            ),
            web_search.search(
                _competitive_products_prompt(ticker, company_name, sector, fact_anchor),
                context,
            ),
            web_search.search(
                _capital_analyst_prompt(ticker, company_name, fact_anchor),
                context,
            ),
            return_exceptions=True,
        )

        texts = []
        errors = []
        total_cost = 0.0
        for r in results:
            if isinstance(r, Exception):
                texts.append("")
                errors.append(str(r))
            else:
                texts.append(r.text)
                total_cost += r.cost
                if r.error:
                    errors.append(r.error)

        output = {
            "opportunity_risk": texts[0],
            "competitive_products": texts[1],
            "capital_analyst": texts[2],
            "errors": errors,
            "elapsed": time.time() - t_start,
            "cost": total_cost,
            "_available": any(t for t in texts),
        }

        # --- Post-search grounding (E4) ---
        if financial_data:
            try:
                from backend.core.web_grounding import ground_web_research

                query_names = ["opportunity_risk", "competitive_products", "capital_analyst"]
                grounding = {}
                confidences = []

                for i, name in enumerate(query_names):
                    text = texts[i]
                    if not text:
                        grounding[name] = {
                            "confidence": 0.0,
                            "recency_score": 0.0,
                            "contradictions": [],
                            "warnings": ["No text to ground"],
                            "claims_confirmed": 0,
                            "claims_contradicted": 0,
                        }
                        continue

                    try:
                        grounded = ground_web_research(
                            text, financial_data, ticker, company_name, fact_anchor,
                        )
                        grounding[name] = _grounding_dict(grounded)
                        confidences.append(grounded.confidence)
                    except Exception as ge:
                        log.warning(
                            f"Grounding failed for {ticker}/{name}: {ge}"
                        )
                        grounding[name] = {
                            "confidence": 0.0,
                            "recency_score": 0.0,
                            "contradictions": [],
                            "warnings": [f"Grounding error: {ge}"],
                            "claims_confirmed": 0,
                            "claims_contradicted": 0,
                        }

                output["grounding"] = grounding

                # Build grounding summary
                total_contradictions = sum(
                    len(g.get("contradictions", [])) for g in grounding.values()
                )
                output["grounding_summary"] = {
                    "avg_confidence": (
                        round(sum(confidences) / len(confidences), 3)
                        if confidences
                        else 0.0
                    ),
                    "min_confidence": (
                        round(min(confidences), 3) if confidences else 0.0
                    ),
                    "stale_warning": any(
                        g.get("recency_score", 1.0) < 0.3
                        for g in grounding.values()
                    ),
                    "total_contradictions": total_contradictions,
                }

            except Exception as e:
                log.warning(f"Post-search grounding failed for {ticker}: {e}")

        return output

    except Exception as e:
        log.error(f"Market research failed: {e}")
        return {**empty, "errors": [str(e)], "elapsed": time.time() - t_start}
