# FundOps API & Module Contract (build coordination)

Pinned contract for parallel implementation. Backend route modules each expose
`router = APIRouter()`. All routes mount under `/api`. JSON in/out. Errors:
`{"detail": str}` with 4xx/5xx. This contract is authoritative for names/paths;
response field lists may grow but not change meaning.

## Route module ownership
- `backend/api/routes/workflows.py` — screener/thesis/ic/memo/pipeline/runs/directed
- `backend/api/routes/portfolio.py` — portfolio + ledger
- `backend/api/routes/company.py` — company page + financials + thesis health reads
- `backend/api/routes/monitoring.py` — thesis health refresh actions + coverage
- `backend/api/routes/learning.py` — learning records/views
- `backend/api/routes/chat.py` — FundOps Chat
- `backend/api/routes/strategy.py` — constitution/proposals/wiring
- `backend/api/routes/dashboard.py` — dashboard items/responses/recent activity
- `backend/api/routes/settings.py` — opconfig, usage, destructive actions, export
- `backend/api/routes/artifacts.py` — artifact reader/export
- `backend/api/routes/library.py` — known-ticker suggest
- `backend/api/__init__.py` — `create_app()` + `app`; mounts all routers; serves
  frontend/dist with SPA fallback; CORS for localhost:5173.

## Endpoints

### System
- `GET /api/health` → `{ok, ai_configured, has_constitution, workspace_schema_version}`

### FundOps Chat
- `POST /api/chat/message` `{session_id?, message}` →
  `{session_id, mode: "strategy"|"archive"|"exploration"|"status", reply,
    draft?: ProposalCard, citations?: [{artifact_id?, ticker?, kind, label}],
    actions?: [{type:"open_artifact"|"open_company", id?, ticker?, label}]}`
- `GET /api/chat/history?session_id=` → `{messages:[{role, mode, content, refs, created_at}]}`

### Strategy
- `GET /api/strategy` → `{active_version: VersionSummary|null, pending_proposal: Proposal|null,
   projections: [{capability, summary_text, review_items}], universe: {name, tickers_count}}`
- `GET /api/strategy/versions` → `[{id, version_number, status, north_star, version_rationale, activated_at}]`
- `GET /api/strategy/versions/{id}` → full snapshot incl. criteria + projections
- `GET /api/strategy/diff?from_id=&to_id=` → `{added:[], removed:[], changed:[]}` (criteria-level)
- `POST /api/strategy/proposals/{id}/accept` → `{version}` (guardrails re-validated; wires settings)
- `POST /api/strategy/proposals/{id}/reject` → `{ok}`
- `GET /api/strategy/wiring/{capability}` → `{capability, settings, summary_text, review_items, version_id}`

ProposalCard payload (`strategy_proposals.payload`):
`{summary, north_star, style_blend:{label:weight}, rules:[CriterionDict],
  ic:{gate_score_blend?, pass_cutoff?}, universe:{name, tickers?},
  unsupported_preferences:[str], tradeoffs:[str], wiring_preview:{capability: summary_str},
  approval_prompt: str}`

### Workflows (shared stage pattern)
- `POST /api/workflows/screener/run` → `{run_id}` (async kicked; poll current)
- `GET  /api/workflows/screener/current` →
  `{run: RunSummary|null, summary:{universe_size, passed, shown}, top_picks:[CandidateRow],
    remaining:[CandidateRow], status:"idle"|"running"|"completed"|"failed"}`
  CandidateRow: `{ticker, company_name, sector, price, rank, selected, selection_order,
    key_financials:[{metric,label,value}], ranking_explanation, pass_evidence:[{criterion,threshold,observed}]}`
- `POST /api/workflows/screener/selection` `{ticker, action:"promote"|"dismiss"}` → updated current
- `POST /api/workflows/thesis/run` → `{run_id}`
- `GET  /api/workflows/thesis/current` →
  `{status, rows:[ThesisRow], selection:[ticker], remaining:[ticker], selection_count}`
  ThesisRow: `{ticker, company_name, state:"pending"|"running"|"retrying"|"failed"|"completed",
    artifact_id?, price?, fair_value?, expected_return_pct?, capped?, summary?, return_components?}`
