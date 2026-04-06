"""FundOps Data Connector Framework.

Each connector provides data from an external source (FMP, SEC EDGAR, Bloomberg, etc.)
via a standard interface. Connectors register via entry_points.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConnectorResult:
    """Standard result from a data connector call."""
    connector: str
    capability: str  # quotes, financials, filings, estimates
    data: Any = None
    error: Optional[str] = None
    cached: bool = False
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None


class DataConnector(ABC):
    """Base class for all data connectors.

    Capabilities a connector can provide:
    - quotes: current and historical prices
    - financials: income statement, balance sheet, cash flow
    - filings: SEC filings (10-K, 10-Q text)
    - estimates: analyst consensus estimates
    - profile: company description, sector, industry
    - peers: comparable companies
    - key_metrics: ratios, ROIC, margins, etc.
    """

    name: str = ""
    capabilities: list[str] = []

    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    async def get_quotes(self, tickers: list[str]) -> ConnectorResult:
        """Get current quotes for a list of tickers."""
        ...

    @abstractmethod
    async def get_financials(self, ticker: str, years: int = 5) -> ConnectorResult:
        """Get financial statements for a ticker."""
        ...

    async def get_filings(self, ticker: str, filing_type: str = "10-K") -> ConnectorResult:
        """Get SEC filing text. Override if supported."""
        return ConnectorResult(connector=self.name, capability="filings",
                               error="Not supported by this connector")

    async def get_estimates(self, ticker: str) -> ConnectorResult:
        """Get analyst estimates. Override if supported."""
        return ConnectorResult(connector=self.name, capability="estimates",
                               error="Not supported by this connector")

    async def get_profile(self, ticker: str) -> ConnectorResult:
        """Get company profile. Override if supported."""
        return ConnectorResult(connector=self.name, capability="profile",
                               error="Not supported by this connector")

    async def get_peers(self, ticker: str) -> ConnectorResult:
        """Get peer companies. Override if supported."""
        return ConnectorResult(connector=self.name, capability="peers",
                               error="Not supported by this connector")

    async def get_key_metrics(self, ticker: str) -> ConnectorResult:
        """Get key financial metrics/ratios. Override if supported."""
        return ConnectorResult(connector=self.name, capability="key_metrics",
                               error="Not supported by this connector")

    def validate_config(self) -> list[str]:
        """Validate connector configuration."""
        return []

    async def health_check(self) -> bool:
        """Check if the data source is reachable."""
        return True
