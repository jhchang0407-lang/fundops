# FundOps Implementation Map

Distilled from CONTEXT.md and docs/adr/0001–0052. This is the build anchor for the platform
rebuild. CONTEXT.md remains product truth; this map records how that truth becomes code.

## 1. Build shape

- **Stack**: Python 3.12 FastAPI backend + SQLite (WAL, forward-only migrations) + React 19/TS/Vite
  frontend. `npm start` → `scripts/start.mjs` → uvicorn serving API + built frontend. HTTP API is a
  UI adapter, not the product contract (ADR-0050).
- **Clean baseline**: new workspace DB (`~/.fundops/workspace.db`, env `FUNDOPS_DB` override; tests
  use tmp). The PoC schema is NOT migrated (ADR-0029). Forward migrations apply from this new
  baseline (ADR-0030).
- **One workspace, one owner, one active Constitution, one primary portfolio** (ADR-0040/0052).
- **Module layout** (new backend):
  - `backend/core/` — db + migrations, config, llm client, ids/clock, errors
  - `backend/stores/` — platform stores; ALL writes go through these (ADR-0031)
  - `backend/domain/` — pure domain logic (constitution model, guardrails, wiring, IC scoring
    model, thesis-health evaluation, ledger math, metric catalog, artifact schemas)
  - `backend/services/` — application services with explicit command intents; canonical writes
    commit atomically, projections refresh after (ADR-0033)
  - `backend/workflows/` — screener, thesis, ic_review, memo, thesis_health, portfolio_review,
    learning, pipeline (durable runs + steps, ADR-0036)
  - `backend/chat/` — FundOps Chat: strategy chat + archive Q&A
  - `backend/connectors/` — sec_edgar, yfinance (kept from PoC, adapted), provider request queue
  - `backend/api/` — thin FastAPI routes

## 2. Core domain model (tables)

Identity (ADR-0023): `investment_entities` (stable id, name, cik, sector, industry),
`ticker_aliases` (ticker → entity, valid_from/to). Product stays ticker-first; ticker is alias.

Constitution (ADR-0002..0011, 0006):
- `constitution_versions` — immutable; version_number, status(active|superseded), north_star,
  style_blend JSON, narrative, version_rationale, source_proposal_id, activated_at.
- `strategy_criteria` — typed child rows: criterion_id, kind(screen|rank|research_review|
  ic_hurdle|preference), metric, operator, value JSON, weight, data_support_level(fully|partial|
  proxy|research_review|unsupported), rule_rationale, rule_source (required to activate),
  interpretation (plain-English).
- `strategy_proposals` — envelope: status(draft|pending|accepted|rejected|cancelled), payload JSON
  (summary, rules, wiring_preview, tradeoffs, unsupported_preferences), validation JSON,
  rationale, chat session ref, resulting_version_id. Only ONE pending draft at a time.
- `settings_projections` — per capability per version: settings JSON + durable
  `summary_text` (capability wiring summary), generated at activation. Deterministic from
  criteria; ambiguity → review item, never invented defaults.
- `universe_versions` — resolved ticker list snapshot, exclusions+reasons, source label.
- `strategy_memory` — structured strategy memory (preferences, unsupported criteria, session
  summaries). Raw chat = evidence only (ADR-0011).
- `chat_sessions`, `chat_messages` — conversation evidence; mode per exchange
  (strategy|archive|exploration|status).

Evidence (ADR-0021, 0024–0028):
- `evidence_sources` — kind(filing|provider|web|user|model), locator, title, publisher, hash,
  retention_tier(identity|excerpt|normalized|snapshot), snapshot TEXT nullable, fetched_at.
- `evidence_records` — family(financial_metric|filing_citation|market_data|research_claim|
  model_finding|user_response|workflow_judgment|portfolio_event), entity_id, ticker, as_of,
  captured_at, payload JSON, source_id, quality, superseded_by, created_by_run_id.
- `evidence_bundles` — frozen manifest JSON (evidence ids, constitution_version, universe_version,
  prompt versions, model, inclusion notes) per meaningful output (ADR-0026).

Financial data (ADR-0015–0017, 0042–0047):
- `reported_financial_facts` — entity, concept/tag, taxonomy, period_end, period_type, value, unit,
  source_id, accession, filed_at, mapped_concept nullable, superseded_by. Unmapped facts retained
  (ADR-0044).
