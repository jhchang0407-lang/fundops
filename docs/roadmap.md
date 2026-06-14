# FundOps Product Roadmap — "a Bloomberg terminal for retail"

Status: Phases 1–4 shipped in baseline form (June 2026) — see the ✅ markers
per phase; remaining depth is noted inline. This document is the product
direction; implementation truth stays in
[implementation-map.md](implementation-map.md) and [adr/](adr/).

**AI-first redesign shipped (June 2026).** The app now lives in the
light-first elevation design language (canvas → panel → well tokens in
`frontend/src/styles/design-system.css`, warm dark variant via
`html[data-theme="dark"]`), with a new IA: **Home** (cited deterministic
briefing + the one conversation inline + Now rail), **Inbox** (triage only —
decisions, portfolio review, attention, activity), **Runs** (pipeline as a
durable object: live stage map over the four workbenches + recent-runs
provenance table), **Markets** (the research hub), **Portfolio** (analytics
plus a composed plain-language "read" card), **Library** (dossiers +
conversation threads + readable/forgettable assistant memory). The
conversation follows you: a docked companion panel on every non-Home surface
(same thread/session), point-at-anything popovers on instrumented numbers
(company KPIs, portfolio read/exposure) that route object-born questions to
the real local-data analyst, and a ⌘K palette (navigate, run, sync, export,
or free-text → conversation).
Conversations and strategy memory are first-class API objects
(`GET /chat/threads`, `GET /chat/memory`, `POST /chat/memory/{id}/forget` —
append-only forget). Company Page keeps its tab layout for now (one-scroll
conversion deferred; all capabilities intact and instrumented).

## Constraints (chosen deliberately)

- **Free data sources only.** SEC EDGAR, yfinance, FRED, free feeds. Anyone
  can run FundOps with zero data cost; index/ETF prices are allowed purely as
  benchmark/context, not as a universe expansion.
- **US equities only** for research depth — SEC data is rich and free there.
- **Local-first, owner-operated.** No cloud dependency for core workflows.

## Guiding thesis

The differentiator is not data breadth — Bloomberg wins that forever. It is
that **an AI analyst sits on top of a disciplined local research system the
user owns**: versioned strategy, evidence-bundled artifacts, deterministic
gates, and monitoring. Every roadmap phase should either make the chat
smarter or make what the chat can reference richer.

Sequencing: command center first (the differentiator), then the data context
that feeds it, then the analytics layer, then the deep-research harness and
reporting.

---

## Phase 1 — Chat as Command Center ✅ (shipped)

The chat is a tool-calling analyst over local data, not just strategy
drafting and archive retrieval.

- **Read-only tool loop** (`backend/chat/tools.py`, `backend/chat/analyst.py`):
  company financials, metric history, price history, side-by-side comparison,
  ad-hoc screens (never Constitution-mutating), portfolio summary, ownership,
  archive search. Provider-agnostic bounded loop over the existing AI gateway
  (OpenAI / agent CLI / offline stub), every tool call recorded as Execution
  Provenance (`kind="tool"`) under the chat session.
- **Inline result blocks**: tables and price charts render inside assistant
  replies and replay from retained history.
- **Ambient chat drawer** on every page with page context injected
  ("Viewing: NVDA" — "compare this with X" resolves against it); the drawer
  and `/chat` are one conversation.
- **Session anchor** (`GET /chat/session`) so a cold client resumes the
  latest conversation; **Strategy Preference Memory is read back** into
  drafting/exploration prompts instead of being write-only.

## Phase 2 — Market Context & Data Depth ✅ (shipped)

Make every surface information-dense. All free sources; mostly riding the
existing bulk-first ingestion patterns. Shipped: 5y universe bars + market
technicals in the metric catalog (`backend/services/ingest/price_metrics.py`),
benchmark series, events layer (`company_events` + merged Company Page Events
tab + Dashboard upcoming strip), peer comparison (route, tab, chat
`peers_of`), volume pane + indexed S&P overlay on the price chart, keyless
FRED macro cache (`backend/services/macro.py`, Dashboard strip, `get_macro`
tool), watchlists/themes (store, routes, Research Hub rail, `get_watchlist`
tool), the Research Hub surface (`/research`,
`backend/services/research_hub.py` — incl. P/E distribution + margin-trend
charts), and live company news (`backend/services/news.py`, Events tab —
explicitly shown-not-retained). Still open: candlesticks/sparklines beyond
the volume+overlay upgrade (parts of 4).

0. **Price-history depth & market-derived metrics** — the universe batch
   moves from 1y to 5y of daily bars (holdings already got 5y), and the
   stored OHLCV history starts earning its keep: momentum (1m/3m/6m/12m),
   distance below 52-week high, realized volatility, average dollar volume —
   computed locally from `price_history`, registered in the metric catalog so
   they are screenable/rankable/chat-queryable like any fundamental, and
   refreshed on every price sync tick.
1. **Events & calendar layer** — earnings dates (yfinance), filing events
   (already detected by the daily SEC index tick — surface them), insider
   transaction clusters, dividend/split dates. Events timeline on the Company
   Page + upcoming-events strip on the Dashboard.
2. **News** — yfinance company news + 8-K material-event extraction from the
   already-ingested filings index. Company Page section + chat-citable.
