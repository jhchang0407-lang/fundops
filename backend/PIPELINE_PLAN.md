# FundOps Pipeline Architecture Plan

**Philosophy:** AI proposes, system validates and enforces. Never let AI outputs run unchecked.

**Status:** Living document. Last updated 2026-03-31. Reflects actual codebase state — read every file before editing this.

---

## Part 1: What Already Exists

This section is a precise inventory of working code. Build ON it, not around it. Before touching any of the files below, read them.

---

### 1.1 Data Connectors (`backend/connectors/`)

#### `backend/connectors/__init__.py` — COMPLETE, STABLE
- **What it does:** Defines abstract `DataConnector` base class and `ConnectorResult` dataclass
- **Exposes:** `DataConnector` (abstract), `ConnectorResult`, capability constants (quotes, financials, filings, estimates, profile, peers, key_metrics)
- **Status:** Stable interface. Do not modify. All connectors implement this.

#### `backend/connectors/fmp.py` — COMPLETE, WORKING
- **What it does:** Financial Modeling Prep API client. Rate-limited async HTTP with `httpx.AsyncClient`.
- **Exposes:** `FMPConnector` with methods: `get_quotes()`, `get_financials()`, `get_estimates()`, `get_profile()`, `get_peers()`, `get_key_metrics()`, `get_ratios()`, `get_bulk_quotes()`, `get_stock_screener()`
- **Depends on:** `httpx`, FMP API key from `config.py`
- **Rate limiting:** Configurable `requests_per_batch`, `delay_between_batches_s`
- **Health check:** Queries AAPL to validate connectivity
- **Status:** Complete. Do not rewrite. Only add methods if a new FMP endpoint is needed.

#### `backend/connectors/sec_edgar.py` — COMPLETE, WORKING
- **What it does:** SEC EDGAR connector. Uses free XBRL API. Dispatches to `backend/core/sec/` modules for parsing.
- **Exposes:** `SECEdgarConnector` with methods: `get_financials()`, `get_filings()`, `get_profile()`, `get_key_metrics()`, `get_segments()`, `get_ratios()`, `to_financial_data()`
- **Depends on:** `backend/core/sec/` (all modules), no API key
- **Key contract:** Returns `FinancialData` from `backend/core/financial_data.py`
- **Status:** Complete. `to_financial_data()` is the critical output — everything downstream reads this.

#### `backend/connectors/yfinance_connector.py` — COMPLETE, WORKING
- **What it does:** Free Yahoo Finance fallback for quotes and basic profiles. Async concurrent fetch (30 concurrent, 12s timeout per ticker).
- **Exposes:** `YFinanceConnector` with `get_quotes()`, `get_profile()`
- **Does NOT do:** Financials (delegates to SEC). Estimates. Peers.
- **Status:** Complete. Free default for users without FMP.

---

### 1.2 Core Infrastructure (`backend/core/`)

#### `backend/core/config.py` — COMPLETE, WORKING
- **What it does:** Loads `config/workflow.yaml` with `${ENV_VAR}` substitution. Manages all agent and connector configuration.
- **Exposes:** `FundOpsConfig` with: `get_connector_config(name)`, `get_agent_config(name)`, `get_agent_trigger(name)`, `get_all_agent_names()`, `get_strategy_presets()`, `from_wizard(wizard_data)`, `save_to_disk()`
- **Strategy presets:** value (20% base / 15% bear), growth (18% / 12%), dividend (10% / 6%)
- **Status:** Complete.

#### `backend/core/financial_data.py` — COMPLETE, STABLE
- **What it does:** Canonical data model. Every connector produces this. Every agent consumes it.
- **Exposes:** `CompanyProfile` (ticker, name, sector, industry, sic_code, fiscal_year_end, is_bank, is_insurance, is_reit), `FinancialData` (financials_annual, financials_quarterly, ratios, segments, filing_text, estimates, peers, sector_kpis, market_data, growth, key_metrics)
- **Critical rule:** Memo pipeline reads ONLY `FinancialData`. Never raw connector data.
- **Status:** Stable interface. Do not change field names — breaks all agents.

#### `backend/core/cache.py` — COMPLETE
- **What it does:** File-based JSON cache at `~/.cache/fundops/`.
- **Exposes:** `FileCache` with `get(key, max_age_hours)`, `set(key, data)`, `invalidate(key)`, `clear()`, `stats()`
- **Default TTL:** 12 hours
- **Status:** Complete.

#### `backend/core/llm.py` — COMPLETE, WORKING
- **What it does:** Shared LLM client with cost tracking per agent.
- **Exposes:** `LLMClient` with `generate(prompt, agent, reasoning_effort, search_context_size)`, `generate_with_search(...)`. `LLMResult` with `text, tokens_in, tokens_out, cost, duration_s, model, agent, cached`.
- **Supported models:** gpt-5-mini, gpt-4.1-mini, gpt-4.1, gpt-4o, gpt-4o-mini (OpenAI only — structured outputs required)
- **Helper:** `_sanitize_llm_output()` strips HTML tags from responses
- **Status:** Complete. Model selection comes from user config — pipeline is model-agnostic.

#### `backend/core/web_search.py` — COMPLETE
- **What it does:** Abstract web search provider + OpenAI Responses API implementation.
- **Exposes:** `WebSearchProvider` (abstract), `OpenAIWebSearch(llm_client, search_context_size)`, `NoOpWebSearch`
- **Status:** Complete.

#### `backend/core/quality_scores.py` — COMPLETE
- **What it does:** Deterministic quality metrics computed from raw SEC XBRL statements.
- **Exposes:** `piotroski_f_score(inc_current, inc_prior, bs_current, bs_prior, cf_current)` → 0-9, `altman_z_score(inc, bs)` → float
- **Inputs:** Raw statement dicts (not precomputed ratios from FMP)
- **Status:** Complete.

#### `backend/core/db.py` — COMPLETE (LEGACY LAYER)
- **What it does:** Core SQLite DB. WAL mode, foreign keys. Tables: tickers, agent_runs, portfolio_snapshots, watchlist, actions, documents, outcomes.
- **Exposes:** `FundOpsDB` with full CRUD for all tables. Ticker management, agent run logging, portfolio snapshots.
- **Status:** Complete. Legacy layer — new features go to `db_v2.py`.

#### `backend/core/db_v2.py` — COMPLETE, HEAVILY USED
- **What it does:** Extended SQLite schema for constitution, learning, and library. Shares same file as `db.py`.
- **Schema tables (all created on init):**
  - `constitution` — investor's living document (north_star, dimensions, ic_hurdles, anti_signals, must_have_signals, position_sizing, sell_discipline, autonomy_mode)
  - `constitution_changelog` — versioned evolution history with trigger tracking
  - `judgment_events` — unified event stream (every IC pass/fail, memo, override, etc.) with `parent_event_id` chain
  - `conversation_history` — persists strategy conversations across sessions (by constitution_id + session_id)
  - `library_entries` — research archive (ticker, entry_type, verdict, conviction, expected_return, discount_pct, sector, gross_margin, roic, revenue_growth, debt_equity, key_assumptions, judgment_event_id)
  - `refinement_proposals` — AI-proposed scoring code changes with status/response tracking
  - `strategy_profiles` — legacy (kept for backward compat, falls through to constitution)
  - `strategy_versions` — versioned scoring code + label maps
  - `screener_runs` — per-run results linked to strategy version
  - `feedback_records` — user feedback (promoted/dismissed) with score_at_feedback, rank_at_feedback
  - `outcome_snapshots` — periodic 90/180/365/730/1095d checks on screened stocks
- **Key methods:** `get_active_constitution()`, `update_constitution()` (bumps version, records changelog), `record_judgment_event()`, `get_event_chain()`, `store_library_entry()`, `find_similar()`, `store_proposal()`, `get_pending_proposals()`, `resolve_proposal()`, `get_proposal_stats()`, `save_conversation_message()`, `get_conversation_history()`, `get_due_checks()`, `record_outcome_snapshot()`
- **`find_similar()`:** SQL-based similarity (same sector ± GM ±10pp ± ROIC ±5pp). No vector embeddings.
- **Status:** Complete schema. Some query methods may need adding as features are built.

---

### 1.3 SEC Module (`backend/core/sec/`)

All files are COMPLETE and WORKING. Do not rebuild these.

| File | What it does | Key function |
|------|-------------|-------------|
| `client.py` | SEC EDGAR HTTP client, CIK mapping, rate limiting (100ms between requests) | `get_cik_map()`, `get_companyfacts()`, `get_submissions()` |
| `mapper.py` | XBRL tag → canonical field name mapping | Used internally by `statements.py` |
| `statements.py` | Extracts income statement, balance sheet, cash flow from XBRL | `extract_financials()` |
| `ratios.py` | Computes ROE, ROA, ROIC, margins, growth, FCF from raw statements | `calculate_ratios()` |
| `profile.py` | Company metadata from SEC submissions | `get_profile()` |
| `filings.py` | 10-K/10-Q section text via `edgartools` | `get_filing_text()` |
| `segments.py` | Revenue segments from XBRL instance docs | `get_segments()` |
| `sectors/__init__.py` | Auto-detects sector from SIC, dispatches to sector module | `get_sector_kpis(ticker, years, sector_override)` |

**Sector KPI modules** (`sectors/banks.py`, `insurance.py`, `reits.py`, `tech.py`, `retail.py`, `energy.py`, `healthcare.py`, `industrials.py`, `utilities.py`, `_utils.py`) — all complete.

---

### 1.4 Agents (`backend/agents/`)

#### `backend/agents/__init__.py` — COMPLETE
- **Exposes:** `AgentPlugin` (abstract with `run(context)`, `validate_config()`, `health_check()`), `AgentResult` (agent, ticker, status, event_type, data, errors, duration_s, timestamp), `OutcomeRecord`

#### `backend/agents/screener.py` — COMPLETE, WORKING
- **What it does:** Dual-lens screening. yfinance quick filter → SEC enrichment → dual lens scoring → analyst handoff.
- **Phase 1:** yfinance bulk quotes (~30s for 500 tickers)
- **Phase 2:** SEC EDGAR enrichment on survivors (~200 stocks)
- **Phase 3:** Dislocation lens (cheapness 70%, quality 15%, health 10%, growth 5%) + Compounder lens (quality 50%, cheapness 30%, growth_durability 20%)
- **Phase 4:** Builds analyst handoff (top candidates with return decomposition)
- **Output event:** "handoff" with `handoff_candidates` in `result.data`
- **Note:** All fundamentals from raw SEC XBRL — never precomputed FMP ratios.

#### `backend/agents/thesis.py` — COMPLETE, WORKING
- **What it does:** Quick thesis with return source decomposition + web research.
- **Steps:** Fetch data (SEC+FMP) → web research (GPT-5 mini, "Why cheap? Bull case?") → independent valuation → return decomposition (discount + growth + margin + dividends) → assemble thesis
- **Output:** `{ticker, fair_value, discount_pct, expected_return, conviction (LOW/MEDIUM/HIGH)}`
- **Constitution-aware:** Loads active constitution for context