- `financial_observations` — entity, metric (from catalog), period_end,
  period_type(annual|quarterly|ttm), value, unit, basis, is_calculated, lineage JSON (inputs,
  formula, derivation e.g. derived-Q4), catalog_version, mapping_version, quality, superseded_by.
- Metric catalog lives in code `backend/domain/metric_catalog.py` with `CATALOG_VERSION`;
  each metric: id, label, unit, formula/source, expected range, sector applicability,
  missing-data behavior, decision_authority (hard-gate-capable bool), thesis-health support
  (allowed cadences × lookback bases).
- `latest_financials` — rebuildable projection (entity, metric → value, period_end).
- Retention targets: 5 fiscal years annual + 12 quarters quarterly; derived Q4 only with complete
  provenance else data gap.

Workflow spine (ADR-0020, 0022, 0032–0037):
- `workflow_runs` — kind(screener|thesis|ic_review|memo|thesis_health|portfolio_review|learning|
  pipeline), status(running|completed|failed|cancelled), trigger(user|schedule|pipeline|directed|
  coverage), constitution_version_id, universe_version_id, stats JSON, error.
- `workflow_steps` — run_id, name, item ref (ticker), status, attempt (retry ≤3), detail, error.
  Operational failure ≠ investment judgment, ever.
- `artifacts` — the shared artifact identity. id = workflow artifact identifier (waid). Columns:
  kind(screener_snapshot|thesis|ic_verdict|investment_memo|thesis_health_check|portfolio_review|
  learning_card), entity_id, ticker, run_id, schema_version, payload JSON (Structured Workflow
  Artifact: artifact kernel + typed body + citations + evidence refs + validation state),
  rendered_md, evidence_bundle_id, constitution_version_id, created_at, superseded_by.
  Artifact kernel fields (in payload): {kind, schema_version, entity, ticker, generated_at,
  constitution_version, evidence_bundle_id, validation:{status, errors}, sections|fields,
  citations[]}.
- `screener_results` — typed per-run rows: passed, rank, score, ranking_components JSON,
  pass_evidence JSON [{criterion, threshold, observed}], fail_reasons JSON (all failures),
  selected (top-picks membership), selection_order.
- `selection_events` — stage selection feedback: capability, run_id, ticker,
  action(promote|dismiss), recorded for learning; never mutates ranking.
- `workbench_state` — active stage state per capability for the live server session
  (session_id, capability, payload JSON). New server session ⇒ abandoned, never auto-resumed.
- `ic_verdicts` — typed: run_id, ticker, thesis_artifact_id, verdict(pass|fail), conviction, fit,
  data_quality (0-100 each, component breakdowns in JSON), gate_score, blend JSON, cutoff,
  hurdle_findings JSON [{hurdle, met, explanation}], rationale, is_override, prior_verdict,
  constitution_version_id, artifact_id.
- IC gate scoring model (ADR-0012): hard hurdles first (miss ⇒ auto fail unless user override);
  then gate score = 45% conviction + 35% fit + 20% data quality (blend constitution-ownable),
  pass cutoff default 70. Unknown component = neutral 50, lowers data quality; contradicted
  component < 50 and lowers both. Component weights fixed and equal within each score.

Memo (ADR-0013/0014): fixed 7-section outline — Current Setup & Variant View / Business Quality /
Industry and Growth / Financial Quality / Valuation / Risks, Bear Case & Kill Criteria / Decision
Summary. Fixed subsections per CONTEXT (e.g. Why Now, Recent Events, Market View, Variant View,
Evidence Quality...). Generation order: evidence → research stage → distribution → core body
(risks before valuation) → valuation (judgment + deterministic math) → current setup → decision
summary. Section-scoped evidence packages; Completed Thesis and IC outputs are provenance only,
never writer inputs. Memo Decision ∈ {attractive, watchlist, avoid, needs_more_evidence}.
Monitoring plan is a separate structured output (not a rendered memo section).

Thesis health (ADR-0014):
- `thesis_health_plans` — memo_artifact_id, entity, active bool, raw_plan JSON. New memo freezes
  prior plan, becomes active source.
- `thesis_watch_items` — plan_id, item_type(assumption|return_driver|risk|kill_criterion),
  title, tracking_mode(quantitative|qualitative|unsupported), metric, comparator, threshold,
  cadence(quarterly|annual|ttm|slower), lookback(latest|yoy|ttm|annual|multi_period_avg),
  confirmation_periods (default 2), status(intact|watch|broken|unknown|data_gap), current_value,
  last_checked_at, why_matters. Unsupported items retained but hidden + non-status-driving.
