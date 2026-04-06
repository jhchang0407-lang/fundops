"""
FundOps Canonical Financial Data Model.

Standard data format that all connectors produce and the memo pipeline consumes.
Connectors translate their native formats (SEC XBRL, FMP JSON, Bloomberg) into
this schema. The memo pipeline never touches raw source data directly.

Metric naming convention: FMP-compatible names as canonical standard
(revenue, grossProfit, operatingIncome, netIncome, etc.).
SEC connector maps XBRL tags to these names in its adapter.

Required core: financials, ratios, profile.
Optional enrichment: filing text, estimates, peers, segments, sector KPIs.
Memo degrades gracefully without optional data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CompanyProfile:
    """Company metadata."""
    ticker: str
    name: str
    sector: str = ""
    industry: str = ""
    sic_code: str = ""
    exchange: str = ""
    country: str = "US"
    fiscal_year_end: str = ""  # e.g., "December"
    ipo_date: str = ""
    market_cap: float = 0.0
    employees: int = 0
    description: str = ""
    is_bank: bool = False
    is_insurance: bool = False
    is_reit: bool = False


@dataclass
class FinancialData:
    """
    Canonical financial data that all connectors produce.

    Required fields must be populated by any connector.
    Optional fields enhance memo quality but are not required.
    """
    ticker: str
    profile: CompanyProfile

    # REQUIRED: 5-year annual financials (income, balance sheet, cash flow)
    # Each dict has keys like: revenue, grossProfit, operatingIncome, netIncome,
    # totalAssets, totalDebt, operatingCashFlow, capitalExpenditure, etc.
    # Plus metadata: date, calendarYear, period
    financials_annual: list[dict] = field(default_factory=list)

    # REQUIRED: 8 quarters of financials (same key structure)
    financials_quarterly: list[dict] = field(default_factory=list)

    # REQUIRED: calculated ratios (ROE, margins, growth, ROIC, etc.)
    ratios: dict = field(default_factory=dict)

    # --- Optional enrichment (memo degrades gracefully without these) ---

    # Revenue by business segment / geography (SEC-specific)
    segments: Optional[dict] = None

    # 10-K/10-Q text sections: {"item_1": "...", "item_1a": "...", "item_7": "..."}
    filing_text: Optional[dict] = None

    # Analyst consensus estimates (forward EPS, revenue)
    estimates: Optional[list[dict]] = None

    # Comparable companies with multiples
    peers: Optional[list[dict]] = None

    # Sector-specific KPIs (bank: NIM, CET1; tech: ARR, NRR; etc.)
    sector_kpis: Optional[dict] = None

    # Market data (price, beta, 52wk high/low, volume)
    market_data: Optional[dict] = None

    # Growth rates (revenue growth, EPS growth, etc.)
    growth: Optional[dict] = None

    # Key metrics (FCF yield, EV/EBITDA, P/E, etc.)
    key_metrics: Optional[list[dict]] = None

    # Fetch metadata
    source: str = ""  # "sec_edgar", "fmp", "bloomberg"
    fetch_duration_s: float = 0.0
    fetch_errors: list[str] = field(default_factory=list)

    @property
    def has_filing_text(self) -> bool:
        return bool(self.filing_text)

    @property
    def has_estimates(self) -> bool:
        return bool(self.estimates)

    @property
    def has_peers(self) -> bool:
        return bool(self.peers)

    @property
    def has_segments(self) -> bool:
        return bool(self.segments)

    @property
    def is_complete(self) -> bool:
        """Check if required data is present."""
        return bool(
            self.profile
            and self.financials_annual
            and self.financials_quarterly
            and self.ratios
        )

    @property
    def has_minimum_viable_data(self) -> bool:
        """Stricter check: enough data to write a meaningful memo without fabrication.

        Requires: profile, at least 1 year of annual financials with revenue > 0,
        a live price, and at least basic ratios.
        """
        if not self.profile:
            return False
        annual = self.financials_annual
        if not annual:
            return False
        latest = annual[0] if annual else {}
        revenue = latest.get("revenue", 0) or 0
        shares = latest.get("weightedAverageShsOutDil", 0) or 0
        if revenue <= 0 or shares <= 0:
            return False
        price = (self.market_data or {}).get("price", 0) or 0
        if price <= 0:
            return False
        return True

    def data_coverage_report(self) -> dict:
        """Return a structured report of what data is available and what's missing.

        Used to prefix memos with honest data coverage so the AI doesn't fabricate.
        """
        annual = self.financials_annual or []
        quarterly = self.financials_quarterly or []
        latest = annual[0] if annual else {}
        price = (self.market_data or {}).get("price", 0) or 0

        available = []
        missing = []
        warnings = []

        # Profile
        if self.profile and self.profile.name:
            available.append(f"Company profile ({self.profile.name}, {self.profile.sector})")
        else:
            missing.append("Company profile / sector")

        # Financials
        if len(annual) >= 3:
            available.append(f"{len(annual)} years of annual financials")
        elif len(annual) >= 1:
            available.append(f"{len(annual)} year(s) of annual financials (limited history)")
            warnings.append("Only 1-2 years of history — trend analysis will be limited")
        else:
            missing.append("Annual financial statements")

        if quarterly:
            available.append(f"{len(quarterly)} quarters of data")
        else:
            missing.append("Quarterly financials")

        # Revenue check
        revenue = latest.get("revenue", 0) or 0
        if revenue > 0:
            available.append(f"Revenue data (${revenue/1e9:.1f}B latest year)")
        else:
            missing.append("Revenue figures")
            warnings.append("Revenue is zero or missing — valuation and margin analysis will be unreliable")

        # Price
        if price > 0:
            available.append(f"Live market price (${price:.2f})")
        else:
            missing.append("Live market price")
            warnings.append("No price data — discount-to-fair-value cannot be calculated")

        # Filing text
        if self.has_filing_text:
            available.append("SEC filing text (10-K/10-Q)")
        else:
            missing.append("SEC filing text (10-K/10-Q)")
            warnings.append("No SEC filings — competitive moat, management, and risk sections will rely on LLM priors only")

        # Ratios
        if self.ratios:
            available.append("Financial ratios (P/E, EV/EBITDA, etc.)")
        else:
            missing.append("Financial ratios")

        # Peers
        if self.has_peers:
            available.append("Peer comparison data")
        else:
            missing.append("Peer data — benchmarking section will be qualitative only")

        # Estimates
        if self.has_estimates:
            available.append("Forward analyst estimates")
        else:
            missing.append("Forward estimates")

        overall = "complete" if not missing else ("partial" if available else "minimal")

        return {
            "overall": overall,
            "available": available,
            "missing": missing,
            "warnings": warnings,
            "annual_periods": len(annual),
            "quarterly_periods": len(quarterly),
            "has_price": price > 0,
            "has_filings": self.has_filing_text,
            "fetch_errors": self.fetch_errors,
        }

    def summary(self) -> dict:
        """Quick summary of what data is available."""
        return {
            "ticker": self.ticker,
            "source": self.source,
            "profile": bool(self.profile),
            "annual_periods": len(self.financials_annual),
            "quarterly_periods": len(self.financials_quarterly),
            "ratios": bool(self.ratios),
            "segments": self.has_segments,
            "filing_text": self.has_filing_text,
            "estimates": self.has_estimates,
            "peers": self.has_peers,
            "sector_kpis": bool(self.sector_kpis),
            "market_data": bool(self.market_data),
            "errors": self.fetch_errors,
        }

    # --- Serialization ---

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for DB storage."""
        from dataclasses import asdict
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FinancialData":
        """Deserialize from a dict (e.g. from DB JSON column)."""
        profile_data = d.pop("profile", {}) or {}
        profile = CompanyProfile(**{
            k: v for k, v in profile_data.items()
            if k in CompanyProfile.__dataclass_fields__
        }) if profile_data else CompanyProfile(ticker=d.get("ticker", ""), name="")
        return cls(profile=profile, **{
            k: v for k, v in d.items()
            if k in cls.__dataclass_fields__ and k != "profile"
        })

    def to_flat_metrics(self, live_price: float = None) -> dict:
        """Extract a flat dict of key metrics for agents that need simple values.

        SEC-derived metrics come from stored ratios/financials.
        Price-dependent metrics (PE, FCF yield, etc.) are computed fresh
        if live_price is provided.
        """
        ratios = self.ratios or {}
        # Latest annual ratios (list of dicts sorted by date desc)
        latest_ratios = ratios[0] if isinstance(ratios, list) and ratios else (ratios if isinstance(ratios, dict) else {})

        annual = self.financials_annual or []
        latest = annual[0] if annual else {}

        price = live_price or (self.market_data or {}).get("price", 0) or 0
        market_cap = (self.market_data or {}).get("marketCap", 0) or 0

        # Core SEC metrics (stable, from filings)
        revenue = latest.get("revenue", 0) or 0
        net_income = latest.get("netIncome", 0) or 0
        shares = latest.get("weightedAverageShsOutDil", 0) or 0
        eps = net_income / shares if shares > 0 else 0
        fcf = latest.get("freeCashFlow", 0) or 0
        owner_eps = eps  # Real EPS from SEC, not derived from PE

        metrics = {
            # Identity
            "ticker": self.ticker,
            "company_name": self.profile.name if self.profile else "",
            "sector": self.profile.sector if self.profile else "",
            "industry": self.profile.industry if self.profile else "",
            "is_bank": self.profile.is_bank if self.profile else False,

            # Margins (from ratios, as decimals 0-1)
            "gross_margin": latest_ratios.get("grossProfitMargin", 0) or 0,
            "operating_margin": latest_ratios.get("operatingProfitMargin", 0) or 0,
            "net_margin": latest_ratios.get("netProfitMargin", 0) or 0,
            "fcf_margin": latest_ratios.get("freeCashFlowMargin", 0) or 0,

            # Returns (as decimals)
            "roic": latest_ratios.get("returnOnInvestedCapital", 0) or 0,
            "roe": latest_ratios.get("returnOnEquity", 0) or 0,
            "roa": latest_ratios.get("returnOnAssets", 0) or 0,

            # Leverage
            "debt_equity": latest_ratios.get("debtToEquity", latest_ratios.get("debtToEquityRatio", 0)) or 0,
            "current_ratio": latest_ratios.get("currentRatio", 0) or 0,
            "interest_coverage": latest_ratios.get("interestCoverage", 0) or 0,

            # Cash flow
            "fcf_conversion": latest_ratios.get("freeCashFlowConversion", 0) or 0,

            # Growth (compute from multi-year if available)
            "revenue_growth": 0,
            "earnings_growth": 0,

            # Per-share
            "eps": round(eps, 2),
            "owner_eps": round(owner_eps, 2),
            "fcf_per_share": round(fcf / shares, 2) if shares > 0 else 0,

            # Absolute values
            "revenue": revenue,
            "net_income": net_income,
            "fcf": fcf,

            # Price-dependent (computed fresh)
            "price": price,
            "market_cap": market_cap,
        }

        # Compute growth from multi-year data
        if len(annual) >= 2:
            prev_rev = annual[1].get("revenue", 0) or 0
            if prev_rev > 0:
                metrics["revenue_growth"] = (revenue - prev_rev) / prev_rev
            prev_ni = annual[1].get("netIncome", 0) or 0
            if prev_ni > 0:
                metrics["earnings_growth"] = (net_income - prev_ni) / prev_ni

        # Price-dependent metrics (always compute fresh from live_price)
        if price > 0:
            metrics["pe"] = round(price / eps, 1) if eps > 0 else 0
            metrics["fcf_yield"] = round(fcf / (market_cap or price * shares), 4) if (market_cap or shares) else 0
            metrics["earnings_yield"] = round(eps / price, 4) if eps else 0
        else:
            metrics["pe"] = 0
            metrics["fcf_yield"] = 0
            metrics["earnings_yield"] = 0

        return metrics


