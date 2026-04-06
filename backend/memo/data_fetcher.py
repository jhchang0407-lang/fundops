"""Memo Data Fetcher.

Fetches all data needed for memo generation using platform connectors.
Returns a canonical FinancialData object that the rest of the pipeline consumes.
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.core.financial_data import FinancialData, CompanyProfile

log = logging.getLogger("fundops.memo.data_fetcher")


async def fetch_pipeline_data(
    ticker: str,
    fmp=None,
    sec=None,
    yfinance=None,
) -> FinancialData:
    """Fetch all data for memo generation.

    Uses SEC EDGAR as primary source, FMP/yfinance for market data and estimates.
    """
    t0 = time.time()
    ticker = ticker.upper()
    errors = []

    # Parallel fetch from all sources
    tasks = {}

    # SEC data (primary)
    if sec:
        tasks["sec_financials"] = sec.get_financials(ticker)
        tasks["sec_profile"] = sec.get_profile(ticker)
        tasks["sec_filings_10k"] = sec.get_filings(ticker, "10-K")
        tasks["sec_filings_10q"] = sec.get_filings(ticker, "10-Q")
        tasks["sec_kpis"] = sec.get_key_metrics(ticker)

    # FMP data (enrichment)
    if fmp:
        tasks["fmp_profile"] = fmp.get_profile(ticker)
        tasks["fmp_estimates"] = fmp.get_estimates(ticker)
        tasks["fmp_peers"] = fmp.get_peers(ticker)
        tasks["fmp_key_metrics"] = fmp.get_key_metrics(ticker)
        tasks["fmp_financials"] = fmp.get_financials(ticker)
        tasks["fmp_quarterly"] = fmp.get_financials_quarterly(ticker)

    # yfinance (free fallback for quotes)
    if yfinance and not fmp:
        tasks["yf_quotes"] = yfinance.get_quotes([ticker])
        tasks["yf_profile"] = yfinance.get_profile(ticker)

    # Execute all in parallel
    keys = list(tasks.keys())
    results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results = {}
    for k, r in zip(keys, results_list):
        if isinstance(r, Exception):
            errors.append(f"{k}: {r}")
            log.warning(f"Fetch failed for {k}: {r}")
        else:
            results[k] = r

    # Build profile
    profile_data = {}
    if "sec_profile" in results and results["sec_profile"].ok:
        profile_data = results["sec_profile"].data
    if "fmp_profile" in results and results["fmp_profile"].ok:
        fmp_p = results["fmp_profile"].data
        profile_data.setdefault("name", fmp_p.get("companyName", ""))
        profile_data.setdefault("sector", fmp_p.get("sector", ""))
        profile_data.setdefault("industry", fmp_p.get("industry", ""))
        profile_data["market_cap"] = fmp_p.get("mktCap", 0)
        profile_data["price"] = fmp_p.get("price", 0)
    if "yf_profile" in results and results["yf_profile"].ok:
        yf_p = results["yf_profile"].data
        profile_data.setdefault("name", yf_p.get("companyName", ""))
        profile_data.setdefault("sector", yf_p.get("sector", ""))
        profile_data.setdefault("industry", yf_p.get("industry", ""))

    company_profile = CompanyProfile(
        ticker=ticker,
        name=profile_data.get("name", ""),
        sector=profile_data.get("sector", ""),
        industry=profile_data.get("industry", ""),
        sic_code=profile_data.get("sic", ""),
        is_bank=profile_data.get("isBank", False),
        is_insurance=profile_data.get("isInsurance", False),
        is_reit=profile_data.get("isReit", False),
    )

    # Build financials
    annual = []
    quarterly = []
    if "sec_financials" in results and results["sec_financials"].ok:
        sec_fin = results["sec_financials"].data
        annual = sec_fin.get("annual", [])
        quarterly = sec_fin.get("quarterly", [])

    # FMP fallback/supplement
    if "fmp_financials" in results and results["fmp_financials"].ok:
        fmp_fin = results["fmp_financials"].data
        if not annual:
            annual = fmp_fin.get("income_statement", [])
        # Merge balance sheet and cash flow into annual dicts
        for bs in fmp_fin.get("balance_sheet", []):
            date = bs.get("date", "")
            for a in annual:
                if a.get("date") == date:
                    a.update(bs)
                    break
        for cf in fmp_fin.get("cash_flow", []):
            date = cf.get("date", "")
            for a in annual:
                if a.get("date") == date:
                    a.update(cf)
                    break

    if "fmp_quarterly" in results and results["fmp_quarterly"].ok:
        fmp_q = results["fmp_quarterly"].data
        if not quarterly:
            quarterly = fmp_q.get("income_statement", [])

    # Filing text
    filing_text = {}
    if "sec_filings_10k" in results and results["sec_filings_10k"].ok:
        filing_text["10k"] = results["sec_filings_10k"].data
    if "sec_filings_10q" in results and results["sec_filings_10q"].ok:
        filing_text["10q"] = results["sec_filings_10q"].data

    # Estimates, peers, KPIs, market data
    estimates = None
    if "fmp_estimates" in results and results["fmp_estimates"].ok:
        estimates = results["fmp_estimates"].data

    peers = None
    if "fmp_peers" in results and results["fmp_peers"].ok:
        peers = results["fmp_peers"].data

    sector_kpis = None
    if "sec_kpis" in results and results["sec_kpis"].ok:
        sector_kpis = results["sec_kpis"].data

    key_metrics = None
    if "fmp_key_metrics" in results and results["fmp_key_metrics"].ok:
        key_metrics = results["fmp_key_metrics"].data

    # Market data from quotes
    market_data = None
    if "yf_quotes" in results and results["yf_quotes"].ok and results["yf_quotes"].data:
        q = results["yf_quotes"].data[0]
        market_data = {
            "price": q.get("price"),
            "marketCap": q.get("marketCap"),
            "beta": q.get("beta"),
            "yearHigh": q.get("yearHigh"),
            "yearLow": q.get("yearLow"),
        }
    # FMP profile also carries price/market cap — use it when yf_quotes wasn't fetched
    if not market_data and "fmp_profile" in results and results["fmp_profile"].ok:
        fmp_p = results["fmp_profile"].data or {}
        if fmp_p.get("price"):
            market_data = {
                "price": fmp_p.get("price"),
                "marketCap": fmp_p.get("mktCap"),
                "beta": fmp_p.get("beta"),
                "yearHigh": fmp_p.get("range", "").split("-")[-1].strip() if fmp_p.get("range") else None,
                "yearLow": fmp_p.get("range", "").split("-")[0].strip() if fmp_p.get("range") else None,
            }

    return FinancialData(
        ticker=ticker,
        profile=company_profile,
        financials_annual=annual,
        financials_quarterly=quarterly,
        ratios={},  # Calculated by transforms
        segments=None,
        filing_text=filing_text or None,
        estimates=estimates,
        peers=peers,
        sector_kpis=sector_kpis,
        market_data=market_data,
        key_metrics=key_metrics,
        source="sec_edgar+fmp" if fmp else "sec_edgar+yfinance",
        fetch_duration_s=time.time() - t0,
        fetch_errors=errors,
    )