#### `backend/agents/ic_review.py` — COMPLETE, WORKING
- **What it does:** IC stress-test. Applies 70% haircut on growth/margin sources for bear case. Checks growth-aware discount floors. AI IC review (style fit, conviction).
- **Hurdles:** base ≥20%, bear ≥15%
- **Growth-aware floors:** high-growth (15%+ rev, 60%+ GM) → 15% min discount; moderate (10%+ rev, 50%+ GM) → 20%; steady-state → 30%
- **Output events:** "pass" or "fail"

#### `backend/agents/memo.py` — COMPLETE, WORKING
- **What it does:** Full deep-dive analysis (~$1/run). Two modes: Research Report (13-section, no valuation) and Investment Memo (4-section buy thesis with valuation + return decomp).
- **Strategy-aware:** Adapts emphasis per constitution dimensions

#### `backend/agents/portfolio.py` — COMPLETE, WORKING
- **What it does:** Monitors held positions only. Loads positions from DB → fetches current prices → calculates P&L → checks thesis health (assumption breaches) → generates alerts.
- **Alerts:** Concentration overweight, drawdown, thesis breach
- **Output event:** "alert" or "complete"

#### `backend/agents/allocator.py` — COMPLETE, WORKING
- **What it does:** Position sizing for held positions. Classifies positions (tactical/core/legacy) → checks concentration → generates action recommendations (TRIM, EXIT, ADD_ON_WEAKNESS, HOLD).
- **Groups:** action_required (red), monitoring (amber), no_action (gray)

#### `backend/agents/library.py` — COMPLETE, WORKING
- **What it does:** Research archive with similarity retrieval. NOT a filing cabinet — it's a memory engine.
- **Modes:**
  - Mode 1: Ingest a specific artifact from context (thesis, ic_verdict, memo)
  - Mode 2: Ingest from judgment events not yet in library
  - Mode 3: Legacy scan of output directories
- **`find_similar()`:** Delegates to `ScreenerV2DB.find_similar()` — SQL-based, sector + GM ± ROIC matching
- **Auto-ingest:** Called after thesis/IC/memo completion via orchestrator

#### `backend/agents/outcome_checker.py` — PARTIALLY COMPLETE
- **What it does:** Grades screener results at 90/180/365/730/1095-day intervals.
- **What works:** Event structure, DB recording, yfinance price fetch, framework scaffolding
- **What's MISSING/TODO:**
  - Benchmark return (S&P 500) not actually fetched — hardcoded `None`
  - Thesis integrity check has `current: None` for all metrics — SEC data not refetched
  - `goal_alignment` is a stub: `{"assessed": False, "note": "Phase 3"}`
- **This is a priority gap** — see Part 4, Work Stream H

---

### 1.5 Scoring (`backend/scoring/`)

#### `backend/scoring/sandbox.py` — COMPLETE, WORKING
- **What it does:** AST validation + restricted execution environment for LLM-generated scoring code.
- **`validate_ast(code)`:** Blocks imports, exec, eval, compile, open, dunder attributes. Returns list of error strings.
- **`run_in_sandbox(code, stock_dict, timeout_s)`:** Executes in restricted globals: `{math, statistics, abs, max, min, round, len, sum, safe_get, clamp, normalize}`
- **`safe_get(stock, key, default=0.0)`:** Safe dict access for LLM-generated code
- **`clamp(value, low=0.0, high=10.0)`:** Range enforcer
- **`normalize(value, low, high)`:** Maps to [0, 10]
- **Note:** Not multi-tenant safe. Adequate for single-user environment.

#### `backend/scoring/codegen.py` — COMPLETE, WORKING (but has known problems)
- **What it does:** Generates scoring code from strategy profile via LLM. Includes `build_metric_schema()` (100+ metrics) and validation.
- **Known problem:** Directly asks LLM to write Python. LLM misspells field names, writes logically wrong code. The existing `validate_ast()` catches syntax, not semantics.
- **This is the problem the reliability pipeline (Part 3) fixes.**

#### `backend/scoring/strategy.py` — COMPLETE, WORKING
- **What it does:** Extracts investment philosophy via multi-turn AI conversation. Terminal-style (not chatbot). Quantifies dimensions to specific numbers.
- **Dimensions:** Dynamic — AI extracts whatever matters for this user's strategy.

---

### 1.6 Memo Pipeline (`backend/memo/`)

All files COMPLETE and WORKING.

| File | What it does |
|------|-------------|
| `data_fetcher.py` | `fetch_pipeline_data(ticker, fmp, sec, yfinance)` — parallel async fetch from all sources, merges to `FinancialData` |
| `quantitative.py` | Builds comprehensive financial fact sheet from pivoted data. Bank override. 15+ sections. |
| `transforms.py` | Transforms raw connector data to memo-ready format |
| `sanitize.py` | 100+ internal tag → display label mappings. Number formatting. Text sanitization. |
| `writers.py` | 3-stage async LLM writing pipeline (3A: research, 3B: body sections, 3C: synthesis). `_call_openai()`, `_is_reasoning_model()`. |
| `source_registry.py` | Registry of data source availability/quality |
| `market_research.py` | Web research integration |
| `valuation/dcf.py` | 2-stage DCF model |
| `valuation/bank_equity.py` | Bank-specific valuation |
| `valuation/ddm.py` | Dividend discount model |
| `valuation/nav.py` | NAV for REITs/insurance |
| `valuation/peer_multiples.py` | Comparable company analysis |
| `valuation/industry_config.py` | Sector-specific valuation approach selection |
| `valuation/__init__.py` | Valuation orchestrator |

---

### 1.7 Learning Infrastructure (`backend/learning/`)

**This entire directory is already built.** Do not treat as greenfield.

#### `backend/learning/__init__.py` — COMPLETE
- **Documents the 3-loop architecture:**
  - Loop 1 (Fast): User feedback on screener results → immediate pattern detection
  - Loop 2 (Medium): Behavioral calibration from IC decisions → Said vs Did
  - Loop 3 (Slow): Outcome reinforcement from 200+ resolved outcomes → activates after months

#### `backend/learning/feedback_loop.py` — COMPLETE, WORKING
- **Loop 1 — Preference Alignment**
- **`detect_patterns(db)`:** Analyzes `feedback_records` table. Clusters dismissals by reason, finds promotion patterns, detects high-score-dismissal mismatches. Threshold: 3+ matching feedback events.
- **`propose_refinement(llm, pattern, current_code, constitution)`:** Given a pattern, LLM proposes specific code change. Returns `{id, pattern, proposal, analysis, code_change, confidence, risk, evidence_summary}`.
- **`generate_refined_code(llm, current_code, proposal, strategy)`:** Generates complete updated scoring function, validates via `validate_ast()` + `compile_scoring_function()`.
- **What's missing:** This code is not yet wired to an API route or UI. Proposals are generated but there's no endpoint to surface them to the user or accept/reject them.

#### `backend/learning/behavioral.py` — COMPLETE, WORKING
- **Loop 2 — Said vs Did (Behavioral Calibration)**
- **`analyze_drift(db, constitution)`:** Queries `judgment_events` for ic_passed/ic_failed/ic_overridden. Checks must_have_signals, anti_signals, style_identity against actual approval patterns. Requires ≥5 decisions.
- **`propose_constitution_update(llm, drift, constitution)`:** LLM decides: "update constitution to match behavior" OR "tighten discipline to match constitution". Returns specific field changes.
- **What's missing:** Not wired to any API route or scheduled trigger. No UI surface for displaying drift or proposing updates.

---

### 1.8 API Routes (`backend/api/routes/`)

| File | Routes | Status |
|------|--------|--------|
| `agents.py` | Agent execution (screener, thesis, IC, library, portfolio, allocator) | Complete |
| `dashboard.py` | `GET /dashboard` — KPIs, funnel, activity, agent status | Complete |
| `screener_config.py` | Screener config CRUD, strategy wizard | Complete |
| `strategy.py` | `POST /strategy/conversation` — multi-turn AI conversation for constitution setup | Complete |
| `portfolio_routes.py` | Portfolio CRUD, position sync, P&L | Complete |
| `config_routes.py` | Config CRUD, API key validation, preset management | Complete |
| `pipeline.py` | Full pipeline orchestration | Complete |

**Missing routes** (identified gaps):
- No route for `GET /learning/proposals` (pending refinement proposals)
- No route for `POST /learning/proposals/{id}/accept` or `/reject`
- No route for `GET /learning/drift` (behavioral calibration)
- No route for `GET /learning/outcomes` (outcome snapshot results)
- No route for `POST /library/similar` (find_similar for a ticker)

---

### 1.9 Frontend (`frontend/src/`)

All pages complete in terms of component structure. See DESIGN.md for full spec.

| Page | File | Status |
|------|------|--------|
| Dashboard/Mirror | `pages/Dashboard.tsx`, `pages/Mirror.tsx` | Complete |
| Screener | `pages/Screener.tsx` | Complete — supports streaming partial results, feedback (promote/dismiss) |
| Research | `pages/Research.tsx` | Complete — thesis/IC/approved tabs |
| Portfolio | `pages/Portfolio.tsx` | Complete |
| Allocator | `pages/Allocator.tsx` | Complete |
| Configure | `pages/Configure.tsx` | Complete — strategy conversation, autonomy mode |
| Library | `pages/Library.tsx` | Complete — master-detail |
| Settings | `pages/Settings.tsx` | Complete — data sources, AI model, schedules |
| Ticker Detail | `pages/TickerDetail.tsx` | Complete — pipeline timeline, IC verdict, "Ask AI" |

**Missing UI surfaces:**
- No Learning/Mirror page section that surfaces refinement proposals to the user
- No behavioral drift display in Mirror/Dashboard
- No outcome tracking visualization

---

### 1.10 Data Universes (`backend/data/universes/`)

| Universe | Tickers | Use |
|----------|---------|-----|
| `starter_30.txt` | 30 | Quick testing |
| `nasdaq100.txt` | 101 | Tech-heavy, fast |
| `us_largecap_200.txt` | 207 | Default |
| `sp500.txt` | ~503 | Comprehensive |

`__init__.py` exposes `load_preset(name)`, `load_custom(tickers_text)`, `list_presets()`.

---

## Part 2: The Learning Loop & Suggestion Engine

### What's Already Built

The learning infrastructure is more complete than it might appear. Here is the precise state:

**Database layer (db_v2.py)** — COMPLETE:
- `feedback_records` table captures every user promote/dismiss with score and rank at time of feedback
- `outcome_snapshots` table stores 90/180/365/730/1095d checks with return_pct, benchmark_return_pct, alpha_pct, thesis_integrity, goal_alignment
- `refinement_proposals` table stores AI-proposed scoring changes with status tracking (pending/accepted/rejected) and `applied_version_id`
- `library_entries` table with `find_similar()` SQL query (sector + GM ± ROIC matching)
- `judgment_events` with full event chain (parent_event_id) linking every decision to its ancestor

