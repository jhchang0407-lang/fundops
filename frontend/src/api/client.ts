/**
 * FundOps typed API client.
 *
 * Mirrors docs/api-contract.md. All routes mount under /api (vite proxies to the
 * backend in dev). Errors arrive as `{detail: string}` with 4xx/5xx and are thrown
 * as ApiError. Response field lists may grow but not change meaning, so most
 * interfaces keep non-essential fields optional.
 */

const BASE = '/api';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body: unknown = await res.json();
      if (
        body &&
        typeof body === 'object' &&
        typeof (body as { detail?: unknown }).detail === 'string'
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetchJSON<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/* ════════════════════════ System ════════════════════════ */

export interface HealthResponse {
  ok: boolean;
  ai_configured: boolean;
  ai_provider?: string;
  ai_provider_id?: string;
  has_constitution: boolean;
  constitution_version?: number | null;
  workspace_schema_version: number | null;
}

export const getHealth = () => fetchJSON<HealthResponse>('/health');

/* ════════════════════════ FundOps Chat ════════════════════════ */

export type ChatMode =
  | 'strategy' | 'archive' | 'exploration' | 'status' | 'data' | 'guide' | 'action';

export interface ChatCitation {
  artifact_id?: string | null;
  ticker?: string | null;
  kind: string;
  label: string;
}

/** Ambient page context sent with drawer messages ("you're viewing NVDA"). */
export interface ChatPageContext {
  page: string;
  ticker?: string | null;
  /** When reading a retained artifact: lets the analyst open the document. */
  artifact_id?: string | null;
}

export interface ChatTableColumn {
  key: string;
  label: string;
  /** Metric catalog id when the column is one metric (values arrive pre-formatted). */
  metric?: string | null;
}

/** Structured result block rendered inside an assistant reply. */
export type ChatBlock =
  | {
      type: 'table';
      title: string;
      columns: ChatTableColumn[];
      rows: Record<string, string | number | null>[];
    }
  | {
      type: 'chart';
      title: string;
      ticker: string;
      range: string;
      points: { date: string; close: number }[];
    };

export interface ChatAction {
  type: 'open_artifact' | 'open_company' | 'navigate' | 'run_directed' | 'run_workflow';
  id?: string | null;
  ticker?: string | null;
  /** navigate: client route to open. */
  route?: string | null;
  /** run_directed: which workflow to run for `ticker`. */
  capability?: 'thesis' | 'memo' | string | null;
  /** run_workflow: pipeline | screener. */
  kind?: string | null;
  label: string;
}

/** Typed strategy criterion inside a proposal payload. */
export interface CriterionRule {
  criterion_id?: string;
  kind: string; // screen | rank | research_review | ic_hurdle | preference
  metric?: string | null;
  operator?: string | null;
  value?: unknown;
  weight?: number | null;
  data_support_level?:
    | 'fully'
    | 'partial'
    | 'proxy'
    | 'research_review'
    | 'unsupported'
    | string;
  rule_rationale?: string | null;
  rule_source?: string | null;
  interpretation?: string | null;
  /** Backend-humanized display fields (preferred when present). */
  rule?: string | null;
  metric_label?: string | null;
  kind_label?: string | null;
}

/**
 * Strategy proposal payload (strategy_proposals.payload) plus the proposal id —
 * `id` is what acceptProposal/rejectProposal take.
 */
export interface ProposalCard {
  id: string;
  summary?: string;
  north_star?: string;
  style_blend?: Record<string, number>;
  rules?: CriterionRule[];
  ic?: { gate_score_blend?: Record<string, number>; pass_cutoff?: number };
  universe?: { name?: string; tickers?: string[] };
  unsupported_preferences?: string[];
  tradeoffs?: string[];
  wiring_preview?: Record<string, string>;
  approval_prompt?: string;
  status?: string;
}

export interface ChatResponse {
  session_id: string;
  mode: ChatMode;
  reply: string;
  draft?: ProposalCard | null;
  citations?: ChatCitation[];
  actions?: ChatAction[];
  blocks?: ChatBlock[];
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant' | string;
  mode?: ChatMode | string | null;
  content: string;
  refs?: unknown;
  created_at?: string;
}

export interface ChatHistoryResponse {
  messages: ChatHistoryMessage[];
}

export const sendChat = (
  message: string,
  sessionId?: string | null,
  context?: ChatPageContext | null,
) =>
  post<ChatResponse>('/chat/message', {
    message,
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(context ? { context } : {}),
  });

export const getChatHistory = (sessionId: string) =>
  fetchJSON<ChatHistoryResponse>(
    `/chat/history?session_id=${encodeURIComponent(sessionId)}`,
  );

/** Server-side session anchor: the latest conversation, for cold starts. */
export const getChatSession = () =>
  fetchJSON<{ session_id: string | null }>('/chat/session');

export interface ChatThreadSummary {
  id: string;
  started_at: string;
  message_count: number;
  last_at: string | null;
  first_user_message: string | null;
}

export const getChatThreads = (limit = 30) =>
  fetchJSON<{ threads: ChatThreadSummary[] }>(`/chat/threads?limit=${limit}`);

export interface MemoryRecord {
  id: string;
  kind: string;
  content: { text?: string } & Record<string, unknown>;
  source: string | null;
  created_at: string;
}

export const getChatMemory = () =>
  fetchJSON<{ memory: MemoryRecord[] }>('/chat/memory');

export const forgetChatMemory = (memoryId: string) =>
  post<{ forgotten: string }>(`/chat/memory/${encodeURIComponent(memoryId)}/forget`, {});

/* ════════════════════════ Strategy ════════════════════════ */

export interface VersionSummary {
  id: string;
  version_number: number;
  status: string;
  north_star?: string | null;
  style_blend?: Record<string, number> | null;
  narrative?: string | null;
  version_rationale?: string | null;
  activated_at?: string | null;
}

export interface CapabilityProjection {
  capability: string;
  summary_text: string;
  review_items?: string[];
}

/** Pending proposal envelope as returned by GET /strategy. */
export interface PendingProposal {
  id: string;
  status?: string;
  payload?: ProposalCard;
  rationale?: string | null;
  created_at?: string;
}

export interface StrategyResponse {
  active_version: VersionSummary | null;
  pending_proposal: PendingProposal | null;
  projections: CapabilityProjection[];
  universe?: { name?: string | null; tickers_count?: number | null } | null;
}

export interface WiringResponse {
  capability: string;
  settings: Record<string, unknown>;
  summary_text: string;
  review_items: string[];
  version_id?: string | null;
}

export const getStrategy = () => fetchJSON<StrategyResponse>('/strategy');

export const getWiring = (capability: string) =>
  fetchJSON<WiringResponse>(
    `/strategy/wiring/${encodeURIComponent(capability)}`,
  );

export const acceptProposal = (proposalId: string) =>
  post<{ version: VersionSummary }>(
    `/strategy/proposals/${encodeURIComponent(proposalId)}/accept`,
  );

export const rejectProposal = (proposalId: string) =>
  post<{ ok: boolean }>(
    `/strategy/proposals/${encodeURIComponent(proposalId)}/reject`,
  );

/* ════════════════════════ Workflows (shared stage pattern) ════════════════════════ */

export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled';
export type StageStatus = 'idle' | 'running' | 'completed' | 'failed';
export type ItemState = 'pending' | 'running' | 'retrying' | 'failed' | 'completed';
export type SelectionAction = 'promote' | 'dismiss';

export interface RunSummary {
  id: string;
  kind: string;
  status: RunStatus | string;
  trigger?: string;
  started_at?: string;
  finished_at?: string | null;
  stats?: Record<string, unknown> | null;
  error?: string | null;
}

export interface RunStep {
  name: string;
  item_ref?: string | null;
  status: string;
  attempt?: number;
  error?: string | null;
}

export interface RunDetail {
  run: RunSummary;
  steps: RunStep[];
}

export interface RunStartResponse {
  run_id: string;
}

export interface KeyFinancial {
  metric: string;
  label: string;
  value: string | number | null;
  /** Pre-formatted human display value (preferred when present). */
  display?: string | null;
}

export interface PassEvidence {
  criterion: string;
  threshold: string | number | null;
  observed: string | number | null;
  metric?: string | null;
  /** Humanized fields (backend enrichment) — prefer over the raw ones. */
  label?: string | null;
  rule?: string | null;
  threshold_display?: string | null;
  observed_display?: string | null;
}

export interface CandidateRow {
  ticker: string;
  company_name?: string | null;
  sector?: string | null;
  price?: number | null;
  rank?: number;
  selected?: boolean;
  selection_order?: number | null;
  key_financials?: KeyFinancial[];
  ranking_explanation?: string | null;
  pass_evidence?: PassEvidence[];
}

export interface ScreenerCurrent {
  run: RunSummary | null;
  summary?: { universe_size?: number; passed?: number; shown?: number };
  top_picks: CandidateRow[];
  remaining: CandidateRow[];
  status: StageStatus | string;
}

export interface ThesisRow {
  ticker: string;
  company_name?: string | null;
  state: ItemState | string;
  artifact_id?: string | null;
  price?: number | null;
  fair_value?: number | null;
  expected_return_pct?: number | null;
  capped?: boolean;
  summary?: string | null;
  return_components?: unknown;
  coherence_warning?: string | null;
}

export interface ThesisCurrent {
  status: StageStatus | string;
  rows: ThesisRow[];
  selection: string[];
  remaining: string[];
  selection_count?: number;
}

export interface HurdleFinding {
  hurdle: string;
  met: boolean | null;
  explanation?: string | null;
}

export interface ICRow {
  ticker: string;
  company_name?: string | null;
  price?: number | null;
  verdict: 'pass' | 'fail' | null;
  state?: ItemState | string;
  gate_score?: number | null;
  conviction?: number | null;
  constitution_fit?: number | null;
  data_quality?: number | null;
  rationale?: string | null;
  hurdle_findings?: HurdleFinding[];
  is_override?: boolean;
  artifact_id?: string | null;
}

export interface ICCurrent {
  status: StageStatus | string;
  selection: ICRow[];
  remaining: ICRow[];
}

export interface MemoIntakeItem {
  ticker: string;
  state: ItemState | string;
  artifact_id?: string | null;
  decision?: string | null;
}

export interface MemoCurrent {
  status: StageStatus | string;
  intake: MemoIntakeItem[];
}

export const runScreener = () => post<RunStartResponse>('/workflows/screener/run');
export const getScreener = () => fetchJSON<ScreenerCurrent>('/workflows/screener/current');
export const selectScreener = (ticker: string, action: SelectionAction) =>
  post<ScreenerCurrent>('/workflows/screener/selection', { ticker, action });

export const runThesis = () => post<RunStartResponse>('/workflows/thesis/run');
export const getThesis = () => fetchJSON<ThesisCurrent>('/workflows/thesis/current');
export const selectThesis = (ticker: string, action: SelectionAction) =>
  post<ThesisCurrent>('/workflows/thesis/selection', { ticker, action });

export const runIC = () => post<RunStartResponse>('/workflows/ic/run');
export const getIC = () => fetchJSON<ICCurrent>('/workflows/ic/current');
export const overrideIC = (ticker: string, action: 'promote' | 'remove') =>
  post<ICCurrent>('/workflows/ic/override', { ticker, action });

export const runMemo = (ticker?: string) =>
  post<RunStartResponse>('/workflows/memo/run', ticker ? { ticker } : {});
export const getMemo = () => fetchJSON<MemoCurrent>('/workflows/memo/current');

export const runPipeline = () => post<RunStartResponse>('/workflows/pipeline/run');

export const getRun = (runId: string) =>
  fetchJSON<RunDetail>(`/runs/${encodeURIComponent(runId)}`);

export const getRuns = (limit = 30) =>
  fetchJSON<RunSummary[]>(`/runs?limit=${limit}`);

export const directedResearch = (ticker: string, capability: 'thesis' | 'memo') =>
  post<RunStartResponse>('/research/directed', { ticker, capability });

/* ════════════════════════ Company Page ════════════════════════ */

export interface CompanyIdentity {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  industry?: string | null;
  price?: number | null;
  latest_stage?: string | null;
  latest_verdict?: string | null;
  owned?: boolean;
  entity_id?: string;
  status?: string | null;
  status_reason?: string | null;
}

/** One enriched milestone number — label is human text, value may be pre-formatted. */
export interface MilestoneKeyNumber {
  label: string;
  value: string | number | null;
}

/** Enriched milestone detail payload (may also arrive JSON-encoded as a string). */
export interface MilestoneDetail {
  key_numbers?: MilestoneKeyNumber[];
  run_id?: string | null;
  constitution_version?: string | null;
  constitution_version_id?: string | null;
  [key: string]: unknown;
}

export interface LaneMilestone {
  date: string;
  title: string;
  status?: string | null;
  artifact_id?: string | null;
  kind?: string;
  summary?: string | null;
  detail?: string | MilestoneDetail | null;
}

export interface CompanyLane {
  lane: 'screener' | 'thesis' | 'ic_review' | 'memo' | 'portfolio' | string;
  milestones: LaneMilestone[];
}

export interface CompanyResponse {
  identity: CompanyIdentity;
  lanes: CompanyLane[];
}

export interface FinancialPeriod {
  period_end: string;
  metrics: Record<string, number | null>;
}

export interface SnapshotBasis {
  period_end: string;
  period_type: string;
  stale?: boolean;
}

export interface StatementBlock {
  periods?: FinancialPeriod[];
  income?: FinancialPeriod[];
  balance?: FinancialPeriod[];
  cashflow?: FinancialPeriod[];
}

export interface FinancialsCoverage {
  sections: Record<string, { available: boolean; metric_count: number }>;
  snapshot: Record<string, string>;
  notes: string[];
}

export interface CompanyFinancialsResponse {
  snapshot?: Record<string, number | null>;
  snapshot_basis?: Record<string, SnapshotBasis | null>;
  annual?: StatementBlock;
  quarterly?: StatementBlock;
  as_of?: string | null;
  coverage?: FinancialsCoverage;
}

export interface ThesisWatchItem {
  id: string;
  title: string;
  item_type: 'assumption' | 'return_driver' | 'risk' | 'kill_criterion' | string;
  status: 'intact' | 'watch' | 'broken' | 'unknown' | 'data_gap' | string;
  metric?: string | null;
  comparator?: string | null;
  threshold?: number | string | null;
  current_value?: number | string | null;
  lookback?: string | null;
  cadence?: string | null;
  last_checked_at?: string | null;
  data_gap?: boolean;
  why_matters?: string | null;
}

export interface ThesisHealthResponse {
  summary_label: 'Intact' | 'Watching' | 'Broken' | 'Not Checked' | string | null;
  active_source: { memo_artifact_id: string; memo_date?: string | null } | null;
  items: ThesisWatchItem[];
  history?: {
    refresh_id?: string;
    ran_at: string;
    metadata_only?: boolean;
    trigger?: string;
  }[];
  filings_last_checked?: string | null;
  recalculated_at?: string | null;
  empty_reason?: string | null;
}

export const getCompany = (ticker: string) =>
  fetchJSON<CompanyResponse>(`/company/${encodeURIComponent(ticker)}`);

export const getCompanyFinancials = (ticker: string) =>
  fetchJSON<CompanyFinancialsResponse>(
    `/company/${encodeURIComponent(ticker)}/financials`,
  );

export const getThesisHealth = (ticker: string) =>
  fetchJSON<ThesisHealthResponse>(
    `/company/${encodeURIComponent(ticker)}/thesis-health`,
  );

/* ════════════════════════ Bulk data sync (ADR-0059) ════════════════════════ */

/** Bootstrap progress payload — providers may report a fraction, bytes, or both. */
export interface SyncProgress {
  pct?: number | null;
  bytes?: number | null;
  total_bytes?: number | null;
  note?: string | null;
  [key: string]: unknown;
}

export interface SyncBootstrap {
  done: boolean;
  stage?: string | null;
  progress?: number | SyncProgress | null;
  error?: string | null;
}

export interface SyncCounts {
  facts?: number | null;
  prices_tickers?: number | null;
  prices_rows?: number | null;
  filings?: number | null;
  ownership?: number | null;
}

export interface SyncStatus {
  bootstrap: SyncBootstrap;
  last_daily_tick?: string | null;
  last_bulk_refresh?: string | null;
  universe: { name?: string | null; count?: number | null };
  counts: SyncCounts;
  cache_size_mb?: number | null;
}

export const getSync = () => fetchJSON<SyncStatus>('/sync');

/** One-time full download: companyfacts + price history + ownership. */
export const startBootstrap = () => post<{ started: boolean }>('/sync/bootstrap');

/** Manual daily tick: index files → filings → top-ups → prices → health. */
export const runDailySync = () => post<{ started: boolean }>('/sync/daily');

export type PriceRange = '1m' | '6m' | '1y' | '5y';

export interface PricePoint {
  date: string;
  close: number;
  volume?: number | null;
}

export interface PricesResponse {
  ticker: string;
  range: string;
  prices: PricePoint[];
  empty_reason?: string | null;
}

export const getPrices = (ticker: string, range: PriceRange = '1y') =>
  fetchJSON<PricesResponse>(
    `/company/${encodeURIComponent(ticker)}/prices?range=${range}`,
  );

export interface InsiderTransaction {
  as_of: string;
  owner_name?: string | null;
  owner_role?: string | null;
  txn_type?: string | null;
  shares?: number | null;
  value?: number | null;
}

export interface InstitutionalHolding {
  as_of: string;
  owner_name?: string | null;
  shares?: number | null;
  value?: number | null;
}

export interface BeneficialHolder {
  owner_name: string;
  as_of: string;
  shares?: number | null;
  percent?: number | null;
  form?: string | null;
}

export interface OwnershipResponse {
  insiders: InsiderTransaction[];
  largest_holders?: BeneficialHolder[];
  institutions?: InstitutionalHolding[];
  empty_reason?: string | null;
  // Panel-level reasons so an empty 13D/G or 13F section explains itself instead
  // of silently vanishing (the empty_reason above fires only when ALL ownership
  // is empty).
  holders_reason?: string | null;
  institutions_reason?: string | null;
}

export const getOwnership = (ticker: string) =>
  fetchJSON<OwnershipResponse>(
    `/company/${encodeURIComponent(ticker)}/ownership`,
  );

/* ════════════════════ Market context (events, peers, macro) ════════════════════ */

export interface CompanyEvent {
  date: string;
  kind: string;
  label: string;
  detail?: string | null;
  source?: string | null;
}

export const getCompanyEvents = (ticker: string) =>
  fetchJSON<{ ticker: string; events: CompanyEvent[]; empty_reason?: string | null }>(
    `/company/${encodeURIComponent(ticker)}/events`,
  );

export interface PeerRow {
  ticker: string;
  name: string;
  is_subject: boolean;
  [metric: string]: unknown;
}

export const getCompanyPeers = (ticker: string) =>
  fetchJSON<{ ticker: string; metrics: string[]; na_metrics?: string[]; peers: PeerRow[] }>(
    `/company/${encodeURIComponent(ticker)}/peers`,
  );

export const runCompanyResearch = (ticker: string, kind: 'risk_diff' | 'mdna_note') =>
  post<{ ok: boolean; artifact_id: string; title: string }>(
    `/company/${encodeURIComponent(ticker)}/research`,
    { kind },
  );

export interface UpcomingEvent {
  ticker: string;
  date: string;
  kind: string;
  label: string;
}

export const getUpcomingEvents = () =>
  fetchJSON<{ events: UpcomingEvent[] }>('/events/upcoming');

export interface NewsItem {
  title: string;
  url: string;
  publisher?: string | null;
  published?: string | null;
}

export const getCompanyNews = (ticker: string) =>
  fetchJSON<{ ticker: string; items: NewsItem[]; live: boolean; note: string }>(
    `/company/${encodeURIComponent(ticker)}/news`,
  );

export interface FulltextHit {
  company?: string | null;
  ticker?: string | null;
  cik?: string | null;
  form?: string | null;
  filed?: string | null;
  accession?: string | null;
  in_universe: boolean;
  known: boolean;
}

export const searchFilingsFulltext = (q: string, forms?: string) =>
  fetchJSON<{ query: string; hits: FulltextHit[]; ok: boolean; total?: number | null; note: string }>(
    `/research/fulltext?q=${encodeURIComponent(q)}${forms ? `&forms=${encodeURIComponent(forms)}` : ''}`,
  );

export interface MacroEntry {
  series: string;
  label: string;
  value: number | null;
  display: string;
  as_of: string | null;
  // Distinguishes "never cached" from "last fetch failed" (populated by the
  // macro sync; null when the series has never been attempted or last succeeded).
  last_sync_error?: string | null;
  last_sync_at?: string | null;
}

export const getMacro = () => fetchJSON<{ series: MacroEntry[] }>('/macro');

/* ════════════════════════ Home briefing ════════════════════════ */

export interface BriefingResponse {
  date: string;
  filings: { ticker: string; form: string; label: string; filed_at: string }[];
  health: { broken: string[]; watching: string[]; intact: number; unchecked: number };
  learning_ready: number;
  learning?: { ready: number; evaluations: number; patterns: number };
  pending_proposal: { id: string; summary?: string | null } | null;
  running: { id: string; kind: string; started_at?: string | null }[];
  events: UpcomingEvent[];
  macro: MacroEntry[];
  watch_total: number;
}

export const getBriefing = () => fetchJSON<BriefingResponse>('/home/briefing');

/* ════════════════════════ Watchlists & themes ════════════════════════ */

export interface WatchlistRow {
  ticker: string;
  name?: string | null;
  price?: number | null;
  momentum_3m?: number | null;
  pe?: number | null;
  fcf_yield?: number | null;
  market_cap?: number | null;
  owned: boolean;
  thesis_health?: string | null;
}

export interface Watchlist {
  id: string;
  name: string;
  kind: 'watchlist' | 'theme' | string;
  note?: string | null;
  tickers: string[];
  rows?: WatchlistRow[];
}

export const listWatchlists = () =>
  fetchJSON<{ watchlists: Watchlist[] }>('/watchlists');

export const createWatchlist = (name: string, kind: string = 'watchlist', tickers: string[] = []) =>
  post<Watchlist>('/watchlists', { name, kind, tickers });

export const deleteWatchlist = (id: string) =>
  fetchJSON<{ ok: boolean }>(`/watchlists/${id}`, { method: 'DELETE' });

export const addWatchlistTicker = (id: string, ticker: string) =>
  post<Watchlist>(`/watchlists/${id}/tickers`, { ticker });

export const removeWatchlistTicker = (id: string, ticker: string) =>
  fetchJSON<Watchlist>(`/watchlists/${id}/tickers/${encodeURIComponent(ticker)}`, {
    method: 'DELETE',
  });

/* ════════════════════════ Research Hub ════════════════════════ */

export interface SectorNode {
  sector: string;
  count: number;
  industries: { industry: string; count: number }[];
}

export const getSectors = () => fetchJSON<{ sectors: SectorNode[] }>('/research/sectors');

export interface IndustryAggregate {
  median: number | null;
  p25: number | null;
  p75: number | null;
  coverage: number;
}

export interface IndustryDashboard {
  group: string;
  sector?: string | null;
  industry?: string | null;
  size: number;
  with_data: number;
  aggregates: Record<string, IndustryAggregate>;
  market_cap_breakdown: { bucket: string; count: number }[];
  pe_distribution: { bucket: string; count: number }[];
  margin_trend: { year: string; median: number; coverage: number }[];
  insider_buys_90d: number;
  constituents: Record<string, unknown>[];
  constituent_metrics: string[];
  aggregate_metrics?: string[];
  trend_metric?: string;
  trend_label?: string;
  na_metrics?: string[];
}

export const getIndustryDashboard = (params: { sector?: string; industry?: string }) => {
  const qs = new URLSearchParams();
  if (params.sector) qs.set('sector', params.sector);
  if (params.industry) qs.set('industry', params.industry);
  return fetchJSON<IndustryDashboard>(`/research/industry?${qs.toString()}`);
};

export const getThemeDashboard = (watchlistId: string) =>
  fetchJSON<IndustryDashboard>(`/research/theme/${watchlistId}`);

export const startResearchRun = (body: {
  kind: string;
  sector?: string;
  industry?: string;
  watchlist_id?: string;
  tickers?: string[];
  label?: string;
}) =>
  post<{ ok: boolean; artifact_id: string; title: string }>('/research/runs', body);

export interface ThematicResult {
  ok: boolean;
  artifact_id?: string;
  title?: string;
  tickers?: string[];
  scope?: { deep_read: number; selected: number; discovered: number };
  note?: string;
  discovered?: number;
}

/** Thematic deep research: theme → discover companies → deep-read 10-Ks →
 * synthesize a cited report. SEC-only, bounded. Slow on agent_cli. */
export const runThematicResearch = (query: string, limit?: number) =>
  post<ThematicResult>('/research/thematic', { query, ...(limit ? { limit } : {}) });

export interface ResearchNote {
  id: string;
  kind: string;
  ticker?: string | null;
  created_at: string;
  title: string;
}

export const getResearchNotes = () =>
  fetchJSON<{ notes: ResearchNote[] }>('/research/notes');

/* ════════════════════════ Portfolio analytics ════════════════════════ */

export interface PortfolioPerformance {
  range: string;
  benchmark: string;
  benchmark_label: string;
  portfolio_return: number | null;
  benchmark_return: number | null;
  excess_return: number | null;
  portfolio_series: { date: string; indexed: number }[];
  benchmark_series: { date: string; indexed: number }[];
  benchmark_available: boolean;
  note?: string | null;
}

export interface PortfolioAnalytics {
  performance: PortfolioPerformance;
  contribution: {
    ticker: string;
    sector?: string | null;
    unrealized_pnl: number;
    realized_pnl: number;
    total_pnl: number;
    contribution_pp: number | null;
    weight?: number | null;
    exited?: boolean;
  }[];
  exposure: {
    sectors: { sector: string; weight: number | null; over_threshold?: boolean }[];
    top_position_weight: number | null;
    top3_weight: number | null;
    positions: number;
    concentration_flag_pct?: number;
    flags?: string[];
  };
  risk: {
    range: string;
    max_drawdown: number | null;
    volatility?: number;
    beta?: number;
    correlation?: number;
    note?: string;
  };
  decisions: {
    events_measured: number;
    min_age_days: number;
    promoted_avg_return: number | null;
    dismissed_avg_return: number | null;
    recent: {
      ticker: string;
      action: string;
      capability: string;
      date: string;
      forward_return: number;
      days: number;
    }[];
    note: string;
  };
  factor_tilts: {
    factor: string;
    label: string;
    metric: string;
    percentile: number | null;
    coverage: number | null;
  }[];
}

export const getPortfolioAnalytics = (range: string = '1y') =>
  fetchJSON<PortfolioAnalytics>(`/portfolio/analytics?range=${range}`);

/** CSV export URLs (plain downloads). */
export const exportUrls = {
  portfolio: `${BASE}/export/portfolio.csv`,
  screener: `${BASE}/export/screener.csv`,
  financials: (ticker: string, periodType: string = 'annual') =>
    `${BASE}/export/financials/${encodeURIComponent(ticker)}.csv?period_type=${periodType}`,
  industry: (params: { sector?: string; industry?: string }) => {
    const qs = new URLSearchParams();
    if (params.sector) qs.set('sector', params.sector);
    if (params.industry) qs.set('industry', params.industry);
    return `${BASE}/export/industry.csv?${qs.toString()}`;
  },
};

/* ════════════════════════ Artifacts ════════════════════════ */

/** Structured table inside a memo section: `sections[].tables[name]`. */
export interface ArtifactSectionTable {
  columns: string[];
  rows: (string | number | null)[][];
}

/** Labeled figure inside a memo section: `sections[].key_figures[]`. */
export interface ArtifactKeyFigure {
  label: string;
  value: string | number | null;
}

export interface ArtifactResponse {
  id: string;
  kind: string;
  ticker?: string | null;
  created_at: string;
  schema_version?: number | string;
  payload: Record<string, unknown>;
  rendered_md?: string | null;
  constitution_version_id?: string | null;
  evidence_bundle_id?: string | null;
  run_id?: string | null;
}

export const getArtifact = (artifactId: string) =>
  fetchJSON<ArtifactResponse>(`/artifacts/${encodeURIComponent(artifactId)}`);

/** URL for the markdown export of an artifact (use as href/download target). */
export const artifactExportUrl = (artifactId: string, format = 'md') =>
  `${BASE}/artifacts/${encodeURIComponent(artifactId)}/export?format=${format}`;

/* ════════════════════════ Library ════════════════════════ */

export interface LibrarySuggestResponse {
  matches: { ticker: string; name?: string | null }[];
}

export const librarySuggest = (q: string) =>
  fetchJSON<LibrarySuggestResponse>(`/library/suggest?q=${encodeURIComponent(q)}`);

/* ════════════════════════ Portfolio ════════════════════════ */

export interface HoldingFlag {
  kind: string;
  detail?: string | null;
}

export interface HoldingRow {
  ticker: string;
  shares: number;
  avg_cost: number;
  price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  weight?: number | null;
  position_type?: string | null;
  coverage_state?:
    | 'covered'
    | 'queued'
    | 'running'
    | 'stale'
    | 'failed'
    | 'none'
    | string
    | null;
  thesis_health_label?: string | null;
  flags?: HoldingFlag[];
}

export interface PortfolioTotals {
  market_value?: number | null;
  cost_basis?: number | null;
  unrealized_pnl?: number | null;
  realized_pnl?: number | null;
  positions?: number;
}

export interface PortfolioResponse {
  holdings: HoldingRow[];
  totals: PortfolioTotals;
}

export interface AddLotInput {
  ticker: string;
  shares: number;
  cost_basis: number;
  purchase_date: string;
  position_type?: string;
  note?: string;
}

export interface RecordSaleInput {
  ticker: string;
  shares: number;
  price: number;
  sale_date: string;
  note?: string;
}

export interface CorrectLotInput {
  shares?: number;
  cost_basis?: number;
  purchase_date?: string;
  remove?: boolean;
}

export interface LedgerResponse {
  lots: Record<string, unknown>[];
  sales: Record<string, unknown>[];
}

export const getPortfolio = () => fetchJSON<PortfolioResponse>('/portfolio');

export const addLot = (input: AddLotInput) =>
  post<{ lot_id: string }>('/portfolio/lots', input);

export const recordSale = (input: RecordSaleInput) =>
  post<{ sale_id: string; realized_pnl: number }>('/portfolio/sales', input);

export const correctLot = (lotId: string, input: CorrectLotInput) =>
  post<{ ok: boolean }>(
    `/portfolio/lots/${encodeURIComponent(lotId)}/correct`,
    input,
  );

export const refreshPortfolio = () => post<{ updated: number }>('/portfolio/refresh');

export const getLedger = (ticker?: string) =>
  fetchJSON<LedgerResponse>(
    `/portfolio/ledger${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ''}`,
  );

/* ════════════════════════ Monitoring (thesis health actions) ════════════════════════ */

export interface MonitoringDueResponse {
  due: number;
  tickers: string[];
}

export interface MonitoringRefreshResponse {
  refreshed: {
    ticker: string;
    metadata_only?: boolean;
    summary_label?: string | null;
  }[];
}

export const getMonitoringDue = () =>
  fetchJSON<MonitoringDueResponse>('/monitoring/due');

export const refreshMonitoring = () =>
  post<MonitoringRefreshResponse>('/monitoring/refresh');

/* ════════════════════════ Dashboard ════════════════════════ */

export interface DashboardResponseOption {
  code?: string;
  response?: string;
  label?: string;
  kind?: string;
}

export type ResponseSetEntry = string | DashboardResponseOption;

export interface DashboardItem {
  id: string;
  kind: 'decision' | 'attention' | string;
  section: 'needs_decision' | 'portfolio_review' | 'needs_attention' | string;
  source_type?: string | null;
  source_id?: string | null;
  ticker?: string | null;
  title: string;
  body?: string | null;
  severity?: 'high' | 'medium' | 'low' | string | null;
  rank_source?: string | null;
  evidence_refs?: unknown;
  response_set?: ResponseSetEntry[];
  created_at?: string;
}

export interface ActivityRow {
  kind: string;
  title: string;
  ticker?: string | null;
  run_id?: string | null;
  artifact_id?: string | null;
  created_at?: string;
}

export interface DashboardResponse {
  needs_decision: DashboardItem[];
  portfolio_review: {
    pressure: DashboardItem[];
    opportunities: DashboardItem[];
    stale?: boolean;
  };
  needs_attention: DashboardItem[];
  recent_activity: ActivityRow[];
}

export const getDashboard = () => fetchJSON<DashboardResponse>('/dashboard');

export const respondDashboard = (
  itemId: string,
  response: string,
  payload?: Record<string, unknown>,
) =>
  post<{ ok: boolean; status?: string }>(
    `/dashboard/items/${encodeURIComponent(itemId)}/respond`,
    payload ? { response, payload } : { response },
  );

export const refreshDashboard = () => post<{ ok: boolean }>('/dashboard/refresh');

/* ════════════════════════ Learning ════════════════════════ */

export interface LearningRecord {
  id?: string;
  kind?: string;
  entity?: string | null;
  ticker?: string | null;
  window_months?: number | null;
  payload?: Record<string, unknown>;
  confidence_label?:
    | 'exploratory'
    | 'promising'
    | 'recommendation_ready'
    | 'superseded'
    | 'inconclusive'
    | string;
  lineage?: unknown;
  superseded_by?: string | null;
  created_at?: string;
}

export interface LearningResponse {
  outcome_evaluations: LearningRecord[];
  recommendations: LearningRecord[];
  findings: LearningRecord[];
  responses: LearningRecord[];
  summary?: { counts?: Record<string, number> };
}

export const getLearning = () => fetchJSON<LearningResponse>('/learning');

export const runLearning = () => post<{ created: number }>('/learning/evaluate');

/* ════════════════════════ Settings ════════════════════════ */

export interface AiUsageRow {
  capability?: string;
  model?: string;
  calls?: number;
  tokens_in?: number;
  tokens_out?: number;
  est_cost?: number | null;
}

export interface ScheduleEntry {
  name?: string;
  label?: string;
  capability?: string;
  cadence?: string;
  cron?: string;
  time?: string;
  enabled?: boolean;
  [key: string]: unknown;
}

export interface AgentCliConfig {
  preset?: 'claude' | 'codex' | 'custom' | string;
  command?: string[] | string | null;
  timeout_s?: number;
  [key: string]: unknown;
}

export interface DataConfig {
  universe_default?: string;
  price_history_years?: number;
  holdings_price_history_years?: number;
  cache_dir?: string | null;
  ownership_ingest?: boolean;
  [key: string]: unknown;
}

export interface SettingsConfig {
  ai?: {
    provider?: 'openai' | 'agent_cli' | string;
    provider_id?: string;
    base_url?: string | null;
    agent_cli?: AgentCliConfig;
    fast_model?: string;
    deep_model?: string;
    model_fast?: string;
    model_deep?: string;
    key_env?: string;
    [key: string]: unknown;
  };
  providers?: {
    sec_user_agent?: string;
    web_search?: boolean;
    [key: string]: unknown;
  };
  data?: DataConfig;
  sec_user_agent?: string;
  web_search_enabled?: boolean;
  schedules?: ScheduleEntry[] | Record<string, string | boolean | null>;
  [key: string]: unknown;
}

export interface AiProviderPreset {
  id: string;
  label: string;
  base_url: string | null;
  model_fast: string;
  model_deep: string;
  requires_key: boolean;
  env: string | null;
  key_hint: string;
  console_url: string | null;
}

export interface AutomationHint {
  command: string;
  cwd: string;
  cron: Record<string, string>;
}

export interface WebSearchProviderStatus {
  id: string;
  label: string;
  env: string | null;
  console_url: string | null;
  key_present: boolean;
}

export interface WebSearchStatus {
  enabled: boolean;
  active_provider: string | null;
  providers: WebSearchProviderStatus[];
}

export interface SettingsResponse {
  config: SettingsConfig;
  health: Partial<HealthResponse> & Record<string, unknown>;
  ai_providers?: AiProviderPreset[];
  ai_key_present?: Record<string, boolean>;
  web_search?: WebSearchStatus;
  automation?: AutomationHint;
  ai_usage?:
    | AiUsageRow[]
    | {
        rows?: AiUsageRow[];
        total_est_cost?: number | null;
        [key: string]: unknown;
      };
}

export interface TestAIResponse {
  ok: boolean;
  model?: string;
  error?: string;
}

export const getSettings = () => fetchJSON<SettingsResponse>('/settings');

export const saveSettings = (updates: Record<string, unknown>) =>
  post<{ config: SettingsConfig }>('/settings', { updates });

export const testAI = () => post<TestAIResponse>('/settings/test-ai');

/** Store (or clear, with an empty key) a provider's API key in the local
 * credential store. Never persisted to the workspace DB or config.yaml. */
export const saveApiKey = (providerId: string, key: string) =>
  post<{ ok: boolean; provider_id: string; key_present: boolean }>('/settings/api-key', {
    provider_id: providerId,
    key,
  });

/** Destructive: removes workflow outputs; preserves constitution + portfolio. */
export const clearPipelineData = () => post<{ ok: boolean }>('/settings/clear-pipeline');

/** Destructive: removes constitution versions/proposals/derived settings. */
export const resetConstitution = () =>
  post<{ ok: boolean }>('/settings/reset-constitution');

/** URL for the workspace data export download. */
export const settingsExportUrl = `${BASE}/settings/export`;

export interface ExportEstimate {
  approx_bytes: number;
  total_rows: number;
  excluded_tables: string[];
}

export const getExportEstimate = () => fetchJSON<ExportEstimate>('/settings/export/estimate');
