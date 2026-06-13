"""Web research: bounded, cited online search that AUGMENTS SEC-grounded work.

SEC filings stay the evidence base everywhere; this layer adds recent context
(news, market commentary) where filings can't reach. It is:

- gated by the Settings toggle (`providers.web_search`) — off means no network;
- provider-pluggable: Tavily or Brave when a key is present (env or the local
  credential store), else a keyless DuckDuckGo HTML fallback;
- bounded and honest: a fixed result cap, short snippets, and every result
  carries its URL so downstream prompts can cite [W1]-style sources;
- degradation-safe: any failure returns [] and a note, never an exception.

Callers (thesis, memo, thematic research) must treat results as *context*,
never as authoritative facts — prompts say so explicitly.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.parse
import urllib.request

from backend.core import opconfig

log = logging.getLogger("fundops.web_research")

FETCH_TIMEOUT_S = 20
MAX_RESULTS = 5
SNIPPET_CHARS = 300

# Keyed search-API providers (DuckDuckGo is the keyless fallback; "harness"
# defers to the coding-agent harness's own web tool — see active_provider).
WEB_PROVIDERS = {
    "tavily": {"label": "Tavily", "env": "TAVILY_API_KEY",
               "console_url": "https://app.tavily.com"},
    "brave": {"label": "Brave Search", "env": "BRAVE_API_KEY",
              "console_url": "https://api-dashboard.search.brave.com"},
    "serper": {"label": "Serper (Google)", "env": "SERPER_API_KEY",
               "console_url": "https://serper.dev/api-key"},
}

# Every choice the user can pin in Settings (in addition to per-provider keys).
PROVIDER_CHOICES = [
    {"id": "auto", "label": "Auto (keyed if set, else DuckDuckGo)", "keyed": False},
    {"id": "duckduckgo", "label": "DuckDuckGo (keyless)", "keyed": False},
    {"id": "tavily", "label": "Tavily", "keyed": True},
    {"id": "brave", "label": "Brave Search", "keyed": True},
    {"id": "serper", "label": "Serper (Google)", "keyed": True},
    {"id": "harness", "label": "Coding-agent harness (no key)", "keyed": False},
]


def enabled() -> bool:
    return bool(opconfig.load()["providers"].get("web_search"))


def chosen_provider() -> str:
    """The user's pinned backend choice; 'auto' by default."""
    return opconfig.load()["providers"].get("web_search_provider") or "auto"


def active_provider() -> str | None:
    """Which backend serves a query right now. Honors the user's explicit choice;
    'auto' picks a keyed provider (Tavily/Brave/Serper) when its key is present
    else keyless DuckDuckGo. None when web search is toggled off."""
    if not enabled():
        return None
    choice = chosen_provider()
    if choice == "harness":
        return "harness"          # the agent harness does the search itself
    if choice in ("duckduckgo", "ddg"):
        return "ddg"
    if choice in WEB_PROVIDERS:    # an explicitly pinned keyed provider
        return choice
    # auto (or unknown): first keyed provider with a key, else keyless DDG.
    for pid, spec in WEB_PROVIDERS.items():
        if opconfig.secret(pid, spec["env"]):
            return pid
    return "ddg"


def _http(url: str, headers: dict | None = None, data: bytes | None = None) -> str:
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": opconfig.load()["providers"]["sec_user_agent"],
                 **(headers or {})})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clip(text: str) -> str:
    text = re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip()
    return text[:SNIPPET_CHARS]


def _search_tavily(query: str, key: str, max_results: int) -> list[dict]:
    body = json.dumps({"api_key": key, "query": query,
                       "max_results": max_results, "search_depth": "basic"}).encode()
    payload = json.loads(_http("https://api.tavily.com/search",
                               headers={"Content-Type": "application/json"}, data=body))
    return [{"title": _clip(r.get("title")), "url": r.get("url"),
             "snippet": _clip(r.get("content"))}
            for r in (payload.get("results") or [])[:max_results] if r.get("url")]


def _search_brave(query: str, key: str, max_results: int) -> list[dict]:
    url = ("https://api.search.brave.com/res/v1/web/search?q="
           + urllib.parse.quote(query) + f"&count={max_results}")
    payload = json.loads(_http(url, headers={"X-Subscription-Token": key,
                                             "Accept": "application/json"}))
    rows = ((payload.get("web") or {}).get("results") or [])[:max_results]
    return [{"title": _clip(r.get("title")), "url": r.get("url"),
             "snippet": _clip(r.get("description"))}
            for r in rows if r.get("url")]