**Loop 1 — Preference Alignment (feedback_loop.py)** — ENGINE BUILT, NOT WIRED:
- `detect_patterns(db)` — works, reads feedback_records
- `propose_refinement(llm, pattern, current_code, constitution)` — works, generates proposals
- `generate_refined_code(llm, current_code, proposal, strategy)` — works, validates via sandbox
- **What's missing:** No API route to trigger loop 1, no route to surface pending proposals, no UI component for accept/reject

**Loop 2 — Behavioral Calibration (behavioral.py)** — ENGINE BUILT, NOT WIRED:
- `analyze_drift(db, constitution)` — works, reads judgment_events
- `propose_constitution_update(llm, drift, constitution)` — works, returns direction + specific field changes
- **What's missing:** No scheduled trigger, no API route, no UI surface

**Loop 3 — Outcome Reinforcement (outcome_checker.py)** — SCAFFOLDING ONLY:
- Framework exists, DB writes work
- Price fetch via yfinance works
- **Critical gaps:** benchmark return is `None` (not fetched), thesis integrity has all `current: None` (SEC data not re-fetched), goal_alignment is stub

**Library similarity** — ENGINE BUILT, NOT WIRED INTO AGENTS:
- `LibraryAgent.find_similar()` delegates to `ScreenerV2DB.find_similar()` — SQL works
- Thesis and IC Review agents don't currently call this — they could provide "similar names you've approved before" as context

### What's Missing

**M1 — API routes for learning surface** (Work Stream H1):
```
GET  /learning/proposals          # pending refinement proposals
POST /learning/proposals/{id}     # accept | reject
GET  /learning/drift              # latest behavioral calibration
GET  /learning/outcomes           # outcome snapshot results
POST /library/similar             # find_similar for a ticker
```

**M2 — Scheduled triggers for loops 1 and 2** (Work Stream H2):
- Loop 1 trigger: After every screener run + every N new feedback records
- Loop 2 trigger: Weekly, or after every IC decision batch

**M3 — Outcome Checker completion** (Work Stream H3):
- Fetch S&P 500 benchmark return for each check period (yfinance SPY)
- Re-fetch current SEC data for thesis integrity (calls `sec_edgar.get_financials()`)
- Implement `goal_alignment` check: compare actual return path vs constitution strategy

**M4 — Library → Agent integration** (Work Stream H4):
- Thesis agent: before writing thesis, call `library.find_similar()`, inject as context ("3 similar names you approved: X (PASS, 28% return), Y (PASS, 22%), Z (FAIL, too leveraged)")
- IC Review agent: same — "Here are your past decisions on comparable quality compounders"
- This closes the feedback loop: past decisions inform new ones

**M5 — Mirror page learning surface** (Work Stream H5):
- Display pending proposals in Mirror/Configure page
- Show behavioral drift analysis ("Said vs Did")
- Show outcome tracker heat map

### How the Learning Loop Works End-to-End

```
User dismisses stock from screener (reason: "too cyclical")
        │
        ▼
feedback_records: INSERT (run_id, ticker, "dismissed", "too cyclical", score=72, rank=3)
        │
        ▼ (triggered: after run, or after 3 new feedback records)
Loop 1: detect_patterns(db)
  → finds: "too_cyclical" dismissed 3 times (AAPL, XOM, CAT)
  → crosses MIN_PATTERN_THRESHOLD (3)
        │
        ▼
propose_refinement(llm, pattern, current_code, constitution)
  → LLM: "scoring overweights revenue growth without penalizing cyclicality.
          Add: score -= 2.0 if safe_get(stock, 'revenueGrowthVolatility', 0) > 0.3"
  → confidence: 0.72
        │
        ▼
store_proposal(db, ...)   → refinement_proposals: status="pending"
        │
        ▼
GET /learning/proposals → UI shows: "Pattern: 3 cyclical stocks dismissed (score 70-80).
                                      Proposal: Penalize revenue growth volatility.
                                      Code change: [diff view]. Accept / Reject"
        │
    ┌───┴──────────────────────┐
    │ accepted                 │ rejected
    ▼                          ▼
generate_refined_code()    resolve_proposal(status="rejected")
  → validate_ast()            → stored for future ML
  → compile check
  → create new strategy_version
  → update active_version_id
  → next screener run uses new code
```

```
Loop 2 — Weekly behavioral calibration:
  analyze_drift(db, constitution)
  → "Constitution says 'quality compounder' but 6/10 IC passes are cyclical re-ratings"
  → "Anti-signal 'D/E > 2x' triggered in 3 approved names"
        │
        ▼
  propose_constitution_update(llm, drift, constitution)
  → direction: "tighten_discipline"
  → proposal: "Your IC is approving cyclical names despite your stated compounder philosophy.
               Consider raising bear return hurdle from 15% to 18% for non-tech names."
  → specific_changes: {"ic_hurdles": {"bear_return_pct": 18}}
        │
        ▼
  GET /learning/drift → Mirror page shows drift analysis + proposed constitution update
  User accepts → update_constitution(id, ic_hurdles=...)
```

---

## Part 3: The Reliability Pipeline

Same core philosophy as the original plan, now scoped to what's actually missing vs what works.

### 3.1 What Already Works (Do Not Rebuild)

- **Sandbox execution:** `backend/scoring/sandbox.py` — `validate_ast()` + `run_in_sandbox()` — keep as-is
- **Constitution-to-agent flow:** `db_v2.get_active_constitution()` called by agents — works
- **Memo fact sheet:** `backend/memo/quantitative.py` — already builds structured fact sheet
- **LLM cost tracking:** `backend/core/llm.py` — already tracks per-agent cost
- **Correction loop sketch:** `backend/agents/thesis.py` already has retry logic, just not standardized

### 3.2 What Needs to Be Built: Metric Schema Registry

**File:** `backend/core/metric_schema.py` — **does not exist yet**

This is the single source of truth for every valid financial metric across all agents. Currently, `codegen.py` has a local `build_metric_schema()` function. This must be extracted and expanded.

```python
# backend/core/metric_schema.py
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class MetricDef:
    canonical_name: str
    display_name: str
    aliases: List[str]
    data_type: str           # float | int | string | bool | percent
    typical_range: Tuple     # (min, max) as stored value
    valid_operators: List[str]  # [">", "<", ">=", "<=", "==", "between"]
    source: str              # sec_xbrl | fmp_key_metrics | computed | yfinance
    sector_specific: bool = False
    sectors: List[str] = field(default_factory=list)  # only for sector_specific=True
    notes: str = ""

METRIC_SCHEMA: dict[str, MetricDef] = {
    "roic": MetricDef(...),
    "nim": MetricDef(..., sector_specific=True, sectors=["banking"]),
    # ... migrate from codegen.py:build_metric_schema()
    # ... add thesis metrics: fair_value, discount_pct, expected_return
    # ... add IC metrics: base_return, bear_return, discount_floor
    # ... add portfolio metrics: weight, pnl_pct, cost_basis
}

def resolve_alias(name: str) -> Optional[str]: ...
def get_metric(name: str) -> Optional[MetricDef]: ...
def metrics_for_source(source: str) -> List[str]: ...
def metrics_for_sector(sector: str) -> List[str]: ...
```

### 3.3 What Needs to Be Built: Intent Schema + Validation Layer

**File:** `backend/core/intent_schema.py` — **does not exist yet**
**File:** `backend/core/validation.py` — **does not exist yet**

The current `codegen.py` asks the LLM to write Python directly. This fails on:
- Field name hallucination (`return_on_invested_cap` vs `roic`)
- Logically wrong but syntactically valid code
- Values outside plausible range

**The fix — two-step code generation:**

Step 1: LLM translates strategy to Intent JSON (validated against metric_schema):
```json
{
  "rules": [
    {"field": "roic", "operator": ">", "value": 0.15, "weight": 2.0, "required": false},
    {"field": "revenueGrowth", "operator": ">", "value": 0.08, "weight": 1.5, "required": false}
  ],
  "logic": "all",
  "sort_by": {"field": "roic", "direction": "desc"}
}
```

Step 2: `validation.py:validate_intent(intent, metric_schema)` checks:
- Every `field` resolves via `resolve_alias()`
- Operator is in `metric.valid_operators`
- Value is in `metric.typical_range`

Step 3: `validation.py:generate_code_from_intent(intent, metric_schema)` generates code deterministically — no LLM:
```python
# rule: {"field": "roic", "operator": ">", "value": 0.15, "weight": 2.0}
score += 2.0 * (1.0 if safe_get(stock, "roic", 0) > 0.15 else 0.0)
```

Step 4: Sandbox execution (already exists in `sandbox.py`) — verify no runtime errors and non-degenerate score distribution.

**Correction loop:** On validation failure, targeted error back to LLM: `"Field 'return_on_invested_cap' not found. Did you mean 'roic'? Matching fields: ['roic', 'roe', 'roa']"`. Max 3 retries. After 3, surface raw errors to user.

### 3.4 What Needs to Be Built: Prose Fact-Check Layer

**Problem:** Agents write prose with hallucinated numbers. `backend/memo/quantitative.py` already builds a structured fact sheet. The missing piece is the post-generation number-extraction and cross-check.

**Add to `backend/memo/writers.py`:**

```python
def fact_check_section(section_text: str, fact_sheet: dict) -> list[str]:
    """Extract all numbers from prose, cross-check against fact_sheet within 5% tolerance."""
    # 1. Find all \d[\d,.]*%? patterns in prose
    # 2. For each number, find matching fact_sheet entry
    # 3. If outside 5% tolerance, return violation message
    # 4. Called per section before accepting output
```

```python
def cross_section_coherence_check(sections: dict[str, str]) -> list[str]:
    """Verify same metric has same value across all sections."""
    # Build number index per metric per section
    # Flag mismatches across sections
```

**This is ADDITIVE to existing writers.py — do not rewrite the whole file.**

### 3.5 What Already Handles Retries

- `backend/agents/thesis.py` has retry logic — standardize it
- `backend/memo/writers.py` has 3-stage pipeline — add fact-check calls after stage 3B and 3C

**The correction loop per section:**
1. Section generated by LLM
2. `fact_check_section()` runs — finds violations
3. If violations: targeted correction prompt, retry that section only (not full memo)
4. Max 3 retries per section
5. After 3: log as system issue, surface to user

---

### 3.6 What Needs to Be Built: Web Research Grounding Layer

**Problem:** The thesis and memo agents run web searches ("Why is PAYC cheap?", "Bull case?") and dump raw AI prose into the output with zero validation. The AI could be citing stale articles, writing about the wrong company, or stating numbers that contradict SEC filings sitting right next to them. The system has high-quality deterministic data (SEC XBRL, FMP) but never uses it to validate the AI's web research claims.

This is a different problem than C1 (prose fact-checking). C1 catches hallucinated numbers in LLM-written prose *after* generation. This layer validates the **web research inputs** *before* they flow into the thesis/memo — ensuring the AI's qualitative context is grounded in reality.

