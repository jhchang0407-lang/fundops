"""Product guide: the conversation explains FundOps itself.

AI is the first interface — not just for strategy and data, but for
understanding every feature. "How does IC review decide?", "what is thesis
health?", "where do memos come from?" route here and are answered from a
curated, honest self-description (never from model imagination), with an
action chip to open the relevant surface.

The guide text is the product's contract with the user: what is deterministic
vs model-written, what each stage consumes and produces, and where data comes
from. Keep it truthful — it is quoted to the user verbatim by the stub and as
grounding for the model path.
"""

from __future__ import annotations

from backend.core.ai import get_ai

# topic id -> (route, title, honest description)
GUIDE: dict[str, tuple[str, str, str]] = {
    "home": ("/", "Home & Briefing", (
        "Home is the conversation plus a deterministic morning Briefing composed "
        "only from retained records — filings on held tickers, thesis-health "
        "changes, learning items, running work, upcoming events, and cached FRED "
        "macro. Every Briefing claim links to its source; nothing in it is "
        "model-written.")),
    "inbox": ("/inbox", "Inbox", (
        "The Inbox is triage: Decisions (strategy proposals awaiting your "
        "approval), Portfolio review (positions under pressure, constitution-fit "
        "opportunities), Attention (filing events on holdings, broken thesis "
        "health), and Recent activity. Responses are recorded as decision "
        "records; nothing here trades for you.")),
    "runs": ("/runs", "Runs & the pipeline", (
        "Runs shows the four-stage funnel as durable records: Screener → Thesis "
        "→ IC review → Memo. 'Run full pipeline' chains them with explicit "
        "handoffs; each stage also runs alone from its page. Runs are resumable "
        "— completed work is never regenerated — and an operational failure is "
        "recorded as failure, never as an investment judgment. The Result column "
        "shows what each run actually produced.")),
    "screener": ("/screener", "Screener (stage 1)", (
        "The screener evaluates the whole universe (e.g. Russell 2000) against "
        "your Constitution's criteria. Fully deterministic — no model involved. "
        "It records pass/fail per ticker with the observed values, and hands its "
        "top picks to Thesis.")),
    "thesis": ("/thesis", "Thesis (stage 2)", (
        "Thesis writes one Completed Thesis per screener candidate: one deep "
        "model call grounded ONLY in the retained evidence packet (financial "
        "history, trends, peers, price context) plus deterministic valuation "
        "anchors it must reconcile with. When web search is enabled, recent web "
        "context is added as supplementary signal — cited [Wn], never a source "
        "of figures. Outputs that fail validation become rejected provenance, "
        "never artifacts.")),
    "ic_review": ("/ic-review", "IC review (stage 3)", (
        "IC review is the gate. Hard hurdles are deterministic (e.g. expected "
        "return above the hurdle); the model scores conviction, constitution "
        "fit, and data quality, and the gate score combines them. Sparse "
        "evidence (missing peers/ownership) lowers data quality and can fail a "
        "candidate — by design, thin data is not conviction. You can override "
        "any verdict either way; overrides are recorded as your decision.")),
    "memo": ("/memo", "Memo (stage 4)", (
        "Memo is the deep-research stage: a seven-section institutional memo "
        "per IC selection, every subsection citing figures from the evidence "
        "packet. It augments SEC data with recent context — filings since the "
        "last annual report (8-K/10-Q, from the local index or live EDGAR), "
        "known events, recent price action, and web search when enabled (cited "
        "[Wn]). Each memo ends with a machine-checkable monitoring plan that "
        "becomes the position's thesis-health source.")),
    "thesis_health": ("/portfolio", "Thesis health monitoring", (
        "Thesis health re-checks each held position's memo monitoring plan "
        "deterministically: every watch item stores the HEALTHY condition (e.g. "
        "revenue_growth >= 0) and is re-evaluated when new data lands via the "
        "daily sync. Breaches must confirm across consecutive periods before a "
        "status flips to broken — no model re-judges health. Ask 'why did X's "
        "thesis health break' for the exact watch items and values.")),
    "markets": ("/markets", "Markets & thematic research", (
        "Markets covers industry dashboards (deterministic aggregates over "
        "retained data), peer research runs, and Thematic Deep Research: name a "
        "theme and FundOps discovers companies via EDGAR full-text (including "
        "outside your universe), reads each one's 10-K Business/Risk/MD&A, and "
        "writes a cited market report — SEC filings carry every figure; web "
        "context is supplementary [Wn]. The 'Preview filings' button is just "
        "the raw discovery step.")),
    "portfolio": ("/portfolio", "Portfolio", (
        "The portfolio is a local ledger of your recorded lots and sales — "
        "FundOps never executes trades. It computes value series, "
        "flow-adjusted returns vs benchmarks, contribution, exposure "
        "concentration, drawdown/volatility, decision attribution, and factor "
        "tilts, all from local data.")),
    "library": ("/library", "Library", (
        "The Library is the archive: company dossiers, every retained artifact "
        "(theses, IC verdicts, memos, research notes), past conversations, and "
        "what the assistant remembers about you (with the ability to forget). "
        "Artifacts are read-only historical records; open one and select any "
        "passage to ask about it.")),
    "constitution": ("/", "Constitution & strategy", (
        "The Constitution is your investment strategy as versioned, wired "
        "settings — screener criteria, hurdles, emphasis. You change it in "
        "conversation: describe intent, get a draft, approve it; every change "
        "is a recorded proposal with provenance. Accepted learning "
        "recommendations also arrive here as proposals — nothing self-amends.")),
    "settings": ("/settings", "Settings, AI providers & web search", (
        "Settings is operational only: market-data sync, AI provider (any "
        "OpenAI-compatible API — OpenAI, Anthropic, Gemini, OpenRouter, Groq, "
        "local Ollama — or your coding agent in headless mode), editable model "
        "ids, API keys stored in a local credentials file (never the workspace "
        "or its export), web-search augmentation with optional Tavily/Brave "
        "key, schedules, exports, and the danger zone. Strategy never lives "
        "here.")),
    "data": ("/settings", "Data sources & provenance", (
        "All data is free and local-first: SEC bulk companyfacts + filings "
        "index, daily EDGAR ticks, yfinance prices (5y daily bars), FRED macro "
        "(keyless), EDGAR full-text search. Derived metrics are computed "
        "locally; every model call and tool read is recorded as provenance; "
        "artifacts carry frozen evidence bundles. Web results are context only "
        "— figures always trace to filings.")),
}