- `POST /api/workflows/thesis/selection` `{ticker, action}` → updated current
- `POST /api/workflows/ic/run` → `{run_id}`
- `GET  /api/workflows/ic/current` → `{status, selection:[ICRow], remaining:[ICRow]}`
  ICRow: `{ticker, company_name, price, verdict:"pass"|"fail"|null, state, gate_score,
    conviction, constitution_fit, data_quality, rationale, hurdle_findings, is_override, artifact_id?}`
- `POST /api/workflows/ic/override` `{ticker, action:"promote"|"remove"}` → updated current
- `POST /api/workflows/memo/run` `{ticker?}` → `{run_id}` (omit ticker = all Memo Intake)
- `GET  /api/workflows/memo/current` → `{status, intake:[{ticker, state, artifact_id?, decision?}]}`
- `POST /api/workflows/pipeline/run` → `{run_id}` (chains all stages)
- `GET  /api/runs/{run_id}` → `{run, steps:[{name,item_ref,status,attempt,error}]}`
- `GET  /api/runs?limit=30` → `[RunSummary]`
- `POST /api/research/directed` `{ticker, capability:"thesis"|"memo"}` → `{run_id}`

### Company Page
- `GET /api/company/{ticker}` →
  `{identity:{ticker, name, sector, industry, price, latest_stage, latest_verdict, owned, entity_id},
    lanes:[{lane:"screener"|"thesis"|"ic_review"|"memo"|"portfolio",
            milestones:[{date, title, status?, artifact_id?, kind, summary, detail?}]}]}`
  (milestones newest-first; 404 `{detail}` when unknown ticker)
- `GET /api/company/{ticker}/financials` →
  `{snapshot:{market_cap, pe, revenue_growth, gross_margin, operating_margin, fcf_yield, roic, debt_equity},
    annual:{income:[], balance:[], cashflow:[]}|{periods:[{period_end, metrics:{}}]},
    quarterly:{periods:[...]}, as_of}`
- `GET /api/company/{ticker}/thesis-health` →
  `{summary_label:"Intact"|"Watching"|"Broken"|"Not Checked"|null, active_source:{memo_artifact_id, memo_date}|null,
    items:[{id, title, item_type, status, metric, comparator, threshold, current_value, lookback, cadence, last_checked_at, data_gap, why_matters}],
    history:[{refresh_id, ran_at, metadata_only, trigger}], filings_last_checked, recalculated_at, empty_reason?}`

### Artifacts
- `GET /api/artifacts/{id}` → `{id, kind, ticker, created_at, schema_version, payload, rendered_md,
    constitution_version_id, evidence_bundle_id, run_id}`
- `GET /api/artifacts/{id}/export?format=md` → text/markdown download

### Library
- `GET /api/library/suggest?q=AA` → `{matches:[{ticker, name?}]}` (known tickers, prefix match)

### Portfolio
- `GET  /api/portfolio` → `{holdings:[HoldingRow], totals:{market_value, cost_basis, unrealized_pnl, realized_pnl, positions}}`
  HoldingRow: `{ticker, shares, avg_cost, price, market_value, unrealized_pnl, weight, position_type,
    coverage_state, thesis_health_label?, flags:[{kind:"concentration"|..., detail}]}`
- `POST /api/portfolio/lots` `{ticker, shares, cost_basis, purchase_date, position_type?, note?}` → `{lot_id}`
  (triggers coverage check; explicit Portfolio Entry Intent = buy)
- `POST /api/portfolio/sales` `{ticker, shares, price, sale_date, note?}` → `{sale_id, realized_pnl}`
- `POST /api/portfolio/lots/{id}/correct` `{shares?, cost_basis?, purchase_date?, remove?:bool}` → `{ok}`
- `POST /api/portfolio/refresh` → `{updated: n}` (price/P&L only; never thesis health)
- `GET  /api/portfolio/ledger?ticker=` → `{lots:[], sales:[]}`