# Canonical metric names (FMP-compatible)
# SEC connector maps XBRL tags to these names
INCOME_STATEMENT_KEYS = [
    "revenue", "costOfRevenue", "grossProfit", "operatingExpenses",
    "operatingIncome", "interestExpense", "incomeBeforeTax",
    "incomeTaxExpense", "netIncome", "eps", "epsDiluted",
    "weightedAverageShsOut", "weightedAverageShsOutDil",
    "researchAndDevelopmentExpenses", "sellingGeneralAndAdministrativeExpenses",
    "depreciationAndAmortization", "ebitda",
    # Bank-specific
    "netInterestIncome", "provisionForLoanLosses",
    # Insurance-specific
    "premiumsEarned", "netInvestmentIncome",
]

BALANCE_SHEET_KEYS = [
    "totalAssets", "totalCurrentAssets", "totalNonCurrentAssets",
    "totalLiabilities", "totalCurrentLiabilities", "totalNonCurrentLiabilities",
    "totalStockholdersEquity", "totalDebt", "netDebt",
    "cashAndCashEquivalents", "cashAndShortTermInvestments",
    "netReceivables", "inventory", "goodwill", "intangibleAssets",
    "propertyPlantEquipmentNet", "accountPayables",
    # Bank-specific
    "totalDeposits", "netLoans",
]

CASH_FLOW_KEYS = [
    "operatingCashFlow", "capitalExpenditure", "freeCashFlow",
    "acquisitionsNet", "debtRepayment", "commonStockRepurchased",
    "dividendsPaid", "netCashUsedForInvestingActivites",
    "netCashUsedProvidedByFinancingActivities",
    "stockBasedCompensation", "changeInWorkingCapital",
]