- `thesis_health_checks` — append-only per-item checks: kind(baseline|refresh), observed JSON,
  status, data_gap, checked_at. Baseline checks at memo time; broken normally requires
  confirmation across periods. Current state = latest accepted check.
- `thesis_health_refreshes` — entity, trigger(scheduled|manual|filing), metadata_only bool,
  filing_check JSON, ran_at. Metadata-gated: full recalc only on new 10-Q/10-K.
- Summary label derived: Broken > Watching > Intact > Not Checked.

Portfolio (ADR-0035, 0041):
- `portfolio_lots` — ticker/entity, shares, cost_basis, purchase_date, import_source(manual|...),
  note, position_type nullable, corrected_by nullable (corrections ≠ outcomes).
- `portfolio_sales` — shares, price, sale_date, realized_pnl, lot_matches JSON (FIFO default),
  is_exit_record bool. Explicit entry intent (buy vs sell), never inferred.
- `price_marks` — ticker, price, as_of (market data cache; price refresh never touches
  thesis health or user-entered fields).
- `holdings` projection — rebuildable from ledger: shares, avg_cost, market_value,
  unrealized_pnl, weight, coverage_state(covered|queued|running|stale|failed|none).
- Coverage: held ticker without fresh thesis-health-ready memo (≤90d) ⇒ automatic coverage memo
  queued on save/sync (not page load); provenance = portfolio_coverage.

Dashboard (decision/attention queue, never duplicate truth):
- `dashboard_items` — kind(decision|attention), section(needs_decision|portfolio_review|
  needs_attention), source_type + source_id + source_version, title, body, severity,
  status(open|resolved|dismissed|snoozed), evidence refs JSON. Responses apply to source
  version; resurfacing only on material source change.
- `dashboard_responses` — item_id, response code, kind(hygiene|feedback|both), payload.
- `approval_records` — target_type/id/version, action(accept|reject), effect, created_at.
- Portfolio Review = projection-built section: `portfolio_pressure` items (held; broken/watch
  thesis health, policy/concentration flags, stale coverage) + `constitution_fit` opportunities
  (non-held; IC pass/memo-backed/intact-health/screener-ranked), each with visible rank source.
  Evidence-first language only; never buy/sell.

Learning (append-only, ADR catalogue + CONTEXT):
- `learning_records` — kind(outcome_evaluation|thesis_health_finding|pattern|recommendation|
  response|recommendation_outcome), entity nullable, window_months nullable, payload JSON,
  confidence_label(exploratory|promising|recommendation_ready|superseded|inconclusive),
  lineage JSON (screener snapshot ids, constitution version, watch items, filings, responses),
  superseded_by.
- Outcome evaluation windows: 3/6/12/24/36 months. Results: thesis_worked | right_thesis_slow_market
  | lucky_result | thesis_failed | no_clear_signal(+reason).
- Recommendations require evidence patterns (not single outcomes), become Dashboard Decision
  Items (evidence cards), require explicit acceptance; accepted executable changes create a new
  Constitution Version via a strategy proposal.

Ops:
- `work_queue` — durable local work records (ADR-0048): kind, priority, status, payload,
  attempts, run_after, last_error. Provider calls go through shared provider request queue with
  budget; interactive > scheduled > idle learning priorities.
- `execution_provenance` (ADR-0034) — run_id, step, kind(model|tool|parser|validation), model,
  prompt_version, inputs ref, outputs ref, validation JSON, usage JSON, rejected_output TEXT
  nullable.
- `ai_usage` — ts, capability, model, tokens_in/out, est_cost nullable, run_id. Summary in
  Settings; estimates labeled approximate.

## 3. Workflow lifecycle (shared stage pattern)

Funnel: Screener (universe → requirements → top 50 review set, top 20 = Top Picks/handoff) →
Thesis (generate ALL of intake; selection ranking by return potential, default selection count 10;
score cap for weak/unsupported return profiles) → IC Review (gate; every pass enters IC selection,
no cap) → Memo (one investment memo per intake item) → monitoring/learning.