_SHAPE = '{"answer": "2-5 sentence answer", "topic": "one topic id from the guide"}'

_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "home": ("home", "briefing", "now panel"),
    "inbox": ("inbox", "triage", "needs decision", "attention"),
    "runs": ("pipeline", "runs page", "full pipeline", "stage map", "run the"),
    "screener": ("screener", "screen stage", "universe"),
    "thesis": ("thesis stage", "thesis work", "theses", "completed thesis", "fair value"),
    "ic_review": ("ic review", "ic stage", "gate", "verdict", "hurdle", "conviction",
                  "data quality", "pass or fail"),
    "memo": ("memo", "memos", "monitoring plan", "deep research stage"),
    "thesis_health": ("thesis health", "health check", "watch item", "monitor",
                      "broken", "intact"),
    "markets": ("markets page", "thematic", "industry dashboard", "research hub",
                "deep research", "edgar search", "filing search"),
    "portfolio": ("portfolio", "ledger", "lots", "benchmark", "attribution",
                  "exposure", "drawdown"),
    "library": ("library", "archive page", "dossier", "artifact reader",
                "conversations", "memory"),
    "constitution": ("constitution", "strategy settings", "wired", "proposal",
                     "criteria", "versioned"),
    "settings": ("settings", "provider", "api key", "model", "web search",
                 "schedule", "sync", "ollama", "claude code", "export"),
    "data": ("data source", "where does the data", "provenance", "sec data",
             "fred", "yfinance", "free data"),
}


def match_topic(message: str) -> str | None:
    """Deterministic topic lookup for the stub path (longest hint wins)."""
    msg = message.lower()
    best: tuple[int, str] | None = None
    for topic, hints in _TOPIC_HINTS.items():
        for h in hints:
            if h in msg and (best is None or len(h) > best[0]):
                best = (len(h), topic)
    return best[1] if best else None


def guide_text() -> str:
    return "\n\n".join(
        f"[{tid}] {title} (page: {route})\n{desc}"
        for tid, (route, title, desc) in GUIDE.items()
    )


async def answer(stores, message: str) -> dict:
    """One fast, bounded call grounded in the guide; the stub answers from the
    matched section verbatim. Returns {reply, actions} — actions open the page."""
    fallback = match_topic(message) or "runs"
    route, title, desc = GUIDE[fallback]
    stub = {"answer": f"{title}: {desc}", "topic": fallback}
    result = await get_ai().complete_json(
        "product_guide",
        "You explain how FundOps works, using ONLY the product guide below — "
        "never invent features or behavior. Answer the user's question in 2-5 "
        "plain sentences, honest about what is deterministic vs model-written. "
        "Set topic to the single most relevant guide id.\n\n" + guide_text(),
        f"Question: {message}",
        _SHAPE, tier="fast", stub=stub,
    )
    if not isinstance(result, dict) or not str(result.get("answer") or "").strip():
        result = stub
    topic = str(result.get("topic") or fallback)
    route, title, _ = GUIDE.get(topic, GUIDE[fallback])
    return {
        "reply": str(result["answer"]),
        "actions": [{"type": "navigate", "label": f"Open {title.split(' (')[0]}",
                     "route": route}],
    }