**Current state of web research (no grounding):**
```
Search query ("Why is PAYC cheap?")
        ↓
OpenAI web search (black box)
        ↓
Raw prose dumped into thesis.web_research / memo.market_intel
        ↓
No validation. No cross-check. No recency check.
```

**Target state (grounded):**
```
Financial data fetched (SEC + FMP) ──► build_fact_anchor()
        │                                      │
        │                    ┌─────────────────┘
        ↓                    ↓
Search query + fact anchor injected into prompt
        ↓
OpenAI web search
        ↓
ground_web_research()
  ├─ verify_entity() ─────── Is this about the right company?
  ├─ check_recency() ─────── Are sources from the last 12 months?
  ├─ extract_and_verify() ── Do numerical claims match SEC/FMP data?
  └─ detect_contradictions() Flag claims that conflict with hard data
        ↓
GroundedResearch (with confidence score, warnings, contradictions)
        ↓
Agent decides: use as-is / use with caveats / discard and re-search
```

**File:** `backend/core/web_grounding.py` — **does not exist yet**

#### 3.6.1 Data Structures

```python
# backend/core/web_grounding.py
from dataclasses import dataclass, field
from datetime import date

@dataclass
class DateReference:
    text: str               # "Q3 2024 earnings call"
    parsed_date: date       # 2024-10-15
    age_days: int           # days from today
    context: str            # surrounding sentence

@dataclass
class NumericalClaim:
    raw_text: str           # "revenue grew 15%"
    value: float            # 15.0
    unit: str               # "percent" | "dollars" | "billions" | "ratio" | "multiple"
    metric_hint: str        # "revenue_growth" (best-guess mapping to financial_data keys)
    context: str            # surrounding sentence

@dataclass
class ClaimVerification:
    claim: NumericalClaim
    matched_metric: str | None    # "revenue_growth" from financial_data
    actual_value: float | None    # 8.2
    deviation_pct: float | None   # 82.9% off
    status: str                   # "confirmed" | "contradicted" | "unmatched" | "stale"

@dataclass
class EntityCheck:
    ticker_found: bool
    company_name_found: bool
    confidence: float                 # 0.0-1.0
    wrong_entity_signals: list[str]   # ["mentions 'PayPal' but ticker is PAYC (Paycom)"]

@dataclass
class GroundedResearch:
    original_text: str
    entity_check: EntityCheck
    date_references: list[DateReference]
    recency_score: float              # 0.0-1.0 (1.0 = all sources < 3 months old)
    claims: list[ClaimVerification]
    contradictions: list[str]         # human-readable warnings
    confidence: float                 # overall 0.0-1.0
    warnings: list[str]              # issues to surface to agent/user
    grounded: bool                    # passes minimum thresholds
    fact_anchor_used: str             # the anchor block that was injected
```

#### 3.6.2 Pre-Search: Fact Anchor Injection

The key insight: don't just validate *after* the search — anchor the AI *before* it searches. Inject known deterministic facts into the search prompt so the AI has ground truth to reconcile against.

```python
def build_fact_anchor(financial_data: dict, ticker: str, company_name: str) -> str:
    """Build a deterministic fact block injected into web search prompts.

    Forces the AI to reconcile web findings against known hard data.
    Returns a text block like:

    VERIFIED FINANCIALS (SEC XBRL filings, as of FY2025):
    - Company: Paycom Software Inc (PAYC)
    - Revenue: $1.83B (YoY growth: 11.2%)
    - Gross margin: 83.4%
    - ROIC: 28.1%
    - D/E: 0.15
    - FCF yield: 4.2%
    - Current price: $198.50 (market cap: $11.2B)
    - Latest 10-K filed: 2025-02-15

    IMPORTANT: These numbers are from audited SEC filings.
    If your web sources cite different numbers, flag the discrepancy.
    Do not repeat these numbers as if you found them — focus on
    qualitative context, catalysts, and risks NOT in the filings.
    """
```

**Why this matters:** Without anchoring, the AI will frequently re-state financial metrics it found on random websites — which may be stale, wrong, or from a different fiscal period. With anchoring, the AI knows the system already has the hard data and focuses on what web research actually adds: catalysts, risks, sentiment, competitive dynamics, management commentary.

**Where to inject:** Both thesis (`_run_web_research`) and memo (`market_research.py`) search prompts get the fact anchor prepended. The existing prompts already say "be specific with dates and numbers" — the anchor gives the AI actual numbers to be specific *against*.

#### 3.6.3 Post-Search: Grounding Validation

**`verify_entity(text, ticker, company_name) → EntityCheck`**
- Check that `ticker` and/or `company_name` appear in the search results text
- Flag common confusion patterns: similar tickers (PYPL vs PAYC), parent/subsidiary confusion (Google vs Alphabet), old names (Facebook vs Meta)
- Confidence score: 1.0 if both ticker and name found, 0.7 if only one, 0.3 if neither, 0.0 if a *different* company name is dominant
- **Threshold:** confidence < 0.5 → discard results, re-search with more specific query

**`check_recency(text) → tuple[list[DateReference], float]`**
- Regex extraction of date patterns: "Q3 2024", "March 2025", "last quarter", "FY2025", "2024 annual report"
- Resolve relative dates ("last quarter") against current date
- Recency score: weighted average of date ages. Dates < 3 months = 1.0, 3-6 months = 0.7, 6-12 months = 0.4, >12 months = 0.1
- **Threshold:** recency_score < 0.3 → warning "web research may be stale — most sources are >12 months old"
- Also flag if zero dates found — means the AI wrote vague prose without temporal grounding

**`extract_numerical_claims(text) → list[NumericalClaim]`**
- Regex: `(\d[\d,.]*)\s*(%|percent|billion|million|x|times)` and common financial patterns
- Map to metric hints using keyword proximity: "revenue grew 15%" → metric_hint="revenue_growth", value=15.0, unit="percent"
- "trading at 12x earnings" → metric_hint="pe", value=12.0, unit="multiple"
- "margin expanded to 45%" → metric_hint="gross_margin" or "operating_margin", value=45.0, unit="percent"
- Does NOT need to be perfect — this is a best-effort extraction for cross-referencing

**`cross_reference_claims(claims, financial_data) → list[ClaimVerification]`**
- For each NumericalClaim, attempt to match `metric_hint` to a key in `financial_data`
- Metric hint → financial_data key mapping (hardcoded, not LLM):
  ```python
  METRIC_MAP = {
      "revenue_growth": ["revenue_growth", "revenueGrowth"],
      "gross_margin": ["gross_margin", "grossProfitMargin"],
      "operating_margin": ["operating_margin", "operatingProfitMargin"],
      "pe": ["pe", "priceEarningsRatio"],
      "roic": ["roic"],
      "roe": ["roe"],
      "debt_equity": ["debt_equity", "debtToEquity"],
      # ... ~20 common financial metrics
  }
  ```
- Unit normalization: if claim is "15%" and data is 0.15, normalize before comparison
- Tolerance: ±10% relative deviation for "confirmed", >10% for "contradicted"
  - Why 10% not 5%: web sources often use TTM vs annual, or different fiscal periods. 10% catches real errors without over-flagging period mismatches
- Unmatched claims (no metric found in financial_data) → status="unmatched", no penalty

**`detect_contradictions(claims, financial_data) → list[str]`**
- Builds human-readable contradiction warnings from "contradicted" claims
- Example: `"Web research claims revenue growth of 15%, but SEC filing shows 8.2% (83% deviation). The web source may be using a different time period or including acquisitions."`
- These warnings flow into the thesis/memo as caveats, NOT as hard blocks

#### 3.6.4 Top-Level Grounding Function

```python
async def ground_web_research(
    raw_text: str,
    financial_data: dict,
    ticker: str,
    company_name: str,
    fact_anchor: str = "",
) -> GroundedResearch:
    """Validate web research against deterministic financial data.

    Called after web search returns, before results are consumed by agents.

    Returns GroundedResearch with confidence score and warnings.
    Agent decides how to use results based on confidence:
      - confidence >= 0.7: use as-is
      - confidence 0.4-0.7: use with warnings injected
      - confidence < 0.4: discard, optionally re-search with tighter query
    """
    entity = verify_entity(raw_text, ticker, company_name)
    dates, recency = check_recency(raw_text)
    claims = extract_numerical_claims(raw_text)
    verified = cross_reference_claims(claims, financial_data)
    contradictions = detect_contradictions(verified, financial_data)

    # Overall confidence: weighted combination
    #   entity: 40% (wrong company = fatal)
    #   recency: 30% (stale data = misleading)
    #   claim accuracy: 30% (contradicted numbers = unreliable)
    contradicted_count = sum(1 for v in verified if v.status == "contradicted")
    confirmed_count = sum(1 for v in verified if v.status == "confirmed")
    total_matched = contradicted_count + confirmed_count
    claim_accuracy = confirmed_count / total_matched if total_matched > 0 else 0.5  # neutral if no claims to check

    confidence = (
        entity.confidence * 0.4
        + recency * 0.3
        + claim_accuracy * 0.3
    )

    warnings = []
    if entity.confidence < 0.5:
        warnings.append(f"Low entity confidence ({entity.confidence:.1f}) — results may be about wrong company")
    if recency < 0.3:
        warnings.append("Most web sources are >12 months old — research may be stale")
    if contradicted_count > 0:
        warnings.extend(contradictions)
    if len(dates) == 0:
        warnings.append("No dates found in web research — temporal grounding unclear")

    return GroundedResearch(
        original_text=raw_text,
        entity_check=entity,
        date_references=dates,
        recency_score=recency,
        claims=verified,
        contradictions=contradictions,
        confidence=confidence,
        warnings=warnings,
        grounded=confidence >= 0.4,
        fact_anchor_used=fact_anchor,
    )
```

#### 3.6.5 Agent Integration Points — Full Map

Web research is not just thesis and memo. Every agent that interprets qualitative market context needs grounding. Here is the complete map of which agents use (or should use) web research, and how grounding applies:

| Agent | Current Web Research | Should Have | Grounding Work Item |
|-------|---------------------|-------------|---------------------|
| **Thesis** | Yes — "why cheap?" + "bull case?" | Yes | C4 (pre+post grounding) |
| **Memo** | Yes — 3 parallel queries (opportunity, competitive, capital) | Yes | E4 (pre+post grounding) |
| **IC Review** | Indirect — consumes thesis `variant_view` (web research summary) | Indirect | Inherits from C4 (thesis grounding flows through) |
| **Portfolio** | **No** — only price P&L + static thresholds | **Yes** — thesis health needs event monitoring | F3 (NEW: add web research + grounding) |
| **Outcome Checker** | **No** — only price return + stub thesis integrity | **Yes** — needs narrative explaining WHY stock moved | B4 (NEW: add web research + grounding) |
| **Allocator** | No | No — works from portfolio output, pure math | N/A |
| **Library** | No | No — archive/retrieval engine | N/A |
| **Screener** | No | No — quantitative scoring from SEC/FMP | N/A |

