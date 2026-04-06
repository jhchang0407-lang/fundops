const BASE = '/api';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  // Dashboard
  dashboard: () => fetchJSON<any>('/dashboard'),

  // Screener
  runScreener: () => fetchJSON<any>('/screener/run', { method: 'POST' }),
  screenerResults: () => fetchJSON<any>('/screener/results'),

  // Thesis
  listTheses: () => fetchJSON<any>('/thesis'),
  runThesis: (ticker: string) => fetchJSON<any>(`/thesis/${ticker}`, { method: 'POST' }),
  runThesisBatch: (tickers: string[]) => fetchJSON<any>('/thesis/batch', { method: 'POST', body: JSON.stringify({ tickers }) }),
  getThesis: (ticker: string) => fetchJSON<any>(`/thesis/${ticker}`),

  // IC Review
  listICReviews: () => fetchJSON<any>('/ic-review'),
  runICReview: (ticker: string) => fetchJSON<any>(`/ic-review/${ticker}`, { method: 'POST' }),
  runICBatch: (tickers: string[]) => fetchJSON<any>('/ic-review/batch', { method: 'POST', body: JSON.stringify({ tickers }) }),
  getICReview: (ticker: string) => fetchJSON<any>(`/ic-review/${ticker}`),
  overrideICReview: (ticker: string, note?: string) => fetchJSON<any>(`/ic-review/${ticker}/override`, { method: 'POST', body: JSON.stringify({ note }) }),
  dismissTicker: (ticker: string, reason?: string) => fetchJSON<any>(`/research/dismiss/${ticker}`, { method: 'POST', body: JSON.stringify({ reason }) }),
  promoteTicker: (ticker: string) => fetchJSON<any>(`/research/promote/${ticker}`, { method: 'POST' }),

  // Approved (IC-passed, ready for memos)
  listApproved: () => fetchJSON<any>('/research/approved'),
  generateResearchReport: (ticker: string) => fetchJSON<any>(`/research/report/${ticker}`, { method: 'POST' }),
  generateInvestmentMemo: (ticker: string) => fetchJSON<any>(`/research/memo/${ticker}`, { method: 'POST' }),

  // Library
  getMemos: (search?: string) => fetchJSON<any>(`/library/memos${search ? `?search=${search}` : ''}`),
  getMemo: (ticker: string) => fetchJSON<any>(`/library/memos/${ticker}`),

  // Portfolio
  runPortfolio: () => fetchJSON<any>('/portfolio/run', { method: 'POST' }),
  portfolioStatus: () => fetchJSON<any>('/portfolio/status'),
  getPortfolio: () => fetchJSON<any>('/portfolio'),
  savePositions: (positions: { ticker: string; shares: number; cost_basis: number; date?: string; type?: string }[], cash?: number) =>
    fetchJSON<any>('/portfolio/positions', { method: 'POST', body: JSON.stringify({ positions, cash }) }),
  // Allocator
  runAllocator: () => fetchJSON<any>('/allocator/run', { method: 'POST' }),
  allocatorRecs: () => fetchJSON<any>('/allocator/recommendations'),
  discussPosition: (ticker: string, message: string, history: {role: string; content: string}[] = [], context: Record<string, any> = {}) =>
    fetchJSON<any>(`/allocator/${ticker}/discuss`, { method: 'POST', body: JSON.stringify({ message, history, context }) }),
  recordAllocatorAction: (ticker: string, action: string, reason?: string) =>
    fetchJSON<any>(`/allocator/${ticker}/action`, { method: 'POST', body: JSON.stringify({ action, reason }) }),

  // Pipeline
  runPipeline: () => fetchJSON<any>('/pipeline/run', { method: 'POST' }),
  pipelineStatus: () => fetchJSON<any>('/pipeline/status'),
  pipelineHistory: () => fetchJSON<any>('/pipeline/history'),

  // Pipeline Approvals
  listPendingApprovals: () => fetchJSON<any>('/pipeline/pending'),
  approvePending: (id: number) => fetchJSON<any>(`/pipeline/pending/${id}/approve`, { method: 'POST' }),
  rejectPending: (id: number, reason?: string) =>
    fetchJSON<any>(`/pipeline/pending/${id}/reject?reason=${encodeURIComponent(reason || '')}`, { method: 'POST' }),

  // Review & Evidence
  getReviewData: (ticker: string) => fetchJSON<any>(`/review/${ticker}`),
  getEvidence: (ticker: string) => fetchJSON<any>(`/evidence/${ticker}`),

  // Ticker
  tickerDetail: (ticker: string) => fetchJSON<any>(`/ticker/${ticker}`),
  tickerTimeline: (ticker: string) => fetchJSON<any>(`/ticker/${ticker}/timeline`),

  // Jobs
  jobStatus: (id: string) => fetchJSON<any>(`/jobs/${id}`),
  listJobs: () => fetchJSON<any>('/jobs'),
  cancelJob: (id: string) => fetchJSON<any>(`/jobs/${id}/cancel`, { method: 'POST' }),

  // Costs
  getCosts: () => fetchJSON<any>('/costs'),

  // Config
  getConfig: () => fetchJSON<any>('/config'),
  testConnection: (source: string) => fetchJSON<any>(`/config/test-connection?source=${source}`, { method: 'POST' }),
  getPresets: () => fetchJSON<any>('/config/presets'),

  // Config save
  saveConfig: (section: string, values: Record<string, any>) =>
    fetchJSON<any>('/config/save', { method: 'POST', body: JSON.stringify({ section, values }) }),

  // Screener config
  getScreenerConfig: () => fetchJSON<any>('/screener/config'),
  saveScreenerConfig: (criteria: any) =>
    fetchJSON<any>('/screener/config', { method: 'POST', body: JSON.stringify({ criteria }) }),
  strategyWizard: (message: string, history: { role: string; content: string }[] = [], currentFilters: Record<string, any> = {}) =>
    fetchJSON<any>('/screener/wizard', { method: 'POST', body: JSON.stringify({ message, history, current_filters: currentFilters }) }),
  getScreenerFilters: () => fetchJSON<any>('/config/screener-filters'),
  saveScreenerFilters: (filters: any, preset?: string) =>
    fetchJSON<any>('/config/screener-filters', { method: 'POST', body: JSON.stringify({ filters, preset }) }),

  // Universe
  getUniverses: () => fetchJSON<any>('/config/universes'),
  getUniverseTickers: (name: string) => fetchJSON<any>(`/config/universe/${name}`),
  setUniverse: (data: { preset?: string; custom_tickers?: string }) =>
    fetchJSON<any>('/config/universe', { method: 'POST', body: JSON.stringify(data) }),

  // Strategy v2
  getStrategy: () => fetchJSON<any>('/strategy'),
  listStrategies: () => fetchJSON<any>('/strategy/list'),
  strategyConversation: (message: string, history: { role: string; content: string }[] = [], strategyId?: string, sessionId?: string) =>
    fetchJSON<any>('/strategy/conversation', { method: 'POST', body: JSON.stringify({ message, history, strategy_id: strategyId, session_id: sessionId }) }),
  getConversationHistory: (strategyId?: string, sessionId?: string) =>
    fetchJSON<any>(`/strategy/conversation/history${strategyId ? `?strategy_id=${strategyId}` : ''}${sessionId ? `${strategyId ? '&' : '?'}session_id=${sessionId}` : ''}`),
  saveStrategy: (profile: any, name?: string) =>
    fetchJSON<any>('/strategy/save', { method: 'POST', body: JSON.stringify({ profile, name }) }),
  getStrategyVersions: (strategyId: string) => fetchJSON<any>(`/strategy/${strategyId}/versions`),
  regenerateScoring: (strategyId: string) =>
    fetchJSON<any>(`/strategy/${strategyId}/regenerate`, { method: 'POST' }),
  resetConstitution: () => fetchJSON<any>('/strategy/reset', { method: 'POST' }),
  clearPipelineData: () => fetchJSON<any>('/config/clear-pipeline', { method: 'POST' }),

  // Constitution
  getConstitution: () => fetchJSON<any>('/constitution'),
  getConstitutionChangelog: () => fetchJSON<any>('/constitution/changelog'),

  // Judgment Events
  getTickerEvents: (ticker: string) => fetchJSON<any>(`/events/ticker/${ticker}`),
  getEventChain: (eventId: number) => fetchJSON<any>(`/events/chain/${eventId}`),
  getRecentEvents: (limit?: number) => fetchJSON<any>(`/events/recent${limit ? `?limit=${limit}` : ''}`),

  // Library
  findSimilar: (ticker: string, sector?: string) => fetchJSON<any>(`/library/similar/${ticker}${sector ? `?sector=${sector}` : ''}`),
  getLibraryTicker: (ticker: string) => fetchJSON<any>(`/library/ticker/${ticker}`),
  getLibraryStats: () => fetchJSON<any>('/library/stats'),

  // Feedback Loop (Loop 1)
  getRefinementProposals: () => fetchJSON<any>('/strategy/refinement-proposals'),
  generateRefinementProposals: () => fetchJSON<any>('/strategy/refinement-proposals/generate', { method: 'POST' }),
  acceptRefinement: (proposalId: string) => fetchJSON<any>(`/strategy/refinement-proposals/${proposalId}/accept`, { method: 'POST' }),
  rejectRefinement: (proposalId: string) => fetchJSON<any>(`/strategy/refinement-proposals/${proposalId}/reject`, { method: 'POST' }),

  // Behavioral Mirror (Loop 2)
  getMirror: () => fetchJSON<any>('/strategy/mirror'),
  proposeMirrorUpdate: () => fetchJSON<any>('/strategy/mirror/propose-update', { method: 'POST' }),
  applyMirrorUpdate: (changes: Record<string, any>, proposal?: string) =>
    fetchJSON<any>('/strategy/mirror/apply-update', { method: 'POST', body: JSON.stringify({ changes, proposal }) }),

  // Screener v2
  runScreenerV2: (strategyId?: string) =>
    fetchJSON<any>('/screener/v2/run', { method: 'POST', body: JSON.stringify(strategyId ? { strategy_id: strategyId } : {}) }),
  screenerV2Results: () => fetchJSON<any>('/screener/v2/results'),
  recordFeedback: (data: { screener_run_id: string; ticker: string; feedback: string; dismiss_reason?: string; note?: string; score_at_feedback?: number; rank_at_feedback?: number }) =>
    fetchJSON<any>('/screener/v2/feedback', { method: 'POST', body: JSON.stringify(data) }),
  getRunFeedback: (runId: string) => fetchJSON<any>(`/screener/v2/feedback/${runId}`),

  // Learning (richer endpoints from learning.py)
  getLearningProposals: () => fetchJSON<any>('/learning/proposals'),
  resolveLearningProposal: (id: string, action: 'accept' | 'reject', reason?: string) =>
    fetchJSON<any>(`/learning/proposals/${id}`, { method: 'POST', body: JSON.stringify({ action, reason }) }),
  getLearningDrift: () => fetchJSON<any>('/learning/drift'),
  getLearningOutcomes: (ticker?: string, limit?: number) =>
    fetchJSON<any>(`/learning/outcomes${ticker || limit ? '?' : ''}${ticker ? `ticker=${ticker}&` : ''}${limit ? `limit=${limit}` : ''}`),
  findSimilarLibrary: (data: { ticker: string; sector?: string; gross_margin?: number; roic?: number; top_k?: number }) =>
    fetchJSON<any>('/library/similar', { method: 'POST', body: JSON.stringify(data) }),
  askLibrary: (question: string, history: { role: string; content: string }[] = []) =>
    fetchJSON<any>('/library/ask', { method: 'POST', body: JSON.stringify({ question, history }) }),
};
