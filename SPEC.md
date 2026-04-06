# FundOps Functional Specification

> Every button, endpoint, and process documented. Use this to verify behavior and catch regressions.

---

## 1. Architecture Overview

```
Frontend (React 19 + Vite)     Backend (FastAPI + SQLite)
  Configure page ────────────►  /api/strategy/conversation
  Screener page  ────────────►  /api/screener/run, /results
  Research page  ────────────►  /api/thesis/:t, /api/ic-review/:t
  Portfolio page ────────────►  /api/portfolio/positions, /status
  Library page   ────────────►  /api/library/memos, /similar
  Allocator page ────────────►  /api/allocator/run, /recommendations
  Dashboard page ────────────►  /api/dashboard
  Mirror page    ────────────►  /api/strategy/mirror, /learning/*
  Settings page  ────────────►  /api/config/save, /test-connection
  TickerDetail   ────────────►  /api/ticker/:t, /review/:t
```

### Data Flow
```
User defines strategy (Configure/Mirror)
  → Constitution saved to DB
  → Scoring code generated (LLM)
  → Screener uses scoring code to rank stocks
  → Thesis agent researches top candidates
  → IC Review stress-tests return thesis
  → Memo generates full analysis (for PASS verdicts)
  → Library archives all research
  → Portfolio monitors held positions
  → Allocator sizes positions
  → Learning loops detect patterns and propose refinements
```

### External Dependencies
- **LLM**: OpenAI API (GPT models) — required for strategy conversation, thesis, IC review, memo, codegen
- **yfinance**: Price quotes (free, no key) — used by portfolio for P&L
- **FMP**: Financial data (paid, optional) — fallback for prices, estimates
- **SEC EDGAR**: Filing data (free) — used by thesis for fundamental data

---

## 2. Database Schema

### v1 Tables (backend/core/db.py)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| tickers | Stock universe metadata | ticker PK, company_name, sector, industry, is_owned |
| agent_runs | All agent execution records | id, ticker, agent, run_at, verdict, fair_value, full_output JSON |
| portfolio_snapshots | Daily portfolio state | snapshot_date UNIQUE, total_value, holdings JSON, daily_pnl |
| watchlist | Tracked tickers | ticker, status, entry_price, target_price |
| actions | User actions audit trail | ticker, action, acted_at, reason |
| documents | Research documents | ticker, doc_type, content |
| outcomes | Trade outcomes | ticker, action, shares, price, judge_verdict |

### v2 Tables (backend/core/db_v2.py)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| constitution | Master strategy object | id PK, name, version, north_star, dimensions JSON, ic_hurdles JSON, active_version_id |
| constitution_changelog | Version history | constitution_id FK, version_from, version_to, change_summary |
| judgment_events | Unified decision stream | event_type, ticker, agent, data JSON, parent_event_id FK |
| conversation_history | Strategy chat persistence | session_id, role, content, extracted JSON |
| library_entries | Research archive | ticker, entry_type, verdict, conviction, expected_return, sector, gross_margin, roic |
| refinement_proposals | AI-suggested scoring changes | pattern_type, proposal, code_change, status (pending/accepted/rejected) |
| strategy_profiles | Legacy strategy defs | id PK, name, dimensions JSON, active_version_id |
| strategy_versions | Scoring code versions | strategy_id FK, version_number, scoring_code, label_map JSON |
| screener_runs | AI-scored screener results | strategy_version_id, results JSON, scores JSON |
| feedback_records | User feedback on screener | screener_run_id, ticker, feedback_type |
| outcome_snapshots | Post-screen performance | ticker, price_at_screen, current_price, return_pct, benchmark_return |
| ticker_financials | Cached financial data | ticker, data JSON, source, fetched_at |

---

## 3. API Endpoint Reference

### Dashboard

| Method | Path | Response Keys | Side Effects |
|--------|------|---------------|--------------|
| GET | /api/dashboard | recent_runs, agent_run_counts, latest_portfolio, running_jobs, agent_status | None |

### Configuration

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/config | — | agents, connectors, system | None |
| POST | /api/config/save | {section, values} | {saved: true} | Writes to workflow.yaml or .env |
| POST | /api/config/test-connection | ?source=yfinance | {connected, source} | None |
| GET | /api/config/presets | — | {presets: [...]} | None |
| GET | /api/config/universes | — | {presets: [...]} | None |
| GET | /api/config/universe/:name | — | {tickers: [...]} | None |
| POST | /api/config/universe | {preset?, custom_tickers?} | {set: true} | Updates workflow.yaml |
| GET | /api/config/screener-filters | — | {filters, presets, active} | None |
| POST | /api/config/screener-filters | {filters, preset?} | {saved: true} | Updates workflow.yaml |
| POST | /api/config/clear-pipeline | {} | {cleared: true} | Deletes agent_runs, screener_runs, workflow_events |
| GET | /api/config/export | ?format=json | Full data export | None |