### Monitoring (thesis health actions)
- `GET  /api/monitoring/due` → `{due: n, tickers:[...]}` (thesis-health-ready tickers due a check)
- `POST /api/monitoring/refresh` → `{refreshed:[{ticker, metadata_only, summary_label}]}` (manual, metadata-gated)
- `POST /api/monitoring/coverage/check` → `{queued:[tickers]}` (holdings lacking fresh coverage)

### Dashboard
- `GET /api/dashboard` →
  `{needs_decision:[Item], portfolio_review:{pressure:[Item], opportunities:[Item]},
    needs_attention:[Item], recent_activity:[{kind, title, ticker?, run_id?, artifact_id?, created_at}]}`
  Item: `{id, kind, section, source_type, ticker?, title, body, severity, rank_source,
    evidence_refs, response_set, created_at}`
- `POST /api/dashboard/items/{id}/respond` `{response, payload?}` → `{ok, status}`
- `POST /api/dashboard/refresh` → `{ok}` (rebuild dashboard projections incl. portfolio review)

### Learning
- `GET /api/learning` → `{outcome_evaluations:[Record], recommendations:[Record], findings:[Record],
    responses:[Record], summary:{counts}}`
- `POST /api/learning/evaluate` → `{created: n}` (run due outcome evaluations)

### Settings
- `GET  /api/settings` → `{config (no secrets), health, ai_usage: summary}`
- `POST /api/settings` `{updates}` → `{config}` (operational only)
- `POST /api/settings/test-ai` → `{ok, model?, error?}`
- `POST /api/settings/clear-pipeline` → `{ok}` (destructive: workflow outputs; preserves constitution+portfolio)
- `POST /api/settings/reset-constitution` → `{ok}` (destructive)
- `GET  /api/settings/export` → JSON download of retained records

## Backend service interfaces (pinned)
- `backend.services.market_data.MarketDataService(stores)`:
  `refresh_quotes(tickers) -> {ticker: quote}`, `fetch_fundamentals(ticker) -> dict|None`,
  `metrics_for(tickers, allow_fetch=True) -> {ticker: metrics}` (all async).
- `backend.core.ai.get_ai().complete_json(capability, system, user, shape_hint, tier, run_id, stub=...)`
  (async) — ALL model calls go through this.
- `backend.workflows.screener.run_screener(stores, trigger="user") -> run_id` (async);
  `screener_current(stores) -> dict` per contract above; `screener_select(stores, ticker, action)`.
- `backend.workflows.thesis.run_thesis(stores, trigger) -> run_id`; `thesis_current(stores)`;
  `thesis_select(stores, ticker, action)`.
- `backend.workflows.ic_review.run_ic(stores, trigger) -> run_id`; `ic_current(stores)`;
  `ic_override(stores, ticker, action)`.
- `backend.workflows.memo.run_memo(stores, ticker=None, trigger="user", provenance="ic_selection") -> run_id`;
  `memo_current(stores)`.
- `backend.workflows.pipeline.run_pipeline(stores) -> run_id`.
- `backend.workflows.thesis_health.refresh_all(stores, trigger="manual") -> list`;
  `due_tickers(stores) -> list`; `create_plan_for_memo(stores, memo_artifact_id) -> plan_id|None`;
  `thesis_health_view(stores, ticker) -> dict` per contract.
- `backend.services.portfolio_service.PortfolioService(stores)`:
  `add_lot(...)`, `record_sale(...)`, `refresh_prices()`, `holdings_view()`,
  `ensure_coverage()` (queues coverage memos for held tickers lacking fresh
  thesis-health-ready memo ≤90 days).
- `backend.services.dashboard_service.rebuild(stores)` — projects portfolio review
  (pressure + constitution-fit) and attention items from sources; `overview(stores) -> dict`.
- `backend.chat.service.handle_message(stores, session_id, message) -> dict` per chat contract.
- Long-running runs execute as asyncio background tasks; `*/current` endpoints poll
  workbench state. Workbench state lives in `stores.runs.get/set_workbench(capability)`.