**Thesis agent (`thesis.py:_run_web_research`):**
```python
# BEFORE (current):
discount_result = await self.web_search.search(
    query=f"Why is {company} ({ticker}) stock trading at a discount? ..."
)
results["why_cheap"] = discount_result.text  # raw, unvalidated

# AFTER (grounded):
fact_anchor = build_fact_anchor(data, ticker, company)
discount_result = await self.web_search.search(
    query=f"{fact_anchor}\n\nGiven the above verified data, research: Why is {company} ({ticker}) trading at a discount? ...",
)
grounded = await ground_web_research(
    discount_result.text, data, ticker, company, fact_anchor
)
results["why_cheap"] = grounded.original_text
results["why_cheap_grounding"] = {
    "confidence": grounded.confidence,
    "recency_score": grounded.recency_score,
    "contradictions": grounded.contradictions,
    "warnings": grounded.warnings,
    "entity_confidence": grounded.entity_check.confidence,
    "claims_confirmed": sum(1 for c in grounded.claims if c.status == "confirmed"),
    "claims_contradicted": sum(1 for c in grounded.claims if c.status == "contradicted"),
}
if not grounded.grounded:
    results["why_cheap_warning"] = "LOW CONFIDENCE — web research may be unreliable"
```

**Memo market research (`market_research.py:fetch_market_intelligence`):**
- Same pattern: inject fact anchor into all 3 search prompts
- Ground all 3 results independently
- Add `grounding` dict to output with per-query confidence
- If any query scores < 0.4, log warning but don't block memo (web research is supplementary)

**Portfolio agent (`portfolio.py`) — NEW web research usage:**

The portfolio agent currently monitors thesis health via static threshold checks. But real thesis health requires knowing if something *happened* — an earnings miss, a management departure, a regulatory action, a competitor move. These are qualitative events that SEC data won't catch until the next quarterly filing (30-90 day lag).

```python
# NEW in portfolio.py — thesis event monitoring for held positions
async def _check_thesis_events(self, ticker: str, thesis_assumptions: list[str],
                                financial_data: dict) -> dict:
    """Web research: has anything happened that challenges the thesis?

    This is NOT the same as the thesis agent's "why cheap?" research.
    This is held-position monitoring: checking for events that could
    break an EXISTING thesis, not evaluating a new opportunity.

    Examples:
    - "MSFT key assumption: Azure growth >25%. Check: any recent guidance?"
    - "MCD key assumption: same-store sales positive. Check: recent earnings?"
    """
    fact_anchor = build_fact_anchor(financial_data, ticker, company_name)

    # Build assumption-specific search queries
    queries = []
    for assumption in thesis_assumptions[:3]:  # Max 3 assumptions to check
        queries.append(
            f"{fact_anchor}\n\n"
            f"We hold {ticker} based on this thesis assumption: '{assumption}'. "
            f"Has anything in the last 3 months challenged or confirmed this assumption? "
            f"Focus on: earnings reports, management commentary, guidance changes, "
            f"regulatory actions, competitive developments. Be specific with dates."
        )

    # Run queries + ground each result
    results = []
    for query in queries:
        raw = await self.web_search.search(query, {"agent": "portfolio"})
        grounded = await ground_web_research(raw.text, financial_data, ticker, company_name, fact_anchor)
        results.append({
            "assumption": assumption,
            "finding": grounded.original_text,
            "confidence": grounded.confidence,
            "contradictions": grounded.contradictions,
            "status": "breach" if any("contradicted" in str(c) for c in grounded.contradictions) else "intact",
        })

    return {"thesis_events": results, "any_breach": any(r["status"] == "breach" for r in results)}
```

**Outcome checker (`outcome_checker.py`) — NEW web research usage:**

Currently records raw price return at 90/180/365d intervals. Doesn't know WHY the stock moved. This narrative is essential for Loop 3 learning — "did the thesis play out, or did something else drive returns?"

```python
# NEW in outcome_checker.py — narrative context for outcome grading
async def _research_outcome_narrative(self, ticker: str, company_name: str,
                                       screened_at: str, check_at: str,
                                       return_pct: float, original_thesis: dict,
                                       financial_data: dict) -> dict:
    """Research WHY a screened stock moved the way it did.

    This feeds Loop 3 learning with qualitative narrative:
    - Did the discount close as expected? (thesis worked)
    - Did growth accelerate? (compounder thesis confirmed)
    - Was there an acquisition/event? (unrelated to thesis)
    - Did the thesis break? (value trap, or wrong on growth)

    The narrative helps the system learn WHICH thesis patterns actually work,
    not just which stocks went up.
    """
    fact_anchor = build_fact_anchor(financial_data, ticker, company_name)

    original_return = original_thesis.get("expected_return", 0)
    original_discount = original_thesis.get("discount_pct", 0)

    query = (
        f"{fact_anchor}\n\n"
        f"We screened {company_name} ({ticker}) on {screened_at} when it had a "
        f"{original_discount:.0f}% discount to fair value and {original_return:.0f}% expected return. "
        f"Since then, the stock has returned {return_pct:+.1f}%. "
        f"Research: What drove this return? Did the discount close? Did growth accelerate or decelerate? "
        f"Were there any major events (earnings beats/misses, M&A, regulatory)? "
        f"Focus on the period from {screened_at} to {check_at}."
    )

    raw = await self.web_search.search(query, {"agent": "outcome_checker"})
    grounded = await ground_web_research(raw.text, financial_data, ticker, company_name, fact_anchor)

    # Classify the outcome narrative
    thesis_played_out = None  # True/False/None
    if grounded.grounded:
        # Simple heuristic: if the return sources match original thesis, thesis played out
        # This is rough — Loop 3 will get smarter over time
        if return_pct > 0 and original_return > 0:
            thesis_played_out = True
        elif return_pct < -10 and original_return > 15:
            thesis_played_out = False

    return {
        "narrative": grounded.original_text,
        "confidence": grounded.confidence,
        "thesis_played_out": thesis_played_out,
        "contradictions": grounded.contradictions,
        "warnings": grounded.warnings,
    }
```

#### 3.6.6 Re-Search Strategy

When grounding fails (confidence < 0.4), the agent can optionally re-search with a more targeted query:

```python
if not grounded.grounded:
    # Build more specific query based on failure reason
    if grounded.entity_check.confidence < 0.5:
        # Entity confusion — be more specific
        retry_query = f"Research {company_name} (NYSE: {ticker}, SIC: {sic_code}). Do NOT include results about {grounded.entity_check.wrong_entity_signals}. ..."
    elif grounded.recency_score < 0.3:
        # Stale results — force recency
        retry_query = f"Research ONLY developments from {current_year} for {company} ({ticker}). ..."

    retry_result = await self.web_search.search(retry_query, context)
    grounded_retry = await ground_web_research(retry_result.text, data, ticker, company, fact_anchor)

    # Use retry only if it's actually better
    if grounded_retry.confidence > grounded.confidence:
        grounded = grounded_retry
```

Max 1 retry. If retry also fails, use original results with warnings attached — don't block the pipeline.

#### 3.6.7 What This Does NOT Do

- **Does not replace web search.** Web research adds genuine value (catalysts, risks, sentiment, competitive intel) that SEC filings don't contain. The grounding layer validates, not eliminates.
- **Does not use AI for validation.** All grounding checks are deterministic (regex, string matching, arithmetic comparison). No LLM calls in the grounding layer — that would just add another hallucination surface.
- **Does not block on warnings.** A low-confidence grounding score generates warnings, not hard failures. The thesis/memo can still use the research with caveats attached. The user sees the confidence score in the UI.
- **Does not validate qualitative claims.** "Management is bullish on AI adoption" cannot be fact-checked against SEC data. The grounding layer only validates quantifiable claims and temporal/entity accuracy.

---

## Part 4: Implementation Plan — Parallel Work Streams

### Dependency Map

```
Work Stream A (Foundation) ─────────────────────────────┐
        │                                                │
        ├──► Work Stream B (Screener Pipeline)           │
        │           │                                    │
        ├──► Work Stream C (Thesis + Valuation)          │
        │           │       ▲                            │
        │           │       │                            │
        │           │   A4 (Web Grounding) ──► C4, E4    │
        │           │                                    │
        ├──► Work Stream E (Memo)                        │
        │                                                │
        ├──► Work Stream H (Learning Loop) ◄─────────────┤
        │                                                │
        └──► [B + C complete] ──► Work Stream D (IC)     │
                                         │               │
                                         └──► Work Stream F (Portfolio)
                                                         │
                                                         └──► Work Stream G (Allocator)
```

**Note on A4:** Web Research Grounding (A4) has no dependency on A1/A2 (metric schema / intent). It depends only on `financial_data.py` (already exists) and `web_search.py` (already exists). A4 can run fully parallel with A1+A2. Its outputs feed C4 (thesis grounding) and E4 (memo grounding).

---

### Work Stream A: Foundation (Sequential — everything depends on this)

**A1 — Metric Schema Registry**
- **Build:** `backend/core/metric_schema.py`
- **What:** Extract `METRIC_DEFINITIONS` from `codegen.py:build_metric_schema()`, expand to full `MetricDef` dataclass schema. Add thesis/IC/portfolio metrics. Add `resolve_alias()`, `get_metric()`, `metrics_for_source()`, `metrics_for_sector()`.
- **Input dependencies:** Read `codegen.py` lines 22-100 for existing metric list. Read `agents.py` `_DISPLAY_TO_EXEC_KEY` for display-to-canonical mappings to absorb.
- **Output:** `METRIC_SCHEMA` dict + resolver functions. Consumed by A2, B1, C1, D1.
- **Complexity:** Medium
- **Parallel within A:** No — A2 depends on A1

**A2 — Intent Schema + Validation Layer**
- **Build:** `backend/core/intent_schema.py`, `backend/core/validation.py`
- **What:** `INTENT_SCHEMA` (JSON schema for AI output), `validate_intent(intent, metric_schema)`, `generate_code_from_intent(intent, metric_schema)`, `correction_message(field, metric_schema)`.
- **Input dependencies:** A1 (`metric_schema.py`)
- **Output:** Two functions used by B1, D1, H1. Replaces the LLM-generates-Python approach in `codegen.py`.
- **Complexity:** Medium
- **Parallel within A:** Must follow A1

**A3 — DB helper additions**
- **Modify:** `backend/core/db_v2.py`
- **What:** Add missing query methods needed by learning routes: `get_feedback_for_run(run_id)`, `get_runs_by_strategy(limit)`, `get_due_checks(intervals)` (verify this exists), `get_outcomes_for_run(run_id)`. Add `get_library_by_sector(sector, verdict, limit)` for suggestion engine.
- **Input dependencies:** Read existing `db_v2.py` to verify what's already there before adding.
- **Output:** Complete DB API consumed by H streams and API routes.
- **Complexity:** Small
- **Parallel within A:** Can run parallel with A1 and A2

