"""SEC EDGAR Data Connector.

Thin adapter wrapping the backend/core/sec/ modules into the DataConnector
interface. Provides financials, filings, profiles, and sector KPIs from
SEC EDGAR (free, no API key needed).

Translates SEC XBRL data to canonical FinancialData format.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.connectors import ConnectorResult, DataConnector
from backend.core.financial_data import CompanyProfile, FinancialData

log = logging.getLogger("fundops.sec_edgar")


class SECEdgarConnector(DataConnector):
    """SEC EDGAR connector wrapping core/sec/ modules."""

    name = "sec_edgar"
    capabilities = ["financials", "filings", "profile", "key_metrics"]

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def get_quotes(self, tickers: list[str]) -> ConnectorResult:
        """SEC doesn't provide real-time quotes."""
        return ConnectorResult(
            connector=self.name, capability="quotes",
            error="SEC EDGAR does not provide real-time quotes. Use FMP.",
        )

    async def get_financials(self, ticker: str, years: int = 5) -> ConnectorResult:
        """Get financial statements from SEC XBRL."""
        t0 = time.time()
        try:
            from backend.core.sec.statements import get_annual_statements

            financials = get_annual_statements(ticker, years=years)

            return ConnectorResult(
                connector=self.name, capability="financials",
                data=financials,
                duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC financials failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="financials",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_filings(self, ticker: str, filing_type: str = "10-K") -> ConnectorResult:
        """Get filing text (10-K/10-Q sections) via edgartools."""
        t0 = time.time()
        try:
            from backend.core.sec.filings import get_filing_text
            data = get_filing_text(ticker, form=filing_type)
            if "error" in data:
                return ConnectorResult(
                    connector=self.name, capability="filings",
                    error=data["error"], duration_s=time.time() - t0,
                )
            return ConnectorResult(
                connector=self.name, capability="filings",
                data=data, duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC filings failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="filings",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_profile(self, ticker: str) -> ConnectorResult:
        """Get company profile from SEC submissions."""
        t0 = time.time()
        try:
            from backend.core.sec.profile import get_profile

            profile = get_profile(ticker)

            return ConnectorResult(
                connector=self.name, capability="profile",
                data=profile, duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC profile failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="profile",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_key_metrics(self, ticker: str) -> ConnectorResult:
        """Get sector-specific KPIs from SEC XBRL data."""
        t0 = time.time()
        try:
            from backend.core.sec.sectors import get_sector_kpis

            kpis = get_sector_kpis(ticker)

            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                data=kpis, duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC KPIs failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_segments(self, ticker: str) -> ConnectorResult:
        """Get revenue segments from SEC XBRL instance documents."""
        t0 = time.time()
        try:
            from backend.core.sec.segments import get_segments
            data = get_segments(ticker)
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                data=data, duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC segments failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                error=str(e), duration_s=time.time() - t0,
            )

    async def get_ratios(self, ticker: str) -> ConnectorResult:
        """Get calculated ratios from SEC financial data."""
        t0 = time.time()
        try:
            from backend.core.sec.statements import get_annual_statements
            from backend.core.sec.ratios import calculate_ratios

            financials = get_annual_statements(ticker, years=5)
            ratios = calculate_ratios(
                income_statements=financials.get("income_statement", []),
                balance_sheets=financials.get("balance_sheet", []),
                cash_flows=financials.get("cash_flow", []),
            )

            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                data=ratios, duration_s=time.time() - t0,
            )
        except Exception as e:
            log.error(f"SEC ratios failed for {ticker}: {e}")
            return ConnectorResult(
                connector=self.name, capability="key_metrics",
                error=str(e), duration_s=time.time() - t0,
            )

    def to_financial_data(self, ticker: str, profile_data: dict,
                          financials: dict, ratios: dict = None,
                          filing_text: dict = None, segments: dict = None,
                          sector_kpis: dict = None) -> FinancialData:
        """Translate SEC data to canonical FinancialData format."""
        company_profile = CompanyProfile(
            ticker=ticker,
            name=profile_data.get("name", ""),
            sector=profile_data.get("sector", ""),
            industry=profile_data.get("industry", ""),
            sic_code=profile_data.get("sic", ""),
            fiscal_year_end=profile_data.get("fiscal_year_end", ""),
            is_bank=profile_data.get("isBank", False),
            is_insurance=profile_data.get("isInsurance", False),
            is_reit=profile_data.get("isReit", False),
        )

        return FinancialData(
            ticker=ticker,
            profile=company_profile,
            financials_annual=financials.get("annual", []),
            financials_quarterly=financials.get("quarterly", []),
            ratios=ratios or {},
            segments=segments,
            filing_text=filing_text,
            sector_kpis=sector_kpis,
            source="sec_edgar",
        )

    def validate_config(self) -> list[str]:
        return []  # SEC EDGAR is free, no config needed

    async def health_check(self) -> bool:
        try:
            from backend.core.sec.client import ticker_to_cik
            cik = ticker_to_cik("AAPL")
            return cik is not None
        except Exception:
            return False