### Screener

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| POST | /api/screener/run | {} | {job_id} | Creates async job, agent_runs INSERT |
| GET | /api/screener/results | — | {results: [{ticker, score, expected_return, reason, ...}]} | None |
| GET | /api/screener/config | — | Screener config dict | None |
| POST | /api/screener/config | {criteria} | {saved: true} | Updates workflow.yaml |
| POST | /api/screener/v2/run | {strategy_id?} | {job_id} | Creates async job, screener_runs INSERT |
| GET | /api/screener/v2/results | — | {results, run_id, label_map, ...} | None |
| POST | /api/screener/v2/feedback | {screener_run_id, ticker, feedback, ...} | {recorded: true} | workflow_events INSERT |
| GET | /api/screener/v2/feedback/:runId | — | {feedbacks: [...]} | None |

**Feedback types**: `dismissed`, `thumbs_up`, `thumbs_down`, `promoted` (NOT `dismiss`)

### Thesis

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/thesis | — | {results: [...]} | None |
| POST | /api/thesis/:ticker | {} | {job_id} | Creates async job |
| POST | /api/thesis/batch | {tickers: [...]} | {job_id} | Creates async job (sequential) |
| GET | /api/thesis/:ticker | — | Latest thesis for ticker | None |

### IC Review

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/ic-review | — | {results: [...]} | None |
| POST | /api/ic-review/:ticker | {} | {job_id} | Creates async job |
| POST | /api/ic-review/batch | {tickers: [...]} | {job_id} | Sequential |
| GET | /api/ic-review/:ticker | — | Latest IC review | None |
| POST | /api/ic-review/:ticker/override | {note} | {overridden: true} | agent_runs UPDATE, workflow_events INSERT |

### Research

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/research/approved | — | {results: [...]} | None |
| POST | /api/research/dismiss/:ticker | {reason?} | {dismissed: true} | agent_runs UPDATE |
| POST | /api/research/promote/:ticker | {} | {promoted: true} | agent_runs UPDATE |
| POST | /api/research/report/:ticker | {} | {job_id} | Creates async job |
| POST | /api/research/memo/:ticker | {} | {job_id} | Creates async job |

### Portfolio

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/portfolio | — | {holdings: [...], id, snapshot_date, total_value, cash, daily_pnl} | None |
| POST | /api/portfolio/positions | {positions: [{ticker, shares, cost_basis, date?, type?}]} | {saved, holdings, total_value, total_pnl, removed_tickers?} | portfolio_snapshots UPSERT, tickers UPSERT |
| GET | /api/portfolio/status | — | Latest snapshot | None |
| GET | /api/portfolio/history | — | Last 30 snapshots | None |
| POST | /api/portfolio/run | {} | {job_id} | Creates async job |

**Position save flow**: Receives positions → fetches prices (yfinance, FMP fallback) → drops tickers with no price → computes P&L → saves snapshot

### Allocator

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| POST | /api/allocator/run | {} | {job_id} | Creates async job |
| GET | /api/allocator/recommendations | — | Recommendations dict/list | None |
| POST | /api/allocator/:ticker/discuss | {message, history, context} | {response} | None |
| POST | /api/allocator/:ticker/action | {action, reason?} | {recorded: true} | agent_runs INSERT |

### Pipeline

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| POST | /api/pipeline/run | {} | {job_id} | Creates async job (8-step pipeline) |
| GET | /api/pipeline/status | — | Latest pipeline status | None |
| GET | /api/pipeline/history | — | {history: [...]} | None |
| GET | /api/pipeline/pending | — | {pending: [...]} | None |
| POST | /api/pipeline/pending/:id/approve | {} | {approved: true} | pending_approvals UPDATE |
| POST | /api/pipeline/pending/:id/reject | ?reason= | {rejected: true} | pending_approvals UPDATE |

### Strategy

| Method | Path | Request Body | Response Keys | Side Effects |
|--------|------|-------------|---------------|--------------|
| GET | /api/strategy | — | Active strategy + constitution | None |
| GET | /api/strategy/list | — | {strategies: [...]} | None |
| POST | /api/strategy/conversation | {message, history, strategy_id?, session_id?} | {response, session_id, ...} | conversation_history INSERT |
| GET | /api/strategy/conversation/history | ?strategy_id=&session_id= | Conversation messages | None |
| POST | /api/strategy/save | {profile, name?} | {strategy_id, constitution_id} | constitution UPSERT, strategy_profiles UPSERT |
| GET | /api/strategy/:id/versions | — | {versions: [...]} | None |
| POST | /api/strategy/:id/regenerate | {} | {version_id} | strategy_versions INSERT |
| POST | /api/strategy/reset | {} | {reset: true} | Archives active constitution |