**A4 — Web Research Grounding Layer**
- **Build:** `backend/core/web_grounding.py`
- **What:** Full grounding layer for AI web research (see Part 3, Section 3.6 for detailed spec). Two-pronged:
  1. **Pre-search anchoring:** `build_fact_anchor(financial_data, ticker, company_name)` — builds a verified-data block from SEC/FMP data and injects into search prompts. Forces the AI to focus on qualitative context (catalysts, risks, sentiment) instead of re-stating financial metrics it found on random websites.
  2. **Post-search validation:** `ground_web_research(raw_text, financial_data, ticker, company_name)` — deterministic checks (no LLM calls) that validate entity accuracy, temporal recency, and numerical claim cross-referencing against hard data.
- **Key functions:** `build_fact_anchor()`, `verify_entity()`, `check_recency()`, `extract_numerical_claims()`, `cross_reference_claims()`, `detect_contradictions()`, `ground_web_research()` (top-level orchestrator)
- **Data structures:** `GroundedResearch`, `ClaimVerification`, `EntityCheck`, `DateReference`, `NumericalClaim`
- **Input dependencies:** `financial_data.py` (already exists — the canonical data model), `web_search.py` (already exists — `SearchResult` interface)
- **Output:** `GroundedResearch` with confidence score (0-1), warnings, contradictions. Consumed by C4 (thesis) and E4 (memo).
- **Complexity:** Medium-Large (regex extraction, metric mapping, scoring logic)
- **Parallel within A:** Fully parallel with A1, A2, A3 — no shared dependencies

---

### Work Stream B: Screener Pipeline (starts after A1+A2)

**B1 — Screener code generation upgrade**
- **Modify:** `backend/scoring/codegen.py`
- **What:** Replace direct LLM Python generation with 2-step flow: (1) LLM → Intent JSON using `intent_schema.py`, (2) `validation.py:generate_code_from_intent()` generates Python deterministically. Keep sandbox validation from `sandbox.py`. Keep `build_metric_schema()` but make it delegate to `metric_schema.py`. Max 3 correction retries with targeted error messages.
- **Input dependencies:** A1 (metric_schema), A2 (validation)
- **Output:** More reliable scoring code generation. Same interface — `codegen.py` still produces `{code, label_map, version_id}`.
- **Complexity:** Medium
- **Parallel:** Can run after A completes, parallel with C and E

**B2 — Screener feedback wiring**
- **What:** After screener run completes, trigger Loop 1 pattern detection. If patterns found above threshold AND new proposals needed, generate and store proposals. Surface proposals count to dashboard.
- **Modify:** `backend/api/routes/agents.py` (screener route handler) + add call to `backend/learning/feedback_loop.py:detect_patterns()`
- **Input dependencies:** B1 (so screener is stable first), A3 (db methods)
- **Output:** `refinement_proposals` table populated automatically after screener runs
- **Complexity:** Small
- **Parallel:** Can run after B1

**B3 — Screener outcome checker completion**
- **Modify:** `backend/agents/outcome_checker.py`
- **What:**
  1. Fetch SPY return for benchmark: call `yfinance.get_quotes(["SPY"])` for the period between `screened_at` and `check_at`. Calculate benchmark return. Write into `outcome_snapshots.benchmark_return_pct`.
  2. Re-fetch current SEC data for thesis integrity: call `sec_edgar.get_financials(ticker)` for current year, compare gross_margin/roic/revenue_growth/debt_equity vs `original_data`. Score 0-100.
  3. Implement `goal_alignment`: load active constitution, check if the return path matches stated strategy (e.g., value constitution → discount closed, compounder constitution → growth maintained).
- **Input dependencies:** B1 (stable screener), existing connectors (sec_edgar, yfinance)
- **Output:** Real outcome data populates `outcome_snapshots`, feeds Loop 3 learning
- **Complexity:** Large
- **Parallel:** Can run parallel with B2

**B4 — Outcome checker narrative context**
- **Modify:** `backend/agents/outcome_checker.py`
- **What:** When grading a stock at 90/180/365d intervals, add web research to understand WHY the stock moved — not just how much. Currently, outcome_checker records raw price return and stub thesis integrity. Adding narrative context turns "MSFT returned +25% over 365d" into "MSFT returned +25% because Azure grew 30% and AI revenue exceeded expectations — thesis played out." This is critical for Loop 3 learning: the system needs to learn WHICH thesis patterns actually work, not just which stocks went up. See Section 3.6.5 for full spec.
- **New method:** `_research_outcome_narrative(ticker, company_name, screened_at, check_at, return_pct, original_thesis, financial_data)` — runs grounded web search explaining the return, classifies whether thesis played out.
- **New dependency:** Requires `web_search` and `sec` connectors added to `OutcomeChecker.__init__()` (currently only has `db`, `yfinance`).
- **Output schema addition:** `outcome_snapshots` records gain `narrative` (text), `narrative_confidence` (float), `thesis_played_out` (bool|null) fields. These feed into Loop 3 behavioral learning.
- **Cost management:** Outcome checks are periodic (90/180/365d), not daily. At scale with 200 screened stocks, a 90d batch might hit ~50 tickers × ~$0.03 = ~$1.50 per batch. Acceptable.
- **Input dependencies:** A4 (`web_grounding.py`), B3 (outcome checker completion — benchmark + SEC refresh must work first)
- **Output:** Outcome snapshots with qualitative narrative, thesis_played_out classification feeds Loop 3
- **Complexity:** Medium
- **Parallel:** After A4 + B3

---

### Work Stream C: Thesis + Valuation (starts after A, parallel with B)

**C1 — Prose fact-check layer**
- **Modify:** `backend/memo/writers.py` (additive only — do not rewrite)
- **What:** Add `fact_check_section(section_text, fact_sheet)` function. Add `cross_section_coherence_check(sections)`. Wire both into the existing 3-stage pipeline: call `fact_check_section` after each section in stage 3B/3C, retry that section with targeted correction prompt if violations found (max 3).
- **Input dependencies:** Read `writers.py` fully before editing. The fact sheet is already produced by `quantitative.py`.
- **Output:** Prose with numbers that match source data ±5%
- **Complexity:** Medium
- **Parallel:** Can run after A, parallel with B

**C2 — Library similarity context in Thesis**
- **Modify:** `backend/agents/thesis.py`
- **What:** Before assembling thesis, call `LibraryAgent.find_similar(ticker, sector, gross_margin, roic)`. Inject results as context into thesis prompt: "Similar names you've researched: X (PASS, 28% return, quality compounder), Y (FAIL, too leveraged)." This gives AI historical pattern context.
- **Input dependencies:** `library.py:find_similar()` (already works)
- **Output:** Thesis has richer historical context, more consistent with past IC decisions
- **Complexity:** Small
- **Parallel:** Can run parallel with C1

**C3 — Return source validation tightening**
- **Modify:** `backend/agents/thesis.py` (validation of return decomposition)
- **What:** After return decomposition is generated, validate that discount + growth + margin + dividend sources sum to stated expected_return ±2pp. If mismatch, correction loop. Verify each source against fact sheet data (discount_pct verified vs DCF output, growth vs SEC revenue CAGR).
- **Input dependencies:** A2 (validation patterns), C1 (fact-check approach)
- **Output:** Return decomposition that adds up and is grounded in data
- **Complexity:** Medium
- **Parallel:** Can run parallel with C1 and C2

**C4 — Thesis web research grounding**
- **Modify:** `backend/agents/thesis.py` (`_run_web_research` method)
- **What:** Wire the web grounding layer (A4) into thesis web research. Two changes:
  1. **Pre-search:** Call `build_fact_anchor(data, ticker, company_name)` and prepend to both search queries ("why cheap" and "bull case"). This anchors the AI against known SEC/FMP data and tells it to focus on qualitative context.
  2. **Post-search:** Call `ground_web_research()` on each search result. Store grounding metadata (`confidence`, `contradictions`, `warnings`, `recency_score`) in `thesis.web_research` alongside raw text. If confidence < 0.4, attempt one re-search with tighter query. If retry also fails, attach warnings but don't block thesis.
- **Also modify:** Thesis output structure — add `web_research.why_cheap_grounding` and `web_research.bull_case_grounding` dicts with confidence/warnings/contradictions so downstream agents (IC, memo) and the UI can display grounding quality.
- **Input dependencies:** A4 (`web_grounding.py`)
- **Output:** Thesis web research validated against deterministic data, with confidence scores visible in output
- **Complexity:** Small-Medium (mostly wiring — grounding logic is in A4)
- **Parallel:** Can run after A4, parallel with C1/C2/C3

---

### Work Stream D: IC Review (starts after B and C)

