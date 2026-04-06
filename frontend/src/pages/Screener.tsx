import React, { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/PageHeader';
import { pct } from '../utils/formatFinancials';

// ── Types ──────────────────────────────────────────────────────────────

interface ScreenerResult {
  ticker: string;
  symbol?: string;
  companyName?: string;
  company_name?: string;
  sector?: string;
  price?: number;
  score?: number;
  quality?: number;
  cheapness?: number;
  growth?: number;
  momentum?: number;
  margin_expansion?: number;
  expected_return?: number;
  reason?: string;
  feedback?: string;
  dismiss_reason?: string;
  lens?: string;
  top_lens?: string;  // API v2 field name
  // Return decomposition — nested (v2) or flat (legacy)
  return_sources?: { discount?: number; growth?: number; margin?: number; dividends?: number };
  return_discount?: number;
  return_growth?: number;
  return_margin?: number;
  return_dividend?: number;
  // Key financials (snake_case from screener, camelCase from FMP)
  // NOTE: margins/growth are stored as 0-1 decimals from SEC XBRL — multiply ×100 before display
  gross_margin?: number;
  grossProfitMargin?: number;
  operatingMargin?: number;
  roic?: number;
  returnOnInvestedCapital?: number;
  revenue_growth?: number;
  revenueGrowth?: number;
  revenueGrowth3y?: number;
  fcf_yield?: number;
  fcfYield?: number;
  debt_to_equity?: number;
  debtEquity?: number;
  // Momentum / RS — 0-100 percentile rank vs universe (free from yfinance price history)
  rs_3m?: number;
  rs_6m?: number;
  rs_3m_percentile?: number;
  rs_6m_percentile?: number;
  // Derived scoring metrics
  piotroski?: number;
  growth_gap?: number;
  // Data quality (Phase 4)
  data_quality_score?: number;
  data_warnings?: string[];
}

interface ScreenerData {
  results: ScreenerResult[];
  label_map?: Record<string, { label?: string; unit?: string; format?: string }>;
  run_id?: string;
  universe_size?: number;
  scored_count?: number;
  strategy_name?: string;
  status?: string;
  failed_count?: number;
  feedback_count?: number;
}

interface JobStatus {
  status: 'pending' | 'running' | 'complete' | 'completed' | 'failed' | 'cancelled';
  phase?: string;
  phase_number?: number;
  total_phases?: number;
  progress?: number;
  total?: number;
  elapsed?: string;
  message?: string;
}

// ── Constants ──────────────────────────────────────────────────────────

const DISMISS_REASONS = [
  'Too much debt',
  'Cyclical/commodity business',
  'Management concerns',
  'Already own enough in this sector',
  'Too small / too large',
  "Don't understand the business",
  'Valuation already reflects quality',
];

const TOP_N = 20;

// ── Score badge color helper ───────────────────────────────────────────

function getScoreBadgeStyle(score: number): React.CSSProperties {
  // Score may be 0-10 (v2 AI scoring) or 0-100 (basic screener). Normalize to 0-100.
  const s = score <= 10 ? score * 10 : score;
  if (s >= 80) return { background: 'rgba(52,168,83,0.12)', color: 'var(--positive)' };
  if (s >= 70) return { background: 'var(--accent-subtle)', color: 'var(--accent)' };
  if (s >= 60) return { background: 'rgba(251,188,4,0.12)', color: 'var(--warning)' };
  return { background: 'var(--bg-tertiary)', color: 'var(--text-muted)' };
}

// ── Dismiss Modal Component ────────────────────────────────────────────

function DismissModal({
  ticker,
  onDismiss,
  onClose,
}: {
  ticker: string;
  onDismiss: (reason: string) => void;
  onClose: () => void;
}) {
  const [customReason, setCustomReason] = useState('');

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-title" style={{ marginBottom: 8 }}>
          DISMISS {ticker}
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 12 }}>
          Why are you passing on this stock? This helps the system learn your preferences.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {DISMISS_REASONS.map((reason) => (
            <button
              key={reason}
              className="dismiss-reason"
              onClick={() => onDismiss(reason)}
            >
              {reason}
            </button>
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <input
              type="text"
              placeholder="Other reason..."
              value={customReason}
              onChange={(e) => setCustomReason(e.target.value)}
              className="dismiss-reason"
              style={{ flex: 1, cursor: 'text' }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && customReason.trim()) onDismiss(customReason.trim());
              }}
            />
            <button
              onClick={() => { if (customReason.trim()) onDismiss(customReason.trim()); }}
              disabled={!customReason.trim()}
              className="btn btn-accent"
              style={{ fontSize: 'var(--text-xs)', padding: '6px 12px' }}
            >
              Submit
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Expanded Detail (3-card layout) ────────────────────────────────────


function ExpandedDetail({
  row,
  labelMap = {},
  strategyWeights = {},
}: {
  row: ScreenerResult;
  labelMap?: Record<string, { label?: string; unit?: string; format?: string }>;
  strategyWeights?: Record<string, number>;
}) {
  const ticker = row.ticker || row.symbol || '';
  const [thesisStatus, setThesisStatus] = React.useState<'idle' | 'running' | 'queued'>('idle');
  const totalReturn = row.expected_return ?? 0;

  // Return sources: prefer nested return_sources (v2), fall back to flat legacy fields
  const rs = row.return_sources ?? {};
  const discount = rs.discount ?? row.return_discount ?? 0;
  const growth = rs.growth ?? row.return_growth ?? 0;
  const margin = rs.margin ?? row.return_margin ?? 0;
  const dividend = rs.dividends ?? row.return_dividend ?? 0;
  const returnSum = discount + growth + margin + dividend || 1;

  // Strategy-aware KEY FINANCIALS: pick metrics based on strategy weights
  const sw = strategyWeights;
  void ((sw.momentum ?? 0) > 0 || ('momentum' in labelMap)); // hasMomentum check reserved

  // RS percentile: use whichever RS key is available
  const rs3 = row.rs_3m ?? row.rs_3m_percentile;
  const rs6 = row.rs_6m ?? row.rs_6m_percentile;
  const fmtRS = (v: number | undefined | null) =>
    v != null ? `${Math.round(v)}th` : '\u2014';

  // Available metrics pool — each metric with its associated strategy dimension
  const metricPool: { label: string; value: string; dim: string; highlight?: boolean }[] = [
    { label: 'GM', value: pct(row.gross_margin ?? row.grossProfitMargin), dim: 'quality' },
    { label: 'ROIC', value: pct(row.roic ?? row.returnOnInvestedCapital), dim: 'quality' },
    { label: 'Op Margin', value: pct(row.operatingMargin), dim: 'quality' },
    { label: 'Rev Grw', value: pct(row.revenue_growth ?? row.revenueGrowth), dim: 'growth' },
    { label: 'FCF Yld', value: pct(row.fcf_yield ?? row.fcfYield), dim: 'valuation' },
    { label: 'D/E', value: (row.debt_to_equity ?? row.debtEquity) != null ? `${(row.debt_to_equity ?? row.debtEquity)!.toFixed(1)}x` : '\u2014', dim: 'valuation' },
    { label: 'RS 3m', value: fmtRS(rs3), dim: 'momentum', highlight: rs3 != null && rs3 >= 70 },
    { label: 'RS 6m', value: fmtRS(rs6), dim: 'momentum', highlight: rs6 != null && rs6 >= 70 },
  ];

  // Build metric list: pick 5 metrics, prioritized by strategy weight
  // If strategy weights exist, only show metrics from dimensions with weight > 0
  const hasWeights = Object.keys(sw).length > 0;
  let keyMetrics: typeof metricPool;
  if (hasWeights) {
    // Filter to dimensions that have weight > 0, then pick up to 5
    const activeDims = new Set(Object.entries(sw).filter(([, w]) => w > 0).map(([k]) => k));
    // Also include 'cheapness' → 'valuation' mapping
    if (activeDims.has('cheapness')) { activeDims.add('valuation'); activeDims.delete('cheapness'); }
    const filtered = metricPool.filter(m => activeDims.has(m.dim));
    keyMetrics = filtered.slice(0, 5);
  } else {
    // Fallback: quality-focused default (no momentum)
    keyMetrics = metricPool.filter(m => m.dim !== 'momentum').slice(0, 5);
  }

  // Pad to 5 if needed
  if (keyMetrics.length < 5) {
    const used = new Set(keyMetrics.map(m => m.label));
    for (const m of metricPool) {
      if (keyMetrics.length >= 5) break;
      if (!used.has(m.label) && m.dim !== 'momentum') {
        keyMetrics.push(m);
        used.add(m.label);
      }
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
      {/* Card 1: Quick Summary */}
      <div className="expanded-card">
        <div className="expanded-card-title">QUICK SUMMARY</div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {row.reason || 'No thesis summary available. Run Thesis for a full analysis.'}
        </div>
      </div>

      {/* Card 2: Key Financials — strategy-aware metric selection */}
      <div className="expanded-card">
        <div className="expanded-card-title">KEY FINANCIALS</div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 4,
          textAlign: 'center', fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)',
        }}>
          {keyMetrics.map((m) => (
            <div key={m.label}>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>{m.label}</div>
              <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Card 3: Return Breakdown + buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="expanded-card">
          <div className="expanded-card-title">RETURN BREAKDOWN</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <div className="return-bar" style={{ flex: 1, maxWidth: 280 }}>
              <div style={{ width: `${(discount / returnSum) * 100}%`, height: 8, background: 'var(--info)' }} />
              <div style={{ width: `${(growth / returnSum) * 100}%`, height: 8, background: 'var(--positive)' }} />
              <div style={{ width: `${(margin / returnSum) * 100}%`, height: 8, background: 'var(--accent)' }} />
              <div style={{ width: `${(dividend / returnSum) * 100}%`, height: 8, background: 'var(--text-muted)' }} />
            </div>
            <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', fontWeight: 700 }}>
              {totalReturn > 0 ? `${Math.round(totalReturn)}%` : '\u2014'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
            <span><span className="return-legend-dot" style={{ background: 'var(--info)' }} />Discount {Math.round(discount)}%</span>
            <span><span className="return-legend-dot" style={{ background: 'var(--positive)' }} />Growth {Math.round(growth)}%</span>
            <span><span className="return-legend-dot" style={{ background: 'var(--accent)' }} />Margin {Math.round(margin)}%</span>
            <span><span className="return-legend-dot" style={{ background: 'var(--text-muted)' }} />Dividend {Math.round(dividend)}%</span>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
          <button
            className="btn btn-accent"
            style={{ padding: '6px 14px', fontSize: 'var(--text-xs)' }}
            disabled={thesisStatus !== 'idle'}
            onClick={() => {
              setThesisStatus('running');
              api.runThesis(ticker)
                .then(() => setThesisStatus('queued'))
                .catch(() => setThesisStatus('idle'));
            }}
          >
            {thesisStatus === 'running' ? 'Submitting…' : thesisStatus === 'queued' ? '✓ Queued' : 'Run Thesis'}
          </button>
          <Link to={`/library?ticker=${ticker}`} className="btn btn-ghost" style={{ padding: '6px 14px', fontSize: 'var(--text-xs)', textDecoration: 'none' }}>
            View in Library
          </Link>
        </div>
      </div>
    </div>
  );
}


// ── Main Screener Component ────────────────────────────────────────────

export function Screener() {
  const queryClient = useQueryClient();
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [dismissModal, setDismissModal] = useState<{
    ticker: string;
    score: number;
    rank: number;
  } | null>(null);
  const [activeLens] = useState('All');
  // Persist jobId in sessionStorage so navigating away and back resumes tracking
  const [jobId, setJobId] = useState<string | null>(() => sessionStorage.getItem('screener_job_id'));
  const setAndPersistJobId = (id: string | null) => {
    setJobId(id);
    if (id) sessionStorage.setItem('screener_job_id', id);
    else sessionStorage.removeItem('screener_job_id');
  };

  // ── Data fetching ──

  const [runError, setRunError] = useState<string | null>(null);

  // Fetch results: prefer v2 (AI-scored) when available, fall back to basic screener results
  // Refetch every 15s so pipeline results appear without manual refresh
  const { data: v2Data, isLoading: v2Loading } = useQuery<ScreenerData>({
    queryKey: ['screener-v2'],
    queryFn: api.screenerV2Results,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  const { data: basicData, isLoading: basicLoading } = useQuery<ScreenerData>({
    queryKey: ['screener-basic'],
    queryFn: api.screenerResults as () => Promise<ScreenerData>,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  // Use v2 if it has results, otherwise use basic screener results
  const data = (v2Data?.results?.length ? v2Data : basicData) ?? v2Data;
  const isLoading = v2Loading && basicLoading;

  const { data: strategyData } = useQuery({
    queryKey: ['strategy'],
    queryFn: api.getStrategy,
  });

  // Poll job status while running
  const { data: jobData } = useQuery<JobStatus>({
    queryKey: ['job', jobId],
    queryFn: () => api.jobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const d = query.state.data as JobStatus | undefined;
      if (d && (d.status === 'complete' || d.status === 'failed' || d.status === 'cancelled')) return false;
      return 2000;
    },
  });

  // Clear jobId and refetch results when job completes or is no longer running
  useEffect(() => {
    const done = jobData?.status === 'complete' || jobData?.status === 'failed' || jobData?.status === 'cancelled';
    if (done) {
      setAndPersistJobId(null);
      queryClient.invalidateQueries({ queryKey: ['screener-basic'] });
      queryClient.invalidateQueries({ queryKey: ['screener-v2'] });
    }
  }, [jobData?.status, queryClient]);

  const runMutation = useMutation({
    mutationFn: async () => {
      setRunError(null);
      let currentStrategyData = strategyData;

      // If strategy exists but no scoring code, generate it first (transparent to user)
      if (currentStrategyData?.has_strategy && !currentStrategyData?.version) {
        const strategyId = currentStrategyData?.strategy?.id || currentStrategyData?.constitution?.id;
        if (strategyId) {
          try {
            await api.regenerateScoring(strategyId);
            // Refetch strategy so we have the new version
            const refreshed = await api.getStrategy();
            currentStrategyData = refreshed;
            queryClient.setQueryData(['strategy'], refreshed);
          } catch {
            // Codegen failed — fall back to basic screener silently
          }
        }
      }

      const scoringReady = !!currentStrategyData?.version;
      if (scoringReady) {
        // Strategy has AI scoring code — use v2 screener (async, job queue)
        const resp = await api.runScreenerV2();
        return { ...resp, _mode: 'v2' };
      } else {
        // No scoring code — run the constitution-based screener
        const resp = await api.runScreener();
        return { ...resp, _mode: 'basic' };
      }
    },
    onSuccess: (resp: any) => {
      if (resp?.job_id) {
        setAndPersistJobId(resp.job_id);
      } else {
        queryClient.invalidateQueries({ queryKey: ['screener-v2'] });
        queryClient.invalidateQueries({ queryKey: ['screener-basic'] });
      }
    },
    onError: (err: Error) => {
      setRunError(err.message || 'Screener failed to start');
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: api.recordFeedback,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['screener-v2'] });
    },
  });

  // ── Derived data ──

  const hasStrategy = strategyData?.has_strategy;
  const hasScoring = !!strategyData?.version;
  const allResults: ScreenerResult[] = data?.results || [];
  const runId: string | null = data?.run_id || null;
  // isRunning covers both: async job-queue runs (jobId set) and sync v2 runs (mutation pending)
  const isRunning = (!!jobId && jobData?.status === 'running') || runMutation.isPending;
  const isEmpty = !isLoading && allResults.length === 0 && !isRunning;

  // Lens filtering — handle both `lens` (legacy) and `top_lens` (API v2)
  const getLens = (r: ScreenerResult) => (r.lens ?? r.top_lens ?? '').toLowerCase();
  const nonDismissed = allResults.filter((r) => r.feedback !== 'dismissed');
  const filteredResults = activeLens === 'All'
    ? nonDismissed
    : nonDismissed.filter((r) => getLens(r) === activeLens.toLowerCase());

  const topPicks = filteredResults.slice(0, TOP_N);
  const rest = filteredResults.slice(TOP_N);

  // Lens counts
  const allCount = allResults.length;
  // Legacy lens counts (no longer displayed but kept for data compatibility)
  const _dislocationCount = allResults.filter((r) => getLens(r) === 'dislocation').length;
  void _dislocationCount; // suppress unused warning

  // Feedback count
  const feedbackCount = allResults.filter((r) => r.feedback === 'promoted' || r.feedback === 'dismissed').length;

  // V2 results detection and dynamic columns
  const isV2Results = !!(v2Data?.results?.length && v2Data?.label_map && Object.keys(v2Data.label_map).length > 1);
  const labelMap: Record<string, { label?: string; unit?: string; format?: string }> =
    (isV2Results ? v2Data?.label_map : null) ?? {};
  // Dynamic dimension columns: everything in label_map except meta/noise keys, max 4
  // Prioritize strategy-unique dimensions (momentum, margin_expansion) over generic ones
  const EXCLUDED_DIM_KEYS = new Set(['score', 'reason', 'penalty', 'ticker', 'symbol']);
  const PRIORITY_KEYS = ['momentum', 'margin_expansion', 'growth', 'quality', 'cheapness'];
  const dynCols = [
    ...Object.entries(labelMap).filter(([k]) => PRIORITY_KEYS.includes(k) && !EXCLUDED_DIM_KEYS.has(k)),
    ...Object.entries(labelMap).filter(([k]) => !PRIORITY_KEYS.includes(k) && !EXCLUDED_DIM_KEYS.has(k)),
  ].slice(0, 4);

  // ── Handlers ──

  const [promoteStatus, setPromoteStatus] = useState<Record<string, string>>({});

  const handlePromote = useCallback((ticker: string, score: number, rank: number) => {
    if (!runId) return;
    setPromoteStatus(prev => ({ ...prev, [ticker]: 'Promoting...' }));
    feedbackMutation.mutate({
      screener_run_id: runId,
      ticker,
      feedback: 'promoted',
      score_at_feedback: score,
      rank_at_feedback: rank,
    }, {
      onSuccess: () => {
        setPromoteStatus(prev => ({ ...prev, [ticker]: 'Promoted! Thesis queued.' }));
        api.runThesis(ticker)
          .then(() => setPromoteStatus(prev => ({ ...prev, [ticker]: 'Thesis running...' })))
          .catch(() => setPromoteStatus(prev => ({ ...prev, [ticker]: 'Promoted, but thesis failed. Retry from Research page.' })));
      },
    });
  }, [runId, feedbackMutation]);

  const handleDismiss = useCallback((reason: string) => {
    if (!runId || !dismissModal) return;
    feedbackMutation.mutate({
      screener_run_id: runId,
      ticker: dismissModal.ticker,
      feedback: 'dismissed',
      dismiss_reason: reason,
      score_at_feedback: dismissModal.score,
      rank_at_feedback: dismissModal.rank,
    });
    setDismissModal(null);
  }, [runId, dismissModal, feedbackMutation]);

  // ── Subtitle ──

  const subtitle = allResults.length > 0
    ? [
      `${allResults.length} scored`,
      data?.universe_size ? `(${data.universe_size} universe \u2192 ${data.scored_count ?? allResults.length} passed filters)` : null,
      data?.strategy_name ? `Strategy: ${data.strategy_name}` : null,
      feedbackCount > 0 ? `${feedbackCount} of ${allResults.length} rated` : null,
    ].filter(Boolean).join(' \u00b7 ')
    : undefined;

  // ── Render table rows ──

  const renderRow = (r: ScreenerResult, rank: number) => {
    const ticker = r.ticker || r.symbol || '';
    const isExpanded = expandedTicker === ticker;
    const isDismissed = r.feedback === 'dismissed';
    const isPromoted = r.feedback === 'promoted';
    const lens = getLens(r);
    const score = r.score || (lens === 'compounder' ? (r as any).compounder_score : (r as any).dislocation_score) || 0;

    return (
      <React.Fragment key={ticker}>
        <tr style={{ opacity: isDismissed ? 0.5 : 1, cursor: 'pointer' }}
          onClick={() => setExpandedTicker(isExpanded ? null : ticker)}
        >
          <td style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
            {rank}
          </td>
          <td>
            <Link to={`/ticker/${ticker}`} className="ticker" onClick={(e) => e.stopPropagation()}>
              {ticker}
            </Link>
            {r.data_warnings && r.data_warnings.length > 0 && (
              <span title={r.data_warnings[0]} style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--warning)', marginLeft: 4, verticalAlign: 'middle' }} />
            )}
          </td>
          <td>{r.companyName || r.company_name || ''}</td>
          <td>{r.sector || ''}</td>
          <td className="num">{r.price != null ? `$${r.price.toFixed(0)}` : '\u2014'}</td>
          <td className="num">
            <span className="score-badge" style={getScoreBadgeStyle(score)}>
              {score > 0 ? (score <= 10 ? (score * 10).toFixed(0) : score.toFixed(0)) : '\u2014'}
            </span>
          </td>
          {isV2Results
            ? dynCols.map(([k]) => {
                const val = (r as any)[k];
                return (
                  <td key={k} className="num">
                    {val != null ? (typeof val === 'number' ? val.toFixed(1) : val) : '\u2014'}
                  </td>
                );
              })
            : <>
                <td className="num">{r.quality?.toFixed(1) ?? '\u2014'}</td>
                <td className="num">{r.cheapness?.toFixed(1) ?? '\u2014'}</td>
                <td className="num">{r.growth?.toFixed(1) ?? '\u2014'}</td>
              </>
          }
          <td className="num">
            <span style={{ fontFamily: 'var(--font-data)' }}>
              {r.expected_return != null ? `${Math.round(r.expected_return)}%` : '\u2014'}
            </span>
          </td>
          <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
            {isPromoted ? (
              <span style={{ color: 'var(--positive)', fontSize: 'var(--text-xs)', padding: '2px 5px' }}
                title={promoteStatus[ticker] || 'Promoted'}>
                &#10003;
                {promoteStatus[ticker] && (
                  <span style={{ fontSize: 9, color: 'var(--text-muted)', marginLeft: 2 }}>
                    {promoteStatus[ticker].includes('failed') ? '!' : ''}
                  </span>
                )}
              </span>
            ) : (
              <button className="action-btn" title="Promote to thesis"
                style={{ color: 'var(--positive)' }}
                onClick={() => handlePromote(ticker, score, rank)}
              >
                &#8853;
              </button>
            )}
            {isDismissed ? (
              <span style={{ color: 'var(--negative)', fontSize: 'var(--text-xs)', padding: '2px 5px' }}
                title={r.dismiss_reason || 'Dismissed'}>
                &#10007;
              </span>
            ) : (
              <button className="action-btn" title="Dismiss"
                onClick={() => setDismissModal({ ticker, score, rank })}
              >
                &#8854;
              </button>
            )}
          </td>
        </tr>
        {isExpanded && (
          <tr>
            <td colSpan={isV2Results ? 6 + dynCols.length : 11} style={{ padding: 0, borderTop: 'none' }}>
              <div className="expanded-area">
                <ExpandedDetail row={r} labelMap={labelMap} strategyWeights={strategyData?.constitution?.agent_profiles?.screener?.weights ?? {}} />
              </div>
            </td>
          </tr>
        )}
      </React.Fragment>
    );
  };

  const renderTable = (rows: ScreenerResult[], startIdx: number) => (
    <table>
      <thead>
        <tr>
          <th style={{ width: 30 }}>#</th>
          <th>Ticker</th>
          <th>Company</th>
          <th>Sector</th>
          <th className="num">Price</th>
          <th className="num">Score</th>
          {isV2Results
            ? dynCols.map(([k, meta]) => (
                <th key={k} className="num">{(meta.label || k).toUpperCase()}</th>
              ))
            : <>
                <th className="num">Quality</th>
                <th className="num">Cheapness</th>
                <th className="num">Growth</th>
              </>
          }
          <th className="num">Return</th>
          <th style={{ width: 50, textAlign: 'center' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, idx) => renderRow(r, startIdx + idx + 1))}
      </tbody>
    </table>
  );


  // ── State: Running ──

  if (isRunning) {
    const phase = jobData?.phase_number ?? 1;
    const totalPhases = jobData?.total_phases ?? 4;
    const progress = jobData?.progress ?? 0;
    const total = jobData?.total ?? 0;
    const pct = total > 0 ? (progress / total) * 100 : 0;
    const isSyncRun = runMutation.isPending && !jobId; // sync v2 run, no job progress

    return (
      <div>
        <PageHeader
          sectionLabel="Screener"
          title="Screener"
          subtitle={data?.strategy_name ? `Strategy: ${data.strategy_name}` : undefined}
          actions={
            !isSyncRun ? (
              <button className="btn btn-ghost" style={{ color: 'var(--negative)', fontSize: 'var(--text-xs)' }}
                onClick={() => setJobId(null)}>
                Cancel
              </button>
            ) : undefined
          }
        />

        <div className="card" style={{ marginBottom: 8 }}>
          {isSyncRun ? (
            <>
              <div className="progress-phase">
                {!hasScoring ? 'Building your scoring function…' : `Running ${strategyData?.strategy?.name || 'strategy'} screener…`}
              </div>
              <div className="progress-track" style={{ overflow: 'hidden' }}>
                <div className="progress-fill" style={{ width: '40%', animation: 'indeterminate 1.5s ease-in-out infinite' }} />
              </div>
              <div className="progress-meta">
                <span>{!hasScoring ? 'Generating AI scoring code from your strategy, then running the screen' : 'Fetching universe, enriching with SEC data, scoring stocks'}</span>
                <span style={{ color: 'var(--text-muted)' }}>Takes a few minutes</span>
              </div>
            </>
          ) : (
            <>
              <div className="progress-phase">
                Phase {phase} of {totalPhases}: {jobData?.phase || 'Scoring'}
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="progress-meta">
                <span>{progress} / {total} stocks {jobData?.message || 'scored'}</span>
                <span>{jobData?.elapsed || ''}</span>
              </div>
            </>
          )}
        </div>

        {/* Partial results streaming in */}
        {allResults.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              PARTIAL RESULTS (streaming)
            </span>
            <div className="card" style={{ padding: 0, opacity: 0.6, overflowX: 'auto', marginTop: 4 }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 30 }}>#</th>
                    <th>Ticker</th>
                    <th>Company</th>
                    <th>Sector</th>
                    <th className="num">Score</th>
                    <th className="num">Quality</th>
                    <th className="num">Cheapness</th>
                  </tr>
                </thead>
                <tbody>
                  {allResults.slice(0, 5).map((r, idx) => {
                    const ticker = r.ticker || r.symbol || '';
                    return (
                      <tr key={ticker}>
                        <td style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>{idx + 1}</td>
                        <td><span className="ticker">{ticker}</span></td>
                        <td>{r.companyName || r.company_name || ''}</td>
                        <td>{r.sector || ''}</td>
                        <td className="num">{r.score?.toFixed(0) ?? '\u2014'}</td>
                        <td className="num">{r.quality?.toFixed(1) ?? '\u2014'}</td>
                        <td className="num">{r.cheapness?.toFixed(1) ?? '\u2014'}</td>
                      </tr>
                    );
                  })}
                  <tr style={{ opacity: 0.4 }}>
                    <td colSpan={7} style={{ textAlign: 'center', padding: 12, color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
                      More results arriving as scoring completes...
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── State: Empty ──

  if (isEmpty && !runMutation.isPending) {
    return (
      <div>
        <PageHeader
          sectionLabel="Screener"
          title="Screener"
        />

        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 'var(--text-lg)', fontWeight: 500, marginBottom: 6 }}>
            Ready to screen
          </div>
          <div style={{
            fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 16,
            maxWidth: 400, marginLeft: 'auto', marginRight: 'auto',
          }}>
            {hasStrategy
              ? `Your scoring function will evaluate stocks using your ${data?.strategy_name || 'strategy'}. Run the screener to discover opportunities.`
              : 'Define your strategy in Settings first, then run the screener to discover opportunities.'}
          </div>
          <button className="btn btn-accent" style={{ padding: '10px 24px', fontSize: 'var(--text-sm)' }}
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
          >
            {runMutation.isPending ? 'Starting...' : 'Run Screener'}
          </button>
        </div>
      </div>
    );
  }

  // ── State: Loading ──

  if (isLoading) {
    return (
      <div>
        <PageHeader sectionLabel="Screener" title="Screener" />

        <div className="card" style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
          Loading...
        </div>
      </div>
    );
  }

  // ── State: Results (default) ──

  return (
    <div>
      <PageHeader
        sectionLabel="Screener"
        title="Screener"
        subtitle={subtitle}
        actions={
          <button
            className="btn btn-accent"
            style={{ padding: '8px 16px', fontSize: 'var(--text-sm)' }}
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
          >
            {runMutation.isPending
              ? (!hasScoring ? 'Preparing…' : 'Running…')
              : 'Run Screener'}
          </button>
        }
      />

      {/* Run error */}
      {runError && (
        <div className="card" style={{ borderLeft: '3px solid var(--negative)', marginBottom: 12 }}>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--negative)' }}>
            {runError.includes('scoring') || runError.includes('400')
              ? 'No AI scoring code generated yet — running with constitution-based screener instead.'
              : `Screener error: ${runError}`}
          </div>
        </div>
      )}


      {/* No strategy warning */}
      {!hasStrategy && (
        <div className="card" style={{ borderLeft: '3px solid var(--warning)', marginBottom: 12 }}>
          <div style={{ fontSize: 'var(--text-sm)' }}>
            No strategy defined yet. Go to{' '}
            <Link to="/settings" style={{ color: 'var(--accent)' }}>Settings &gt; Strategy</Link>{' '}
            to define your investment approach.
          </div>
        </div>
      )}

      {/* Status messages */}
      {data?.status === 'partial' && data.failed_count != null && data.failed_count > 0 && (
        <div className="card" style={{ borderLeft: '3px solid var(--warning)', marginBottom: 8, padding: '8px 12px' }}>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>
            {data.failed_count} stocks failed scoring
          </span>
        </div>
      )}

      {/* Results count */}
      <div className="lens-tabs">
        <button className="lens-tab active">
          All ({allCount})
        </button>
      </div>

      {/* Top picks */}
      {topPicks.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '8px 0' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--accent)' }}>
              Top {Math.min(TOP_N, filteredResults.length)} Picks
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Highest scoring stocks based on your strategy
            </span>
          </div>
          <div className="card" style={{ padding: 0, overflowX: 'auto', borderColor: 'rgba(245,166,35,0.3)' }}>
            {renderTable(topPicks, 0)}
          </div>
        </div>
      )}

      {/* Rest of universe (collapsed) */}
      {rest.length > 0 && (
        <details style={{ marginTop: 4 }}>
          <summary style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', cursor: 'pointer', padding: '6px 0' }}>
            {rest.length} more stocks below threshold
          </summary>
          <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
            {renderTable(rest, TOP_N)}
          </div>
        </details>
      )}

      {/* Dismiss modal */}
      {dismissModal && (
        <DismissModal
          ticker={dismissModal.ticker}
          onDismiss={handleDismiss}
          onClose={() => setDismissModal(null)}
        />
      )}
    </div>
  );
}