### Constitution

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/constitution | Active constitution object (or null) |
| GET | /api/constitution/changelog | {changelog: [...]} |

### Learning

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/learning/proposals | {proposals, detected_patterns, stats} |
| POST | /api/learning/proposals/:id | {action, reason?} → Accept/reject |
| GET | /api/learning/drift | {has_enough_data, signal_drift, anti_signal_violations, ...} |
| GET | /api/learning/outcomes | {outcomes: [...], stats} |

### Refinement Proposals

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/strategy/refinement-proposals | {proposals: [...]} |
| POST | /api/strategy/refinement-proposals/generate | Triggers proposal generation |
| POST | /api/strategy/refinement-proposals/:id/accept | Accepts + generates new version |
| POST | /api/strategy/refinement-proposals/:id/reject | Marks rejected |

### Mirror

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/strategy/mirror | Constitution + behavioral data |
| POST | /api/strategy/mirror/propose-update | Proposed changes |
| POST | /api/strategy/mirror/apply-update | {changes, proposal} → Applied |

### Jobs

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/jobs | {jobs: [...]} |
| GET | /api/jobs/:id | {id, agent, status, progress, error, ...} |
| POST | /api/jobs/:id/cancel | {cancelled: true} |

**Job statuses**: pending, running, complete, completed, failed, cancelled

### Ticker Detail

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/ticker/:ticker | Full ticker data (all agent runs, financials, holdings) |
| GET | /api/ticker/:ticker/timeline | {ticker, timeline: [...]} |
| GET | /api/review/:ticker | Aggregated thesis + IC + evidence |
| GET | /api/evidence/:ticker | {ticker, artifacts: [...]} |
| GET | /api/events/ticker/:ticker | {events: [...], ticker} |
| GET | /api/events/chain/:id | Event chain (parent-child) |
| GET | /api/events/recent | {events: [...]} |

### Library

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/library/memos | {memos: [...], total} |
| GET | /api/library/memos/:ticker | Memos for ticker |
| GET | /api/library/similar/:ticker | Similar research entries |
| GET | /api/library/ticker/:ticker | Library entries for ticker |
| GET | /api/library/stats | Library statistics |
| POST | /api/library/similar | {ticker, sector?, gross_margin?, roic?} → Similar entries |
| POST | /api/library/ask | {question, history} → RAG response |

### Memory

| Method | Path | Response Keys |
|--------|------|---------------|
| GET | /api/memory | List memory entries |
| GET | /api/memory/:id | Single entry |
| POST | /api/memory | {type, rule, why, how_to_apply} → Create |
| DELETE | /api/memory/:id | Delete entry |

---

## 4. Frontend Pages

### Configure (/)
- **On mount**: GET /api/strategy, GET /api/config
- **Chat input**: POST /api/strategy/conversation → displays AI response
- **Save Strategy button**: POST /api/strategy/save
- **Universe selector**: GET /api/config/universes, POST /api/config/universe

### Dashboard (/dashboard)
- **On mount**: GET /api/dashboard (30s refresh), GET /api/config, GET /api/portfolio (60s), GET /api/pipeline/pending (30s), GET /api/learning/proposals (120s), GET /api/learning/drift (120s), GET /api/learning/outcomes (120s)
- **Approve pending**: POST /api/pipeline/pending/:id/approve
- **Reject pending**: POST /api/pipeline/pending/:id/reject
- **Sidebar "Run Pipeline"**: POST /api/pipeline/run

### Screener (/screener)
- **On mount**: GET /api/screener/v2/results (or /screener/results), GET /api/strategy
- **Run button**: POST /api/screener/v2/run (or /screener/run) → stores job_id in sessionStorage
- **Promote button**: POST /api/research/promote/:ticker
- **Dismiss button**: Opens modal → POST /api/screener/v2/feedback with feedback="dismissed"
- **Row expand**: Shows thesis detail, return decomposition, key financials

### Research (/research)
Three tabs: Thesis | IC Review | Approved

**Thesis tab**:
- **On mount**: GET /api/thesis
- **Run Thesis**: POST /api/thesis/:ticker
- **Dismiss**: POST /api/research/dismiss/:ticker

**IC Review tab**:
- **On mount**: GET /api/ic-review
- **Run IC**: POST /api/ic-review/:ticker
- **Override**: POST /api/ic-review/:ticker/override with note
- **Dismiss**: POST /api/research/dismiss/:ticker

**Approved tab**:
- **On mount**: GET /api/research/approved
- **Generate Report**: POST /api/research/report/:ticker
- **Generate Memo**: POST /api/research/memo/:ticker