3. **Peer comparison** — peer groups from identity sector/industry data;
   comparison grid on the Company Page; `compare_companies` gains a
   "vs peers" mode.
4. **Charting upgrade** — candlestick/OHLC + volume, multi-ticker overlay
   (indexed to 100), metric sparklines in tables, price-vs-fundamental
   dual-axis. Recharts is already a dependency.
5. **Macro context** — FRED (free): rates, CPI, unemployment, yield curve.
   Dashboard macro strip + `get_macro(series)` chat tool.
6. **Watchlists** — lightweight ticker lists with snapshot metrics and
   thesis-health/coverage chips, distinct from the formal funnel.
7. **Index/benchmark prices** (^GSPC, ^RUT, sector ETFs) ingested as context
   series — prerequisite for Phase 3.
8. **Research Hub (new surface, v1: deterministic industry dashboards)** —
   a top-level page for industry/sector/thematic work: sector→industry
   browser; per-industry dashboards computed entirely from local data
   (median ROIC/margins/growth, valuation spread, market-cap breakdown,
   margin/growth trends vs the universe); constituents table ranked by any
   catalog metric with handoff to thesis; recent filings + insider activity
   per industry; user-defined peer groups/themes as saved objects. This
   surface is where Phase 4's AI research runs launch from.

## Phase 3 — Portfolio Analytics, Risk & the Learning Loop ✅ (shipped)

"Am I doing well, and why" — closes the audit's biggest gaps. Shipped:
`backend/services/portfolio_analytics.py` (ledger-replayed value series,
flow-adjusted TWR vs S&P 500, per-position contribution, sector exposure,
volatility/beta/correlation/drawdown) + the Portfolio Analytics section;
accepted learning recommendations now create real pending strategy proposals
(`dashboard_service._recommendation_to_proposal`) and Dashboard accepts
activate proposals for real; new filings for held tickers become dashboard
attention items on the daily tick; decision attribution (forward returns of
promote/dismiss selection events) and weighted factor tilts
(size/value/quality/momentum percentiles vs the universe) ship as Portfolio
Analytics cards. Phase 3 is complete.

1. **Benchmark comparison** — portfolio series vs S&P 500 / Russell 2000;
   time-weighted return; relative performance chart on the Portfolio page.
2. **Attribution layer** (currently zero code) — per-position contribution,
   sector contribution, and decision attribution (what promote/dismiss
   choices cost or earned — selection events are already recorded).
3. **Exposure & risk views** — sector/position concentration, drawdown,
   volatility/beta vs benchmark (computable from local price history),
   simple factor tilts from local metrics.
4. **Close the learning→Constitution loop** — accepted learning
   recommendations actually become strategy proposals (the payloads exist;
   the conversion in `dashboard_service.py` was never wired).
5. **Alerts as first-class** — thesis-health breaks, watch-item threshold
   crossings, filing events for holdings → an actionable inbox on the
   Dashboard's existing queue shape.

## Phase 4 — Research Harness & Reporting ✅ (baseline shipped)

Shipped: filing-text intake with cached section extraction
(`backend/services/ingest/filing_text.py`), company runs (risk-factor YoY
diff computed deterministically + cited MD&A note →
`filing_note` artifacts) and group runs (industry note, risk landscape →
`industry_note` artifacts) in `backend/workflows/research_runs.py`, launched
from the Research Hub and the Company Page Research tab; peer deep-dive runs
(Peers tab + Hub); thematic SEC full-text search via the keyless EFTS
endpoint (`backend/services/fulltext_search.py`, Research Hub search box —
live, shown-not-retained); CSV exports (portfolio, financials, screener,
industry, chat tables). Still open: PDF rendering (ADR-0056), transcript
intake.

1. **Filing-text research harness** — the killer free-data feature. SEC full
   text: ingest 10-K/10-Q sections on demand (Business, Risk Factors, MD&A),
   then risk-factor **diffs year-over-year**, cited MD&A summarization,
   segment extraction. Bounded multi-step runs where every claim cites the
   exact filing section — the deferred "online research evidence intake",
   scoped to SEC text.
2. **Industry/thematic research runs** — the AI layer of the Research Hub:
   industry notes (fan out across a peer set's filings), peer deep-dives,
   thematic filing search ("who mentions X" via SEC full-text search),
   risk-factor landscapes. Each run produces a cited, versioned artifact in
   the existing artifact/evidence-bundle machinery, archived in the Hub and
   citable from chat.
3. **Exports** — CSV for every table (screener, comparisons, portfolio,
   financials), PDF rendering for memos/audit packages (ADR-0056 gap), Excel
   portfolio export, chat "export this table".
4. **Earnings-transcript intake** — best-effort free sources / user-pasted
   transcripts → cited Q&A. Explicitly opportunistic.

## Deliberately not on the roadmap

- **Real-time quotes/streaming** — not free, not the edge; daily/delayed is
  right for a research terminal.
- **Trading/broker execution** — FundOps never delegates the decision;
  broker *sync* (import) may come later, execution never.
- **Paid data tiers, international, crypto** — outside current constraints.
- **13F institutional holdings** — blocked on CUSIP mapping; documented out
  of scope.

## Quick wins (any phase)

CSV download on existing tables; surface already-ingested filing events;
sortable table headers; labeled badges for the remaining chat modes.