## Frontend ownership
- Shell agent owns: `src/App.tsx`, `src/components/Sidebar.tsx`, `src/api/client.ts`
  (exports typed fns: `getHealth, sendChat, getChatHistory, getStrategy, getWiring,
  acceptProposal, rejectProposal, runScreener, getScreener, selectScreener, runThesis,
  getThesis, selectThesis, runIC, getIC, overrideIC, runMemo, getMemo, runPipeline,
  getRun, getRuns, directedResearch, getCompany, getCompanyFinancials, getThesisHealth,
  getArtifact, librarySuggest, getPortfolio, addLot, recordSale, correctLot,
  refreshPortfolio, getMonitoringDue, refreshMonitoring, getDashboard, respondDashboard,
  refreshDashboard, getLearning, runLearning, getSettings, saveSettings, testAI`),
  pages: `src/pages/Chat.tsx`, `src/pages/Dashboard.tsx`, `src/pages/Settings.tsx`.
- Workflow agent owns pages: `src/pages/Screener.tsx`, `src/pages/Thesis.tsx`,
  `src/pages/ICReview.tsx`, `src/pages/Memo.tsx`, `src/pages/CompanyPage.tsx`,
  `src/pages/Library.tsx`, `src/pages/Portfolio.tsx`, `src/pages/ArtifactReader.tsx`,
  shared `src/components/workflow/*`.
- Routes (pinned in App.tsx): `/` Chat, `/dashboard`, `/screener`, `/thesis`, `/ic-review`,
  `/memo`, `/portfolio`, `/library`, `/settings`, `/company/:ticker`, `/artifact/:id`.
- Design system: keep `src/styles/design-system.css` tokens (dark, Geist/Inter/JetBrains
  Mono, orange accent). Read-only artifacts look locked/historical; tickers are links
  to `/company/:ticker`.

## Bulk data additions (ADR-0059 / ADR-0060)

Route module: `backend/api/routes/sync.py` (`router = APIRouter()`).
- `GET  /api/sync` → `{bootstrap:{done, stage, progress, error?}, last_daily_tick, last_bulk_refresh,
   universe:{name, count}, counts:{facts, prices_tickers, prices_rows, filings, ownership},
   cache_size_mb}`
- `POST /api/sync/bootstrap` → `{started}` (one-time full download: companyfacts + prices + ownership; work-queue job with progress in sync_state)
- `POST /api/sync/daily` → `{started}` (manual daily tick: index files → filings → targeted top-ups → price update → thesis health for filers)
- `GET  /api/company/{ticker}/prices?range=1m|6m|1y|5y` → `{ticker, range, prices:[{date, close, volume}]}`
- `GET  /api/company/{ticker}/ownership` → `{insiders:[{as_of, owner_name, owner_role, txn_type, shares, value}], institutions:[{as_of, owner_name, shares, value}], empty_reason?}`

Pinned backend interfaces:
- `backend.services.ingest.sync.bootstrap(stores, progress_cb=None)` (async) and
  `daily_tick(stores)` (async) — orchestration entry points; both work-queue friendly.
- `backend.services.ingest.sec_bulk.sync_companyfacts(stores, tickers)` — download/extract → facts + observations.
- `backend.services.ingest.sec_index.sync_daily_indexes(stores, since)` — index files → filings rows.
- `backend.services.ingest.prices.sync_price_history(stores, tickers, years)` — batched downloads → price_history.
- `backend.services.ingest.ownership.sync_ownership(stores, tickers)` — quarterly data sets → ownership_records.
- `stores.bulk` (BulkStore): upsert_prices, price_range, latest_close, close_on_or_before,
  add_filing, filings_for, unprocessed_filings, mark_filings_processed, add_ownership,
  ownership_for, get_state/set_state/state_snapshot.
- Frontend client additions: `getSync, startBootstrap, runDailySync, getPrices, getOwnership`.
- AI provider config: `ai.provider: "openai"|"agent_cli"`, `ai.agent_cli: {preset, command, timeout_s}`;
  `FUNDOPS_AI_PROVIDER` env override; Settings exposes provider choice + test.
