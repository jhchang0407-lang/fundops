"""
Web Search Provider interface for FundOps.

Abstract interface that agents use for web research. Ships with OpenAI
implementation (web_search_preview tool). Pluggable for Perplexity, Tavily, etc.

Usage:
    from backend.core.web_search import OpenAIWebSearch

    search = OpenAIWebSearch(llm_client)
    result = await search.search(
        query="Why is PAYC trading at a discount?",
        context={"ticker": "PAYC", "sector": "Technology"},
    )
    # result.text, result.sources, result.cost
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

log = logging.getLogger("fundops.web_search")


@dataclass
class SearchResult:
    """Result from a web search."""
    text: str
    sources: list[dict] = field(default_factory=list)
    cost: float = 0.0
    duration_s: float = 0.0
    error: str = ""


class WebSearchProvider(ABC):
    """Abstract web search interface. Agents call this, not OpenAI directly."""

    @abstractmethod
    async def search(self, query: str, context: dict | None = None) -> SearchResult:
        """
        Run a web search and return synthesized results.

        Args:
            query: The search prompt (can be multi-paragraph).
            context: Optional context dict (ticker, sector, etc.) for prompt enrichment.
        """
        ...


class OpenAIWebSearch(WebSearchProvider):
    """Web search via OpenAI Responses API with web_search_preview tool."""

    def __init__(self, llm_client, search_context_size: str = "medium"):
        """
        Args:
            llm_client: LLMClient instance (shared).
            search_context_size: "low", "medium", or "high".
        """
        self.llm = llm_client
        self.search_context_size = search_context_size

    async def search(self, query: str, context: dict | None = None) -> SearchResult:
        t0 = time.time()
        try:
            agent = (context or {}).get("agent", "web_search")
            result = await self.llm.generate_with_search(
                prompt=query,
                agent=agent,
                reasoning_effort="medium",
                search_context_size=self.search_context_size,
            )
            return SearchResult(
                text=result.text,
                cost=result.cost,
                duration_s=result.duration_s,
            )
        except Exception as e:
            log.error(f"Web search failed: {e}")
            return SearchResult(
                text="",
                error=str(e),
                duration_s=time.time() - t0,
            )


class NoOpWebSearch(WebSearchProvider):
    """Placeholder when web search is disabled."""

    async def search(self, query: str, context: dict | None = None) -> SearchResult:
        return SearchResult(text="", error="Web search disabled")