### Portfolio (/portfolio)
- **On mount**: GET /api/portfolio (60s refresh)
- **Save positions**: POST /api/portfolio/positions
- **Run portfolio**: POST /api/portfolio/run
- **Edit inline**: Modify shares/cost_basis per holding

### Library (/library)
- **On mount**: GET /api/library/stats, GET /api/library/memos
- **Search**: GET /api/library/memos?search=term
- **Ask tab**: POST /api/library/ask
- **Detail view**: GET /api/library/ticker/:ticker

### Allocator (/allocator)
- **On mount**: GET /api/allocator/recommendations, GET /api/portfolio
- **Run button**: POST /api/allocator/run
- **Execute action**: POST /api/allocator/:ticker/action
- **Discuss**: POST /api/allocator/:ticker/discuss

### Mirror (/mirror)
- **On mount**: GET /api/strategy/mirror, GET /api/learning/proposals, GET /api/learning/drift, GET /api/learning/outcomes
- **Accept proposal**: POST /api/strategy/refinement-proposals/:id/accept
- **Reject proposal**: POST /api/strategy/refinement-proposals/:id/reject
- **Chat**: POST /api/strategy/conversation

### Settings (/settings)
- **On mount**: GET /api/config
- **Save config**: POST /api/config/save with {section, values}
- **Test connection**: POST /api/config/test-connection?source=X
- **Clear pipeline**: POST /api/config/clear-pipeline

### TickerDetail (/ticker/:ticker)
- **On mount**: GET /api/ticker/:ticker, GET /api/ticker/:ticker/timeline, GET /api/review/:ticker, GET /api/evidence/:ticker

---

## 5. Key Workflows

### Full Pipeline Run (8 steps)
1. **Screener**: Loads universe from constitution, runs scoring, saves top results
2. **Thesis** (top 20): Researches each ticker with web search, validates return sources
3. **IC Review**: Stress-tests each thesis with bear case haircuts
4. **Memo** (PASS only): Generates full investment memo
5. **Library**: Archives all research artifacts
6. **Portfolio** (non-blocking): Runs health check on held positions
7. **Allocator** (non-blocking): Generates sizing recommendations
8. **Learning** (non-blocking): Pattern detection, drift analysis, outcome check

Steps 6-8 are non-blocking — their failures don't stop the pipeline.

### Strategy Create/Refine
1. User sends message via POST /api/strategy/conversation
2. AI responds with probing questions (first-time) or refinement suggestions
3. User clicks "Save" → POST /api/strategy/save with extracted profile
4. Backend creates/updates constitution in DB
5. Backend triggers scoring code generation (LLM)
6. New strategy_version created with scoring_code
7. Constitution.active_version_id updated

**Known issue**: Step 2 only generates a response — it does NOT save settings. Step 3 (save) is required.

### Portfolio Position Save
1. User enters positions in editor
2. POST /api/portfolio/positions with [{ticker, shares, cost_basis}]
3. Backend fetches prices: yfinance first, FMP fallback
4. Tickers without prices are DROPPED (removed_tickers in response)
5. Lots aggregated: weighted average cost basis
6. P&L computed: (current_price - avg_cost) * shares
7. Snapshot saved to portfolio_snapshots (UPSERT on today's date)

---

## 6. Test Suite

### Running Tests

```bash
# All new behavioral tests (120 tests)
python3 -m pytest tests/db/ tests/contracts/ tests/flows/ tests/portfolio_tests/ tests/learning_tests/ -v

# Just contract tests (catches button-does-nothing bugs)
python3 -m pytest tests/contracts/ -v

# Just DB tests
python3 -m pytest tests/db/ -v

# Full suite including legacy tests
python3 -m pytest tests/ -v
```

### Test Organization

| Directory | Tests | What it catches |
|-----------|-------|-----------------|
| tests/db/ | 22 | Schema creation, CRUD operations, FK constraints |
| tests/contracts/ | 63 | Every API endpoint responds correctly, response shapes match, mutations change state |
| tests/flows/ | 19 | Pipeline lifecycle, job management, constitution CRUD, strategy conversation |
| tests/portfolio_tests/ | 9 | Position save, P&L calculations, portfolio history |
| tests/learning_tests/ | 16 | Feedback recording, drift detection, outcomes, library search |

### Adding New Tests

Convention: `test_{category}_{behavior}.py` with `test_{action}_{condition}_{expected}()`.

To add a test for a new endpoint:
1. Add entry to `tests/contracts/api_contract_map.py`
2. Run `pytest tests/contracts/test_all_endpoints_respond.py` — it auto-tests the new entry
3. Add specific mutation tests to `tests/contracts/test_mutation_side_effects.py`