def _search_serper(query: str, key: str, max_results: int) -> list[dict]:
    body = json.dumps({"q": query, "num": max_results}).encode()
    payload = json.loads(_http("https://google.serper.dev/search",
                               headers={"X-API-KEY": key, "Content-Type": "application/json"},
                               data=body))
    rows = (payload.get("organic") or [])[:max_results]
    return [{"title": _clip(r.get("title")), "url": r.get("link"),
             "snippet": _clip(r.get("snippet"))}
            for r in rows if r.get("link")]


_DDG_RESULT = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?(?:<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>)?',
    re.S)


def _search_ddg(query: str, max_results: int) -> list[dict]:
    """Keyless fallback via DuckDuckGo's HTML endpoint. Best-effort: markup can
    change; failures degrade to []. Result hrefs are DDG redirects carrying the
    real URL in the uddg param."""
    page = _http("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    out = []
    for m in _DDG_RESULT.finditer(page):
        href = m.group("href")
        real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
        title = _clip(re.sub(r"<[^>]+>", "", m.group("title") or ""))
        snippet = _clip(re.sub(r"<[^>]+>", "", m.group("snippet") or ""))
        if real and title:
            out.append({"title": title, "url": real, "snippet": snippet})
        if len(out) >= max_results:
            break
    return out


async def _news_fallback(ticker: str, max_results: int) -> list[dict]:
    """Company-scoped keyless fallback: recent yfinance headlines. Far more
    reliable than scraping a search engine, and already cached app-wide."""
    from backend.services.news import company_news

    out = await company_news(ticker)
    return [{"title": _clip(i.get("title")),
             "url": i.get("link") or i.get("url") or "",
             "snippet": _clip(i.get("publisher") or "")}
            for i in (out.get("items") or [])[:max_results] if i.get("title")]


async def search(query: str, max_results: int = MAX_RESULTS,
                 ticker: str | None = None) -> dict:
    """One bounded web search. Returns {provider, results, note}; results []
    whenever the toggle is off, no backend works, or the network fails. For
    company-scoped queries pass `ticker`: when no keyed provider is configured
    and the keyless engine is blocked, recent headlines stand in."""
    provider = active_provider()
    if provider is None:
        return {"provider": None, "results": [],
                "note": "web search disabled in Settings"}
    if provider == "harness":
        # The coding-agent harness searches inline during the model call — there
        # is no separate fetch here. Callers feed the model its own web tool.
        return {"provider": "harness", "results": [],
                "note": "web search handled by the coding-agent harness"}
    max_results = max(1, min(int(max_results), MAX_RESULTS))
    _DISPATCH = {"tavily": _search_tavily, "brave": _search_brave, "serper": _search_serper}
    results: list[dict] = []
    try:
        if provider in _DISPATCH:
            key = opconfig.secret(provider, WEB_PROVIDERS[provider]["env"])
            if key:
                results = await asyncio.to_thread(_DISPATCH[provider], query, key, max_results)
            else:  # pinned a keyed provider but no key — fall back to keyless
                provider = "ddg"
                results = await asyncio.to_thread(_search_ddg, query, max_results)
        else:
            results = await asyncio.to_thread(_search_ddg, query, max_results)
    except Exception as exc:
        log.warning("web search (%s) failed for %r: %s", provider, query, exc)
        if not ticker:
            return {"provider": provider, "results": [],
                    "note": f"web search unavailable ({provider}): {exc}"}
    if not results and ticker:
        try:
            results = await _news_fallback(ticker, max_results)
            if results:
                provider = "news"
        except Exception as exc:  # headlines are best-effort too
            log.debug("news fallback failed for %s: %s", ticker, exc)
    return {"provider": provider, "results": results,
            "note": None if results else "no web results"}


def context_block(results: list[dict], start_index: int = 1) -> tuple[str, list[str]]:
    """Render results as a prompt block + source lines. Sources are [W1]…
    so web context never collides with filing citation numbers, and prompts
    can require 'web claims cite [Wn]'."""
    lines, sources = [], []
    for i, r in enumerate(results, start_index):
        tag = f"W{i}"
        lines.append(f"[{tag}] {r['title']} — {r['snippet']}" if r.get("snippet")
                     else f"[{tag}] {r['title']}")
        sources.append(f"[{tag}] {r['title']} — {r['url']}")
    return "\n".join(lines), sources