**D1 — IC scorecard signal validation**
- **Modify:** `backend/agents/ic_review.py`
- **What:** When evaluating must_have_signals from constitution, resolve each signal through `metric_schema.resolve_alias()` before checking. Currently signals are evaluated via string matching heuristics in `behavioral.py` — this is fragile. Replace with proper metric lookup. Record `scorecard_signals_met` and `scorecard_anti_triggered` counts in judgment_event data (these already exist as fields in behavioral.py's signal checker).
- **Input dependencies:** A1 (metric_schema), B and C complete (stable thesis to review)
- **Output:** IC review that properly checks constitution signals, reliable scorecard data in judgment_events
- **Complexity:** Medium
- **Parallel:** Must wait for B + C

**D2 — Library similarity context in IC**
- **Modify:** `backend/agents/ic_review.py`
- **What:** Same as C2 but for IC: inject `find_similar()` results as precedent context in AI IC review step. "Here's how you evaluated similar names: MSFT (PASS, high conviction, quality compounder), ORCL (FAIL, discount insufficient)."
- **Input dependencies:** D1
- **Output:** AI IC review has consistent precedent context
- **Complexity:** Small
- **Parallel:** Can run after D1

---

### Work Stream E: Memo (starts after A, partially parallel with B and C)

**E1 — Memo fact-check integration**
- **This is the same as C1** — `fact_check_section()` added to `writers.py` serves both thesis and memo pipelines. No separate work item needed if C1 is done.
- **Complexity:** Already covered by C1

**E2 — Memo → Library auto-ingest**
- **Verify:** `backend/agents/library.py:_ingest_artifact()` is already called after memo completion via orchestrator. Verify this is actually wired in `backend/api/routes/agents.py` or `pipeline.py` — if not, wire it.
- **What:** Ensure that after every memo generation, `LibraryAgent.run({ticker, artifact_type: "memo", data: {...}})` is called automatically.
- **Complexity:** Small (probably already done — verify first)

**E3 — Memo constitution lens directives**
- **Modify:** `backend/agents/memo.py`
- **What:** When writing memo, inject constitution `dimensions` into section-specific prompts. If constitution has `{"value_creation": "moat quality and reinvestment rate > FCF yield"}`, the business quality section prompt includes this directive. Currently memo is strategy-aware in general but not dimension-specific.
- **Input dependencies:** Constitution from D (IC has run, constitution is settled)
- **Complexity:** Medium
- **Parallel:** Can start after A, can be parallel with B and C

**E4 — Memo web research grounding**
- **Modify:** `backend/memo/market_research.py` (`fetch_market_intelligence` function)
- **What:** Wire grounding layer (A4) into all 3 parallel memo web searches (opportunity/risk, competitive/products, capital/analyst). Same two-pronged approach as C4:
  1. **Pre-search:** Build fact anchor from `FinancialData` (memo pipeline already has this via `data_fetcher.py`). Prepend to all 3 search prompts.
  2. **Post-search:** Ground all 3 results independently. Add per-query `grounding` dict to output: `{confidence, recency_score, contradictions, warnings, claims_confirmed, claims_contradicted}`.
- **Behavior on low confidence:** Log warning but don't block memo — web research is supplementary context for memos, not the core analysis. Attach warnings to the market_intel section so the memo writer LLM sees them and can add caveats in prose.
- **Also modify:** `market_research.py` return structure — add `grounding_summary` with aggregate confidence across all 3 queries, plus a `stale_warning` boolean if recency_score < 0.3 on any query.
- **Input dependencies:** A4 (`web_grounding.py`), `data_fetcher.py` (already exists — provides `FinancialData` to memo pipeline)
- **Output:** Memo market intelligence with grounding metadata, warnings surfaced to writer LLM
- **Complexity:** Small-Medium (same pattern as C4, applied to 3 parallel queries)
- **Parallel:** Can run after A4, parallel with E1/E2/E3

---

### Work Stream F: Portfolio Monitor (depends on D)

**F1 — Thesis health assumption refresh**
- **Modify:** `backend/agents/portfolio.py`
- **What:** When checking thesis health, currently assumptions are static strings. Connect to SEC data: for each assumption (e.g., "gross margin maintained above 60%"), re-fetch latest SEC quarterly data and evaluate. Flag `status: "breach"` with actual current value vs threshold.
- **Input dependencies:** D (IC review must have stored key_assumptions in judgment_events), existing `sec_edgar` connector
- **Output:** Real-time thesis health checks grounded in current SEC data
- **Complexity:** Large

**F2 — Portfolio → Learning feedback**
- **Modify:** `backend/agents/portfolio.py`
- **What:** When a position is exited (user marks exit), record judgment_event `position_exited` with return_pct, hold_duration, thesis_integrity_at_exit. This feeds Loop 3 (outcome reinforcement) with real trade data vs screener data.
- **Input dependencies:** F1 (stable portfolio monitor)
- **Output:** Actual trade outcomes in judgment_events, eventually feeds Loop 3
- **Complexity:** Small

**F3 — Portfolio thesis health web monitoring**
- **Modify:** `backend/agents/portfolio.py`
- **What:** Add web research for held positions to detect thesis-relevant events that SEC data won't catch for 30-90 days. For each held position with `key_assumptions` (from IC verdict), run targeted web searches checking if anything recent challenges or confirms each assumption. Uses the grounding layer (A4) for pre-search anchoring and post-search validation. See Section 3.6.5 for full spec.
- **New method:** `_check_thesis_events(ticker, thesis_assumptions, financial_data)` — runs up to 3 assumption-specific queries per held position, returns per-assumption status ("intact" / "breach" / "unconfirmed").
- **New dependency:** Requires `web_search` and `sec` connectors added to `PortfolioAgent.__init__()` (currently only has `fmp`, `yfinance`, `db`).
- **Alert integration:** If any assumption returns "breach" status, generate a `thesis_event_breach` alert (alongside existing concentration/drawdown alerts). This is a higher-signal alert than price-based drawdown — it means something fundamental changed.
- **Cost management:** Web research costs money. Only run thesis event checks on weekly cadence (`--weekly` flag), not daily. Daily runs stay price-only (cheap). Weekly runs add web research for all held positions (typically 5-15 names, ~$0.05-0.15 per run).
- **Input dependencies:** A4 (`web_grounding.py`), F1 (SEC thesis health checks), IC verdict data in judgment_events (provides `key_assumptions` list)
- **Output:** Portfolio alerts enriched with qualitative thesis event monitoring, not just price-based thresholds
- **Complexity:** Medium-Large
- **Parallel:** After A4 + F1

---

### Work Stream G: Allocator (depends on D + F)

**G1 — Constitution sell discipline integration**
- **Modify:** `backend/agents/allocator.py`
- **What:** Load constitution `sell_discipline` field. When generating TRIM/EXIT recommendations, explicitly check against stated sell rules (e.g., "thesis breach on two consecutive quarters", "position >20% of portfolio", "return vs fair value less than 10%"). Currently allocator uses hardcoded logic.
- **Input dependencies:** D (constitution settled with sell_discipline), F (portfolio health data)
- **Complexity:** Medium

**G2 — Scenario modeling accuracy**
- **Modify:** `backend/agents/allocator.py` (deep reasoning panels)
- **What:** "If trim vs If hold" scenarios currently use rough estimates. Connect to `valuation/` models: for each held position, run a quick DCF with current vs trimmed position, show expected return delta.
- **Input dependencies:** G1, `backend/memo/valuation/` models
- **Complexity:** Large

---

### Work Stream H: Learning Loop (starts after A, runs parallel with everything)

**H1 — Learning API routes**
- **Create:** `backend/api/routes/learning.py`
- **Routes:**
  ```
  GET  /learning/proposals          # get_pending_proposals() for active constitution
  POST /learning/proposals/{id}     # body: {"action": "accept"|"reject"}
                                    # accept: calls generate_refined_code(), creates strategy_version
                                    # reject: resolve_proposal(status="rejected")
  GET  /learning/drift              # analyze_drift(db, constitution) → drift report
  GET  /learning/outcomes           # recent outcome_snapshots with stats
  POST /library/similar             # body: {ticker, sector, gross_margin, roic, top_k}
  ```
- **Input dependencies:** A3 (db methods), existing `feedback_loop.py`, `behavioral.py`
- **Complexity:** Medium
- **Parallel:** Can run after A, parallel with all other streams

**H2 — Learning triggers**
- **Modify:** `backend/api/routes/agents.py` (screener completion handler)
- **What:** After screener run completes → call `detect_patterns(db)` async in background → if patterns found → call `propose_refinement()` for each → store proposals. Also: after every IC decision batch (>3 new decisions since last drift check) → schedule drift analysis.
- **Input dependencies:** H1 (routes built), `feedback_loop.py` (already exists)
- **Complexity:** Small
- **Parallel:** After H1

**H3 — Outcome checker completion**
- **This is the same as B3** (in B stream for sequencing clarity, but owned by H conceptually). Reference B3.

**H4 — Library → Agent integration**
- **This covers C2 and D2** — calling `find_similar()` in thesis and IC agents. Already referenced above.

**H5 — Mirror/Learning UI surface**
- **Modify:** `frontend/src/pages/Mirror.tsx` (or Dashboard)
- **Add:**
  - "Pending Proposals" card: lists refinement_proposals with `status=pending`. Each shows: pattern detected, proposed change, confidence, Accept/Reject buttons.
  - "Behavioral Drift" card: shows latest `analyze_drift()` output. "Said vs Did" — lists any signal violations or style drift.
  - "Outcome Tracker" card: shows outcome_snapshots for the last screener run. Return vs benchmark at 90d/180d.
- **Input dependencies:** H1 (routes), H2 (proposals being generated)
- **Complexity:** Medium

---

## Part 5: Model Strategy

### Model Selection
- **Source of truth:** User settings (already in `backend/api/routes/config_routes.py` + `Settings.tsx`)
- **Pipeline is model-agnostic:** `backend/core/llm.py:LLMClient` handles all models. No hardcoded model in agents — they pass `agent` name, config resolves to model.
- **Current supported models:** gpt-5-mini, gpt-4.1-mini, gpt-4.1, gpt-4o, gpt-4o-mini (OpenAI only — structured outputs required)

### Per-Step Model Assignment (config-driven, not hardcoded)

| Pipeline Step | Recommended Model | Reasoning | AI vs Deterministic |
|---------------|------------------|-----------|---------------------|
| Screener scoring | N/A (code runs in sandbox) | Code generated once, runs deterministic | Deterministic |
| Screener Intent JSON | gpt-4.1-mini or gpt-5-mini | Low-cost translation task with clear schema | AI (structured output) |
| Thesis web research | gpt-5-mini (high reasoning + search) | Needs reasoning about why cheap | AI + web |
| Thesis valuation | N/A (DCF/DDM are deterministic) | Math is deterministic | Deterministic |
| Thesis return decomp | gpt-4.1-mini | Structured JSON output | AI (structured output) |
| Thesis prose | gpt-4.1 or gpt-4o | Prose quality matters | AI |
| IC bear case haircuts | N/A (70% haircut is deterministic) | Rule-based | Deterministic |
| IC AI review | gpt-5-mini (high reasoning) | High-stakes quality gate | AI |
| Memo research sections | gpt-4.1 | Long context, quality prose | AI |
| Memo synthesis sections | gpt-4.1 or gpt-4o | Cross-section coherence | AI |
| Portfolio health check | N/A (SEC data comparison) | Deterministic threshold check | Deterministic |
| Allocator recommendations | gpt-4.1-mini | Structured JSON, constitution-aware | AI (structured output) |
| Feedback loop refinement | gpt-5-mini (high reasoning) | Needs to understand code + patterns | AI |
| Behavioral drift proposal | gpt-5-mini (high reasoning) | Nuanced behavioral analysis | AI |

### Correction Loop Cost Management
- **Cheaper models iterate more:** If using gpt-4.1-mini, allow 3 retries
- **Capable models iterate less:** If using gpt-4.1 or gpt-5, allow 2 retries (they get it right more often)
- **Model capability mapping** in `llm.py`: add `max_correction_retries` per model config

### Structured Outputs
All AI steps that produce JSON use OpenAI's structured output (JSON mode / function calling):
- Intent JSON (A2/B1): `response_format={"type": "json_object"}` with schema injected in system prompt
- Thesis return decomp: same
- IC verdict JSON: same
- Refinement proposals: same
- Behavioral drift direction: same

---

## Part 6: Testing Strategy

### Unit Tests (per work stream)

**Work Stream A tests** (`tests/core/`):
- `test_metric_schema.py`: `resolve_alias()` handles all aliases, `get_metric()` returns None for unknown fields, `metrics_for_sector("banking")` includes "nim" not "rule_of_40"
- `test_validation.py`: `validate_intent()` rejects unknown field names with correction message, rejects out-of-range values, rejects invalid operators; `generate_code_from_intent()` produces runnable Python for every valid operator type
- `test_db_v2_additions.py`: New query methods return correct results, `get_due_checks()` returns correct intervals

**Work Stream A4 tests** (`tests/core/`):
- `test_web_grounding.py`:
  - `test_build_fact_anchor`: Given financial_data with known values, output contains ticker, company name, revenue, margins, ROIC in human-readable format. Missing fields are omitted (not "None").
  - `test_verify_entity_correct`: Text containing "Paycom (PAYC)" scores confidence ≥ 0.9
  - `test_verify_entity_wrong`: Text about "PayPal (PYPL)" when ticker is "PAYC" scores confidence < 0.5 and populates `wrong_entity_signals`
  - `test_verify_entity_missing`: Text with no ticker or company name scores confidence 0.3
  - `test_check_recency_fresh`: Text with dates from last 3 months → recency_score ≥ 0.8
  - `test_check_recency_stale`: Text with dates from 18+ months ago → recency_score < 0.3
  - `test_check_recency_no_dates`: Text with no date references → recency_score 0.5 (neutral) + warning
  - `test_extract_numerical_claims`: "Revenue grew 15% to $1.8B with margins expanding to 45%" extracts 3 claims with correct values and units
  - `test_cross_reference_confirmed`: Claim "gross margin of 45%" vs financial_data `gross_margin: 0.452` → status "confirmed"
  - `test_cross_reference_contradicted`: Claim "revenue growth of 15%" vs financial_data `revenue_growth: 0.082` → status "contradicted" with deviation ~83%
  - `test_cross_reference_unit_normalization`: Claim "45%" correctly compared against 0.45 (not 45.0)
  - `test_ground_web_research_high_confidence`: Correct entity + recent dates + confirmed claims → confidence ≥ 0.7, grounded=True
  - `test_ground_web_research_low_confidence`: Wrong entity + stale dates → confidence < 0.4, grounded=False, warnings populated
  - `test_ground_web_research_mixed`: Correct entity + some contradictions → confidence 0.4-0.7, grounded=True with warnings

**Work Stream C4/E4/F3/B4 tests** (`tests/agents/`, `tests/memo/`):
- `test_thesis_grounding_integration`: Mock web search returns text with contradicted claim → thesis output contains `why_cheap_grounding.contradictions` list with specific warning
- `test_thesis_fact_anchor_injection`: Verify search query sent to web_search contains fact anchor block with SEC-derived numbers
- `test_memo_grounding_integration`: Mock web search with stale dates → market_intel output contains `grounding_summary.stale_warning = True`
- `test_grounding_no_block_on_low_confidence`: Even with confidence < 0.4, thesis/memo still produces output (grounding is advisory, not blocking)
- `test_portfolio_thesis_event_breach`: Mock web search returns news contradicting a key assumption → portfolio output contains `thesis_event_breach` alert with assumption text and finding
- `test_portfolio_thesis_event_intact`: Mock web search returns confirming news → no breach alert generated, assumption status = "intact"
- `test_portfolio_web_research_weekly_only`: Daily portfolio run does NOT call web_search; weekly run does
- `test_outcome_narrative_thesis_played_out`: Stock returned +25%, web research confirms thesis drivers → `thesis_played_out = True`
- `test_outcome_narrative_thesis_failed`: Stock returned -15%, web research shows thesis assumption broke → `thesis_played_out = False`
- `test_outcome_narrative_grounding`: Outcome checker narrative passes through grounding layer, contradictions flagged

**Work Stream B tests** (`tests/scoring/`, `tests/agents/`):
- `test_codegen_reliability.py`: 10 strategy descriptions → 10 intent JSONs → 10 generated codes → all pass `validate_ast()` → all produce non-degenerate scores on sample stocks
- `test_outcome_checker.py`: Benchmark return calculated correctly (mock yfinance SPY), thesis integrity score computed, goal_alignment returns non-stub

**Work Stream C tests** (`tests/memo/`):
- `test_fact_check.py`: Numbers extracted correctly from prose samples, 5% tolerance enforced, violations returned with specific message
- `test_cross_section.py`: Mismatched gross margin across sections detected and returns correctable error message
- `test_thesis_return_sources.py`: Return sources sum to stated expected_return ±2pp

**Work Stream D tests** (`tests/agents/`):
- `test_ic_signals.py`: `resolve_alias()` used for signal field names, scorecard_signals_met counts correctly, judgment_event records correct data

**Work Stream H tests** (`tests/learning/`):
- `test_detect_patterns.py`: 3 dismissals with same reason → pattern returned; 2 dismissals → no pattern; high-score dismissals detected
- `test_propose_refinement.py`: LLM call produces valid JSON, code_change is non-empty
- `test_analyze_drift.py`: With mock ic_passed events, signal violations detected correctly, approval profile built correctly, style drift detected when appropriate
- `test_learning_routes.py`: `GET /learning/proposals` returns pending list, `POST /learning/proposals/{id}` transitions status

### Integration Tests (`tests/integration/`)

**Screener integration:**
- Start to finish: `load_preset("starter_30")` → screener run → handoff produced with ≥1 candidate
- Feedback loop: 3 dismiss records inserted → `detect_patterns()` → proposal created

**Thesis integration:**
- `ThesisAgent.run({ticker: "MSFT"})` with mock SEC data → produces `{fair_value, expected_return, conviction}` → all numeric fields match fact sheet within 5%

**IC → Library integration:**
- IC pass → `LibraryAgent` auto-ingest triggered → `find_similar()` returns the ingested entry for similar sector/metrics

**Portfolio thesis health integration:**
- Weekly portfolio run with 3 held positions + mock web search → at least one `thesis_events` check per position → grounding applied to each
- Thesis event breach → generates alert alongside price-based alerts

**Outcome narrative integration:**
- Outcome checker grades ticker at 90d → web research fetched → narrative stored in `outcome_snapshots` → `thesis_played_out` is non-null
- Outcome with narrative feeds into Loop 3: `detect_patterns()` can now distinguish "stocks that went up because thesis worked" from "stocks that went up for unrelated reasons"

**Learning loop integration:**
- 5 IC passes in DB → `analyze_drift()` → returns non-empty analysis (not "need more data")
- Proposal accepted → `generate_refined_code()` → new strategy_version created → next screener run uses new version

### Regression Tests

**Canonical tickers:** Maintain a fixture set of 5 tickers with known SEC data snapshots (pre-fetched XBRL JSONs). All tests that would hit SEC run against these fixtures. Tests: MSFT (tech compounder), JPM (bank), O (REIT), XOM (energy), MCD (consumer/franchise).

**Score stability:** After B1 (codegen upgrade), run the same strategy description against the same fixture stocks. Scores must be within 10% of pre-upgrade scores for the same intended strategy. Regression alerts if score distribution changes dramatically.

**Return source math:** For all thesis tests, assert: `discount_return + growth_return + margin_return + dividend_return ≈ expected_return ±2pp`.

### Test Fixtures Needed

- `tests/fixtures/sec_xbrl/MSFT_companyfacts.json` — pre-fetched from SEC
- `tests/fixtures/sec_xbrl/JPM_companyfacts.json`
- `tests/fixtures/sec_xbrl/O_companyfacts.json`
- `tests/fixtures/sec_xbrl/XOM_companyfacts.json`
- `tests/fixtures/sec_xbrl/MCD_companyfacts.json`
- `tests/fixtures/sample_strategy.json` — constitution with known dimensions for codegen tests
- `tests/fixtures/sample_feedback.json` — 10 feedback records for pattern detection tests

---

## Appendix: File Reference Quick-Look

```
backend/
├── connectors/
│   ├── __init__.py          STABLE — DataConnector interface
│   ├── fmp.py               COMPLETE — FMP API, all market data
│   ├── sec_edgar.py         COMPLETE — SEC XBRL, primary fundamentals source
│   └── yfinance_connector.py COMPLETE — free quotes fallback
├── core/
│   ├── config.py            COMPLETE — workflow.yaml loader
│   ├── financial_data.py    STABLE — FinancialData canonical model
│   ├── cache.py             COMPLETE — file cache
│   ├── llm.py               COMPLETE — LLM client + cost tracking
│   ├── web_search.py        COMPLETE — OpenAI web search
│   ├── quality_scores.py    COMPLETE — Piotroski, Altman Z
│   ├── db.py                COMPLETE — legacy SQLite layer
│   ├── db_v2.py             COMPLETE — constitution, library, learning, outcomes
│   ├── metric_schema.py     MISSING — BUILD THIS FIRST (Work Stream A1)
│   ├── intent_schema.py     MISSING — BUILD SECOND (Work Stream A2)
│   ├── validation.py        MISSING — BUILD SECOND (Work Stream A2)
│   ├── web_grounding.py     MISSING — BUILD IN A4 (parallel with A1/A2)
│   └── sec/
│       ├── client.py        COMPLETE — SEC HTTP, CIK mapping
│       ├── mapper.py        COMPLETE — XBRL → canonical names
│       ├── statements.py    COMPLETE — income/balance/cashflow extraction
│       ├── ratios.py        COMPLETE — ratio computation
│       ├── profile.py       COMPLETE — company metadata
│       ├── filings.py       COMPLETE — 10-K/10-Q text
│       ├── segments.py      COMPLETE — revenue segments
│       └── sectors/         COMPLETE — all sector KPI modules
├── agents/
│   ├── __init__.py          COMPLETE — AgentPlugin, AgentResult
│   ├── screener.py          COMPLETE — dual lens, B1 upgrades codegen it uses
│   ├── thesis.py            COMPLETE — C2 adds library context, C3 validates return sources
│   ├── ic_review.py         COMPLETE — D1 fixes signal validation, D2 adds library context
│   ├── memo.py              COMPLETE — E3 adds dimension-specific directives
│   ├── portfolio.py         COMPLETE — F1 adds SEC health, F3 adds web research thesis events
│   ├── allocator.py         COMPLETE — G1 adds constitution sell discipline
│   ├── library.py           COMPLETE — already ingests, find_similar works
│   └── outcome_checker.py   SCAFFOLDING — B3/H3 completes it, B4 adds narrative web research
├── scoring/
│   ├── sandbox.py           COMPLETE — AST validation + restricted execution
│   ├── codegen.py           COMPLETE but brittle — B1 upgrades to intent-based approach
│   └── strategy.py          COMPLETE — conversation-based strategy extraction
├── memo/
│   ├── data_fetcher.py      COMPLETE — parallel async data fetch
│   ├── quantitative.py      COMPLETE — fact sheet builder
│   ├── transforms.py        COMPLETE
│   ├── sanitize.py          COMPLETE — 100+ tag → label mappings
│   ├── writers.py           COMPLETE — C1 adds fact-check layer (additive)
│   ├── source_registry.py   COMPLETE
│   ├── market_research.py   COMPLETE
│   └── valuation/           COMPLETE — DCF, bank equity, DDM, NAV, peers
├── learning/
│   ├── __init__.py          COMPLETE — documents 3-loop architecture
│   ├── feedback_loop.py     COMPLETE ENGINE — H1/H2 wire it to routes + triggers
│   └── behavioral.py        COMPLETE ENGINE — H1/H2 wire it to routes + triggers
└── api/routes/
    ├── agents.py            COMPLETE — H2 adds learning trigger hooks
    ├── dashboard.py         COMPLETE
    ├── screener_config.py   COMPLETE
    ├── strategy.py          COMPLETE
    ├── portfolio_routes.py  COMPLETE
    ├── config_routes.py     COMPLETE
    ├── pipeline.py          COMPLETE
    └── learning.py          MISSING — BUILD IN H1
```