Shared rules: ranking expressed by row order; selected block (yellow border) + remaining block
partition stage output; +/- controls only after stage output exists; promote appends to end of
selection and expands count, dismiss reflows ranking without stigma; selection feedback recorded;
ops failures retry ×3 then visible operational-failure state excluded from handoff; completed
artifacts survive any later upstream changes; handoff refreshes next stage intake without
executing it; Run Full Pipeline chains stages via handoffs. Workbench state is per live server
session; completed artifacts are forever. Directed research requests can start at Thesis or Memo
for validated tickers with user-directed provenance; held-position coverage memos bypass the
funnel with coverage provenance.

## 4. AI trust boundaries

AI does: strategy interpretation + proposal drafting (guardrails validate; user accepts),
thesis/memo writing into versioned structured schemas, IC semantic review feeding deterministic
scoring/hurdle rules, evidence/filing interpretation (claims extracted + validated before use),
archive answers grounded in retained artifacts with citations, learning pattern interpretation.
AI never: silently mutates constitution/settings/portfolio/evidence, rejudges quantitative thesis
health, invents watch items from prose, produces buy/sell instructions, or bypasses validation.
Deterministic owns: guardrails, screening, ranking math, IC gate arithmetic + hurdles, valuation
math checks, thesis-health evaluation, ledger math, projections, retries, provenance.
Cost discipline: deterministic pre-filter before AI; bounded section-scoped context packets;
cheap model tier for extraction/classification, strong tier for thesis/IC/memo/strategy/learning;
cache on (evidence bundle hash, constitution version, prompt version, schema version); nothing
expensive triggered by page views; AI usage records for all calls.

## 5. UI navigation model

Sidebar: **Chat** (FundOps Chat, default route), **Dashboard**, — Workflow: **Screener**,
**Thesis**, **IC Review**, **Memo**, — **Portfolio**, **Library**, — **Settings**.
Non-sidebar routes: **Company Page** `/company/:ticker` (identity strip; sections: Workflow Map
(default; lanes Screener/Thesis/IC/Memo/Portfolio, dated milestone cards newest-first, right-side
preview drawer), Financials (snapshot + full annual statements w/ IS-BS-CF switch), Thesis Health
(watch items grouped broken>watch>unknown>intact, summary label, history)); **Workflow Artifact
Reader** `/artifact/:id` (shared shell + type-specific body renderer, PDF/markdown export
secondary). Library = collapsible ticker search panel + embedded Company Page (known tickers
only, prefix matching, blank by default). Tickers everywhere are links to Company Page; no
"View in Library" buttons. Dashboard sections: Needs Decision, Portfolio Review (pressure list +
constitution-fit list side by side), Needs Attention, Recent Activity (quiet). Read-only
generated outputs look intentionally locked/historical. Keep dark institutional design system
(frontend/src/styles/design-system.css) — Geist/Inter/JetBrains Mono, #0a0a0f bg, orange accent.

FundOps Chat page: center column = conversation; metadata panel (Constitution version, style
blend, last changed, pending proposals) shown after setup; capability chips (Screener, Thesis,
IC Review, Memo, Universe...) open read-only Capability Wiring Panels; strategy drafts render as
structured approval cards (summary, rules + interpretation, wiring preview, unsupported
preferences, tradeoffs, approval prompt); archive answers render citations with open-in-reader
actions; mode badge distinguishes strategy vs archive behavior.

## 6. PoC keep / replace / delete

KEEP (adapt): sec_edgar + yfinance connectors and financial calculation logic; LLM client shape
with usage logging; design-system CSS; start.mjs/setup.mjs flow; e2e harness approach.
REFERENCE then REPLACE: all agents (screener/thesis/ic/memo prompts + valuation math reused as
material), routes, db.py/db_v2.py/store.py/migrations.py (clean new schema), pages (rebuilt to
this map), workflow.yaml (replaced by constitution + operational config), Allocator (becomes
Portfolio Review), Mirror (folds into Learning), legacy memo modes (single Investment Memo).
DELETE: legacy tables/dual-write, scoring codegen/sandbox (replaced by typed criteria + wiring),
judgment_events as spine (replaced by runs/artifacts/evidence), refinement code-change proposals
(replaced by learning recommendations → strategy proposals).

## 7. Out of scope for this baseline (documented, not built)

Broker sync (ledger is import-ready), multi-strategy/multi-portfolio, agent-native extension
harness (Agent Work Orders) beyond stubs, PDF rendering pipeline (markdown export ships first;
PDF pipeline versioned later), Risk & Exposure/Decision Register/Audit Packages beyond minimal
records, vector retrieval (Archive Q&A uses deterministic retrieval over structured records
first), FMP enrichment (optional, off by default).
