import React, { useState, useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link, useSearchParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { VerdictBadge } from '../components/VerdictBadge';
import { ReaderPopup } from '../components/ReaderPopup';

// ─── Types ────────────────────────────────────────────────────────

interface Assumption {
  assumption: string;
  predicted: string;
  actual: string;
  status: 'intact' | 'below' | 'broken';
  delta: string;
}

interface ReturnPrediction {
  metric: string;
  thesis: string;
  icBear: string;
  icBase: string;
  actual: string;
  actualColor?: string;
}

interface TimelineEvent {
  type: string;
  date: string;
  dotColor: string;
  typeColor: string;
  summary: string;
  meta?: string;
  verdict?: 'pass' | 'no_pass';
  conviction?: number;
  scorecard?: string;
  returns?: string;
  actions?: { label: string; style: 'amber' | 'blue' | 'link'; onClick: string }[];
  structuredData?: { label: string; rows: { key: string; value: string; valueColor?: string }[] }[];
  rawJson?: string;
  thesisContent?: string;
  icContent?: string;
}

interface FundamentalRow {
  metric: string;
  expected: string;
  quarters: { value: string; color: string }[];
  trend: string;
  trendColor: string;
}

interface TickerResearch {
  ticker: string;
  name: string;
  status: 'held' | 'exited' | 'watchlist' | 'researched';
  sector: string;
  industry: string;
  firstResearched: string;
  latestActivity: string;
  artifactCount: number;
  stageCount: number;
  priceAtFirst: number;
  priceNow: number;
  returnPct: number;
  position?: { shares: number; costBasis: number; weight: number; pnl: number };
  assumptions: Assumption[];
  predictionAccuracy: string;
  returnPredictions: ReturnPrediction[];
  timeline: TimelineEvent[];
  fundamentals: FundamentalRow[];
  feedbackPatterns: { icon: string; color: string; label: string }[];
  refinementProposals: { text: string; status: string }[];
  behavioralSignals: string[];
}

export interface _MemoSection {
  title: string;
  content: string;
}

interface LibraryStats {
  tickers: number;
  artifacts: number;
  winRate: number;
  accuracy: number;
}
// ─── Tabs ─────────────────────────────────────────────────────────

type LibraryTab = 'browse' | 'memos' | 'ask' | 'empty';

export function Library() {
  const [searchParams] = useSearchParams();
  const urlTicker = searchParams.get('ticker')?.toUpperCase() ?? '';
  const urlTab = searchParams.get('tab') as LibraryTab | null;
  const [activeTab, setActiveTab] = useState<LibraryTab>(urlTab ?? 'browse');

  // Lift chat state so it persists across tab switches
  const [askMessages, setAskMessages] = useState<{ role: 'user' | 'ai'; content: string }[]>([
    { role: 'ai', content: 'Ask me anything about your research archive. I can look up thesis narratives, IC review verdicts, screener scores, memo analysis, and outcome tracking for any ticker.' },
  ]);

  const tabs: { key: LibraryTab; label: string }[] = [
    { key: 'browse', label: 'Browse' },
    { key: 'memos', label: 'Memos' },
    { key: 'ask', label: 'Ask the Library' },
  ];

  const queryClient = useQueryClient();
  const syncMutation = useMutation({
    mutationFn: () => fetch('/api/library/sync', { method: 'POST' }).then(r => r.json()),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['library-stats'] }); },
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', height: '100%' }}>
      {/* Top tab bar + sync button */}
      <div style={{ padding: '0 16px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="tab-bar">
          {tabs.map(t => (
            <button
              key={t.key}
              className={`tab${activeTab === t.key ? ' active' : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          className="btn btn-accent"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          style={{ fontSize: 'var(--text-xs)', padding: '6px 14px' }}
        >
          {syncMutation.isPending ? 'Syncing...' : 'Sync Library'}
        </button>
      </div>

      {activeTab === 'browse' && <BrowseTab initialTicker={urlTicker} onSwitchToMemos={(_type) => { setActiveTab('memos'); }} />}
      {activeTab === 'memos' && <MemosTab initialTicker={urlTicker} />}
      {activeTab === 'ask' && <AskTab messages={askMessages} setMessages={setAskMessages} />}
      {activeTab === 'empty' && <EmptyTab />}
    </div>
  );
}

// ─── Browse Tab ───────────────────────────────────────────────────

function BrowseTab({ initialTicker, onSwitchToMemos }: { initialTicker?: string; onSwitchToMemos: (type: 'inv' | 'res') => void }) {
  const [search, setSearch] = useState(initialTicker || '');
  const [sector, setSector] = useState('All Sectors');
  const [expandedStruct, setExpandedStruct] = useState<Record<string, boolean>>({});
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});
  const [readerPopup, setReaderPopup] = useState<{ title: string; content: string } | null>(null);

  // API calls — real data only
  const { data: statsData } = useQuery({ queryKey: ['library-stats'], queryFn: () => api.getLibraryStats() });
  const { data: tickerData } = useQuery({
    queryKey: ['library-ticker', search],
    queryFn: () => api.getLibraryTicker(search),
    enabled: search.length > 0,
  });

  const stats: LibraryStats = statsData ? {
    tickers: statsData.tickers ?? statsData.ticker_count ?? Object.keys(statsData.by_type ?? {}).length ?? 0,
    artifacts: statsData.artifacts ?? statsData.artifact_count ?? statsData.total ?? 0,
    winRate: statsData.winRate ?? statsData.win_rate ?? 0,
    accuracy: statsData.accuracy ?? statsData.prediction_accuracy ?? 0,
  } : { tickers: 0, artifacts: 0, winRate: 0, accuracy: 0 };

  // API returns enriched TickerResearch shape — show if we have entries or assumptions
  const ticker = useMemo(() => {
    if (!tickerData) return null;
    // Accept if we have assumptions OR entries (the enriched response from /library/ticker)
    if (tickerData.assumptions != null || (tickerData.entries && tickerData.entries.length > 0)) {
      return tickerData as TickerResearch;
    }
    return null;
  }, [search, tickerData]);

  const toggleStruct = (key: string) => setExpandedStruct(prev => ({ ...prev, [key]: !prev[key] }));
  const toggleRaw = (key: string) => setExpandedRaw(prev => ({ ...prev, [key]: !prev[key] }));

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0 20px 20px', minHeight: 0 }}>
      {/* Search bar + filters + stats */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0 12px', borderBottom: '1px solid var(--border)', marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', width: 220 }}>
          <input
            className="search-input"
            value={search}
            onChange={e => setSearch(e.target.value.toUpperCase())}
            style={{ fontFamily: 'var(--font-data)', color: 'var(--accent)', fontWeight: 600, letterSpacing: '0.05em', width: '100%' }}
          />
        </div>
        <select
          className="filter-select"
          value={sector}
          onChange={e => setSector(e.target.value)}
          style={{ padding: '2px 6px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 9999, color: 'var(--text-secondary)', fontFamily: 'var(--font-data)', fontSize: 10, cursor: 'pointer' }}
        >
          <option>All Sectors</option>
          <option>Technology</option>
          <option>Financials</option>
          <option>Healthcare</option>
        </select>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>
          <span>Tickers<strong style={{ color: 'var(--text-primary)', marginLeft: 3 }}>{stats.tickers}</strong></span>
          <span>Artifacts<strong style={{ color: 'var(--text-primary)', marginLeft: 3 }}>{stats.artifacts}</strong></span>
          <span>Win rate<strong style={{ color: 'var(--positive)', marginLeft: 3 }}>{stats.winRate}%</strong></span>
          <span>Accuracy<strong style={{ color: 'var(--text-primary)', marginLeft: 3 }}>{stats.accuracy}%</strong></span>
        </div>
      </div>

      {!ticker ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
          {search ? `No research found for "${search}"` : 'Search for a ticker to view its research file'}
        </div>
      ) : (
        <>
          {/* Ticker Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14, paddingBottom: 10, borderBottom: '1px solid var(--border)' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.05em' }}>{ticker.ticker}</span>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{ticker.name}</span>
                <StatusBadge status={ticker.status} />
              </div>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>
                {ticker.sector} . {ticker.industry} . First researched <span style={{ color: 'var(--text-secondary)' }}>{ticker.firstResearched}</span> . Latest activity <span style={{ color: 'var(--text-secondary)' }}>{ticker.latestActivity}</span> . {ticker.artifactCount} artifacts across {ticker.stageCount} pipeline stages
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>PRICE AT FIRST RESEARCH &rarr; NOW</div>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
                {ticker.priceAtFirst != null ? `$${ticker.priceAtFirst.toFixed(2)}` : '--'} &rarr; {ticker.priceNow != null ? `$${ticker.priceNow.toFixed(2)}` : '--'}
                {ticker.returnPct != null && <span style={{ color: 'var(--positive)', marginLeft: 4 }}>+{ticker.returnPct}%</span>}
              </div>
              {ticker.position && (
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                  Position: {ticker.position.shares} shares @ ${ticker.position.costBasis} . Weight {ticker.position.weight}% . P&L <span style={{ color: 'var(--positive)' }}>+{ticker.position.pnl}%</span>
                </div>
              )}
            </div>
          </div>

          {/* Predictions vs Actuals */}
          <div style={{ marginBottom: 16 }}>
            <div className="section-title" style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              PREDICTIONS VS ACTUALS
              <span style={{ fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'var(--font-ui)', textTransform: 'none', letterSpacing: 0 }}>the training signal</span>
            </div>

            {/* Key Assumptions */}
            <div className="card" style={{ marginBottom: 6 }}>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>KEY ASSUMPTIONS</div>
              <table className="pred-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                <thead>
                  <tr>
                    <th style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: 'left', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500, letterSpacing: '0.04em' }}>Assumption</th>
                    <th style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: 'right', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Predicted</th>
                    <th style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: 'right', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Actual</th>
                    <th style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: 'left', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Status</th>
                    <th style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: 'right', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {(ticker.assumptions ?? []).map((a, i) => (
                    <tr key={i}>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.assumptions ?? []).length - 1 ? '1px solid var(--border)' : 'none', color: 'var(--text-secondary)' }}>{a.assumption}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.assumptions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)' }}>{a.predicted}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.assumptions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)' }}>{a.actual}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.assumptions ?? []).length - 1 ? '1px solid var(--border)' : 'none' }}>
                        <span style={{ color: a.status === 'intact' ? 'var(--positive)' : a.status === 'below' ? 'var(--warning)' : 'var(--negative)' }}>
                          {a.status === 'intact' ? '\u2713 intact' : a.status === 'below' ? '\u26A0 below' : '\u2717 broken'}
                        </span>
                      </td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.assumptions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)', color: a.status === 'intact' ? 'var(--positive)' : a.status === 'below' ? 'var(--negative)' : 'var(--negative)' }}>{a.delta}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--border)' }}>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>PREDICTION ACCURACY</span>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', color: 'var(--positive)', fontWeight: 600 }}>{ticker.predictionAccuracy}</span>
              </div>
            </div>

            {/* Return Predictions */}
            <div className="card">
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>RETURN PREDICTIONS</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                <thead>
                  <tr>
                    {['Metric', 'Thesis', 'IC Bear', 'IC Base', 'Actual'].map((h, i) => (
                      <th key={h} style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', textAlign: i === 0 ? 'left' : 'right', padding: '4px 6px', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(ticker.returnPredictions ?? []).map((r, i) => (
                    <tr key={i}>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.returnPredictions ?? []).length - 1 ? '1px solid var(--border)' : 'none', color: 'var(--text-secondary)' }}>{r.metric}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.returnPredictions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)' }}>{r.thesis}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.returnPredictions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)' }}>{r.icBear}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.returnPredictions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)' }}>{r.icBase}</td>
                      <td style={{ padding: '5px 6px', borderBottom: i < (ticker.returnPredictions ?? []).length - 1 ? '1px solid var(--border)' : 'none', textAlign: 'right', fontFamily: 'var(--font-data)', color: r.actualColor, fontWeight: r.actualColor ? 600 : undefined }}>{r.actual}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Research Timeline */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              RESEARCH TIMELINE
              <span style={{ fontSize: 10, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', padding: '0px 5px', borderRadius: 9999 }}>{(ticker.timeline ?? []).length}</span>
            </div>

            <div style={{ position: 'relative', paddingLeft: 20 }}>
              <div style={{ position: 'absolute', left: 5, top: 6, bottom: 6, width: 1, background: 'var(--border)' }} />

              {(ticker.timeline ?? []).map((ev, idx) => (
                <div key={idx} style={{ position: 'relative', marginBottom: 10 }}>
                  <div style={{ position: 'absolute', left: -18, top: 6, width: 8, height: 8, borderRadius: '50%', border: '1.5px solid var(--bg-primary)', background: ev.dotColor }} />

                  <div
                    style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: ev.type === 'PROMOTED' ? '6px 10px' : '8px 10px', cursor: 'pointer', transition: 'border-color 0.15s' }}
                    onClick={() => {
                      const content = ev.icContent || ev.thesisContent || ev.summary || ev.returns || 'No detailed content available.';
                      const title = ev.type === 'ic_review'
                        ? `${ticker.ticker} — IC Review${ev.verdict ? ` — ${ev.verdict.toUpperCase()}` : ''}`
                        : ev.type === 'thesis'
                        ? `${ticker.ticker} — Thesis`
                        : `${ticker.ticker} — ${ev.type}`;
                      setReaderPopup({ title, content });
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: ev.type === 'PROMOTED' ? 0 : 3 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, letterSpacing: '0.05em', fontWeight: 600, color: ev.typeColor }}>{ev.type}</span>
                        {ev.verdict && <VerdictBadge verdict={ev.verdict} />}
                        {ev.conviction != null && <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)' }}>conviction {ev.conviction}/5</span>}
                        {ev.meta && <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)' }}>{ev.meta}</span>}
                        {ev.type === 'PROMOTED' && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{ev.summary}</span>}
                      </div>
                      <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>{ev.date}</span>
                    </div>

                    {ev.type !== 'PROMOTED' && ev.scorecard && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        <div style={{ display: 'flex', gap: 12, marginBottom: 3 }}>
                          <span>Scorecard: <span style={{ fontFamily: 'var(--font-data)' }}>{ev.scorecard}</span></span>
                        </div>
                        {ev.returns && (
                          <div style={{ display: 'flex', gap: 12, marginBottom: 3 }}>
                            <span>Returns: <span style={{ fontFamily: 'var(--font-data)' }}>{ev.returns}</span></span>
                          </div>
                        )}
                      </div>
                    )}

                    {ev.type !== 'PROMOTED' && !ev.scorecard && ev.summary && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.5, whiteSpace: 'pre-line' }}>{ev.summary}</div>
                    )}

                    {/* Actions row */}
                    {(ev.actions || ev.thesisContent || ev.icContent || ev.structuredData || ev.rawJson) && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                        {ev.actions?.map((a, ai) => (
                          <span
                            key={ai}
                            onClick={() => onSwitchToMemos(a.onClick === 'memos-inv' ? 'inv' : 'res')}
                            style={{
                              fontFamily: 'var(--font-data)', fontSize: 9, cursor: 'pointer', letterSpacing: '0.02em', padding: '2px 8px', borderRadius: 3,
                              background: a.style === 'amber' ? 'var(--accent-subtle)' : 'rgba(66,133,244,0.12)',
                              color: a.style === 'amber' ? 'var(--accent)' : 'var(--info)',
                            }}
                          >
                            {a.label}
                          </span>
                        ))}
                        {ev.icContent && (
                          <span
                            onClick={() => setReaderPopup({ title: `${ticker.ticker} \u2014 IC Decision v1 \u2014 PASS`, content: ev.icContent! })}
                            style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--info)', cursor: 'pointer', letterSpacing: '0.02em' }}
                          >
                            Read IC decision
                          </span>
                        )}
                        {ev.thesisContent && (
                          <span
                            onClick={() => setReaderPopup({ title: `${ticker.ticker} \u2014 Thesis v1`, content: ev.thesisContent! })}
                            style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--info)', cursor: 'pointer', letterSpacing: '0.02em' }}
                          >
                            Read thesis
                          </span>
                        )}
                        {ev.structuredData && (
                          <span
                            onClick={() => toggleStruct(`${idx}`)}
                            style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--info)', cursor: 'pointer', letterSpacing: '0.02em' }}
                          >
                            Structured data
                          </span>
                        )}
                        {ev.rawJson && (
                          <span
                            onClick={() => toggleRaw(`${idx}`)}
                            style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--info)', cursor: 'pointer', letterSpacing: '0.02em' }}
                          >
                            Raw
                          </span>
                        )}
                      </div>
                    )}

                    {/* Structured data expandable */}
                    {expandedStruct[`${idx}`] && ev.structuredData && (
                      <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '8px 10px', marginTop: 6 }}>
                        {ev.structuredData.map((section, si) => (
                          <div key={si} style={{ marginBottom: si < ev.structuredData!.length - 1 ? 6 : 0 }}>
                            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 3 }}>{section.label}</div>
                            {section.rows.length === 1 && !section.rows[0].key ? (
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{section.rows[0].value}</div>
                            ) : (
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', fontSize: 'var(--text-xs)' }}>
                                {section.rows.map((r, ri) => (
                                  <div key={ri} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                                    <span style={{ color: 'var(--text-muted)' }}>{r.key}</span>
                                    <span style={{ fontFamily: 'var(--font-data)', color: r.valueColor || 'var(--text-primary)' }}>{r.value}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Raw JSON expandable */}
                    {expandedRaw[`${idx}`] && ev.rawJson && (
                      <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '8px 10px', marginTop: 4, fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', maxHeight: 120, overflowY: 'auto', lineHeight: 1.4 }}>
                        {ev.rawJson}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fundamental Tracking */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>FUNDAMENTAL TRACKING</div>
            <div className="card">
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
                <span>QUARTERLY ACTUALS VS THESIS EXPECTATIONS</span>
                <span>Last updated: Q4 2025 earnings (Mar 20)</span>
              </div>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--border)', paddingBottom: 3 }}>
                <span style={{ flex: 1, minWidth: 140, color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 9 }}>METRIC</span>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', minWidth: 60 }}>EXPECTED</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  {['Q3\'25', 'Q4\'25', 'Q1\'26', 'Q2\'26'].map(q => (
                    <span key={q} style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', minWidth: 44, textAlign: 'center' }}>{q}</span>
                  ))}
                </div>
                <div style={{ width: 60, textAlign: 'center' }}><span style={{ fontSize: 9, color: 'var(--text-muted)' }}>TREND</span></div>
              </div>
              {/* Rows */}
              {(ticker.fundamentals ?? []).map((f, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: i < (ticker.fundamentals ?? []).length - 1 ? '1px solid var(--border)' : 'none', fontSize: 'var(--text-xs)' }}>
                  <span style={{ flex: 1, color: 'var(--text-secondary)', minWidth: 140 }}>{f.metric}</span>
                  <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', minWidth: 60 }}>{f.expected}</span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {f.quarters.map((q, qi) => (
                      <span key={qi} style={{ fontFamily: 'var(--font-data)', minWidth: 44, textAlign: 'center', color: q.color }}>{q.value}</span>
                    ))}
                  </div>
                  <div style={{ width: 60, height: 16, background: 'var(--bg-tertiary)', borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: f.trendColor }}>{f.trend}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Learning Loop Contributions */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>LEARNING LOOP CONTRIBUTIONS</div>
            <div className="card">
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>FEEDBACK PATTERNS</div>
              <div style={{ marginBottom: 8 }}>
                {(ticker.feedbackPatterns ?? []).map((p, i) => (
                  <span key={i} style={{ fontFamily: 'var(--font-data)', fontSize: 9, padding: '2px 6px', borderRadius: 3, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border)', display: 'inline-flex', alignItems: 'center', gap: 3, marginRight: 4, marginBottom: 4 }}>
                    <span style={{ color: p.color }}>{p.icon}</span> {p.label}
                  </span>
                ))}
              </div>

              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>REFINEMENT PROPOSALS INFLUENCED</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
                {(ticker.refinementProposals ?? []).map((rp, i) => (
                  <div key={i} style={{ padding: '3px 0', borderBottom: i < (ticker.refinementProposals ?? []).length - 1 ? '1px solid var(--border)' : 'none', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{rp.text}</span>
                    <span style={{ fontFamily: 'var(--font-data)', color: rp.status === 'accepted' ? 'var(--positive)' : 'var(--text-muted)', fontSize: 10 }}>{rp.status}</span>
                  </div>
                ))}
              </div>

              <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>BEHAVIORAL SIGNALS</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                {(ticker.behavioralSignals ?? []).map((s, i) => (
                  <div key={i} style={{ padding: '3px 0' }}>
                    <span style={{ color: 'var(--positive)' }}>{'\u2713'}</span> {s}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Outcome Performance */}
          {(ticker.returnPct != null || (ticker as any).return_pct != null) && (
            <div style={{ display: 'flex', gap: 12, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', marginTop: 6 }}>
              <span style={{ color: (ticker.returnPct ?? (ticker as any).return_pct) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                Return: {(ticker.returnPct ?? (ticker as any).return_pct) >= 0 ? '+' : ''}{(ticker.returnPct ?? (ticker as any).return_pct).toFixed(1)}%
              </span>
              {(ticker as any).alpha_pct != null && (
                <span style={{ color: (ticker as any).alpha_pct >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                  Alpha: {(ticker as any).alpha_pct >= 0 ? '+' : ''}{(ticker as any).alpha_pct.toFixed(1)}%
                </span>
              )}
              {(ticker as any).thesis_played_out != null && (
                <span style={{ color: (ticker as any).thesis_played_out ? 'var(--positive)' : 'var(--negative)' }}>
                  {(ticker as any).thesis_played_out ? '✓ Thesis confirmed' : '✗ Thesis broke'}
                </span>
              )}
            </div>
          )}

          {/* Bottom action links */}
          <div style={{ display: 'flex', gap: 10, paddingTop: 4, borderTop: '1px solid var(--border)' }}>
            <Link to={`/ticker/${ticker.ticker}`} className="ticker" style={{ fontSize: 'var(--text-xs)', cursor: 'pointer', textDecoration: 'none' }}>View ticker detail &rarr;</Link>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', cursor: 'pointer' }}>Re-run thesis</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', cursor: 'pointer' }}>Re-run IC review</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', cursor: 'pointer' }}>Generate new memo</span>
          </div>
        </>
      )}

      {/* Reader Popup */}
      {readerPopup && (
        <ReaderPopup title={<span dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(readerPopup.title) }} />} onClose={() => setReaderPopup(null)}>
          <div
            className="reader-markdown"
            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(readerPopup.content, { breaks: true }) as string) }}
          />
        </ReaderPopup>
      )}
    </div>
  );
}

// ─── Memos Tab ────────────────────────────────────────────────────

function MemosTab({ initialTicker }: { initialTicker?: string }) {
  const queryClient = useQueryClient();
  const [memoTicker, setMemoTicker] = useState(initialTicker || '');
  const [memoType, setMemoType] = useState<'inv' | 'res'>('res');
  const [activeSection, setActiveSection] = useState(0);
  const [selectedMemoIndex, setSelectedMemoIndex] = useState(0);
  const [regenStatus, setRegenStatus] = useState<'idle' | 'running' | 'done'>('idle');

  const { data: memoData } = useQuery({
    queryKey: ['memo', memoTicker],
    queryFn: () => api.getMemo(memoTicker),
    enabled: memoTicker.length >= 1,
  });
  const { data: allMemos } = useQuery({
    queryKey: ['all-memos'],
    queryFn: () => api.getMemos(),
  });

  const allMemosForTicker: any[] = memoData?.memos ?? [];
  const hasResearch = allMemosForTicker.some((m: any) => m.run_type === 'research');
  const hasInvestment = allMemosForTicker.some((m: any) => m.run_type === 'investment');

  // Auto-select type when data loads; always reset position
  React.useEffect(() => {
    if (hasResearch && !hasInvestment) setMemoType('res');
    else if (hasInvestment && !hasResearch) setMemoType('inv');
    setActiveSection(0);
    setSelectedMemoIndex(0);
  }, [memoTicker, hasResearch, hasInvestment]); // eslint-disable-line react-hooks/exhaustive-deps

  // Filter to the selected type
  const dbType = memoType === 'res' ? 'research' : 'investment';
  const memos = allMemosForTicker.filter((m: any) => m.run_type === dbType);
  const hasMemos = memos.length > 0;

  // Use the selected version (default to latest = index 0)
  const safeVersionIndex = Math.min(selectedMemoIndex, Math.max(0, memos.length - 1));
  const selectedMemo = memos[safeVersionIndex];

  // Parse sections from the selected memo — keyed on memo identity so useMemo is stable
  const memoId = selectedMemo?.id ?? selectedMemo?.run_at ?? '';
  const sections = useMemo(() => {
    if (!selectedMemo?.full_output) return [];
    try {
      const raw = typeof selectedMemo.full_output === 'string'
        ? JSON.parse(selectedMemo.full_output)
        : selectedMemo.full_output;
      const rawSecs: any[] = raw?.sections ?? raw?.content_sections ?? [];
      const parsed = rawSecs.map((s: any) => ({
        title: (s.title ?? s.section ?? 'Section') as string,
        html: marked((s.content ?? s.text ?? '') as string, { breaks: true, gfm: true }) as string,
      }));
      if (parsed.length > 0) return parsed;
      // Fallback: render full content blob as single section
      if (raw?.content) {
        return [{ title: selectedMemo.run_type === 'research' ? 'Research Report' : 'Investment Memo', html: marked(raw.content, { breaks: true, gfm: true }) as string }];
      }
    } catch { /* ignore parse errors */ }
    return hasMemos ? [{ title: 'Memo', html: marked(selectedMemo?.summary ?? 'No content available.', { breaks: true, gfm: true }) as string }] : [];
  }, [memoId]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalSections = sections.length;
  // Clamp active section so it's always in-bounds (guards against switching type/version)
  const safeActiveSection = totalSections > 0 ? Math.min(activeSection, totalSections - 1) : 0;
  const allMemoList: any[] = allMemos?.memos ?? [];

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Left panel: TOC */}
      <div style={{ width: 260, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden', flexShrink: 0 }}>
        {/* Ticker search */}
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ position: 'relative' }}>
            <input
              className="search-input"
              value={memoTicker}
              onChange={e => { setMemoTicker(e.target.value.toUpperCase()); setActiveSection(0); }}
              placeholder="Search ticker..."
              style={{ fontFamily: 'var(--font-data)', color: 'var(--accent)', fontWeight: 600, letterSpacing: '0.05em', width: '100%' }}
            />
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
            {memoTicker
              ? hasMemos ? `${memos.length} memo${memos.length !== 1 ? 's' : ''} for ${memoTicker}` : `No memos for ${memoTicker}`
              : allMemoList.length > 0 ? `${allMemoList.length} total memos` : 'No memos generated yet'}
          </div>
        </div>

        {/* Memo type toggle */}
        <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
            {(['inv', 'res'] as const).map((t, i) => (
              <button
                key={t}
                onClick={() => { setMemoType(t); setActiveSection(0); }}
                style={{
                  flex: 1, padding: '5px 8px', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-ui)',
                  background: memoType === t ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                  color: memoType === t ? 'var(--accent)' : 'var(--text-secondary)',
                  border: 'none', borderLeft: i > 0 ? '1px solid var(--border)' : 'none',
                  cursor: 'pointer', textAlign: 'center',
                }}
              >
                {t === 'inv' ? 'Investment Memo' : 'Research Report'}
              </button>
            ))}
          </div>
          {memos.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <select
                value={safeVersionIndex}
                onChange={e => { setSelectedMemoIndex(Number(e.target.value)); setActiveSection(0); }}
                style={{ width: '100%', padding: '4px 6px', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontFamily: 'var(--font-data)', fontSize: 10 }}
              >
                {memos.map((m: any, i: number) => (
                  <option key={i} value={i}>
                    v{memos.length - i} — {m.run_at ? new Date(m.run_at).toLocaleDateString() : 'Unknown date'} {i === 0 ? '(latest)' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Table of contents */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          <div style={{ padding: '0 12px 6px', fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>TABLE OF CONTENTS</div>
          {sections.map((s, i) => (
            <div
              key={i}
              onClick={() => setActiveSection(i)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', cursor: 'pointer',
                fontSize: 'var(--text-xs)', color: safeActiveSection === i ? 'var(--accent)' : 'var(--text-secondary)',
                borderLeft: `2px solid ${safeActiveSection === i ? 'var(--accent)' : 'transparent'}`,
                background: safeActiveSection === i ? 'var(--accent-subtle)' : undefined,
              }}
            >
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: safeActiveSection === i ? 'var(--accent)' : 'var(--text-muted)', minWidth: 14 }}>{i + 1}</span>
              <span style={{ flex: 1 }}>{s.title}</span>
            </div>
          ))}
        </div>

        {/* Bottom actions */}
        <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <button
            className="btn btn-ghost"
            style={{ width: '100%', fontSize: 10, padding: 6 }}
            onClick={() => {
              if (!hasMemos || sections.length === 0) { alert('No memo loaded. Search for a ticker with a memo first.'); return; }
              const printWin = window.open('', '_blank');
              if (!printWin) { alert('Popup blocked. Allow popups for this site.'); return; }
              const title = `${memoTicker} — ${memoType === 'inv' ? 'Investment Memo' : 'Research Report'}`;
              const allHtml = sections.map((s, i) =>
                `<div style="page-break-after: ${i < sections.length - 1 ? 'always' : 'auto'}; margin-bottom: 32px;">` +
                `<h1 style="font-size: 20px; border-bottom: 1px solid #ccc; padding-bottom: 8px; margin-bottom: 16px;">${s.title}</h1>` +
                s.html +
                `</div>`
              ).join('\n');
              printWin.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
                <style>
                  body { font-family: Georgia, serif; max-width: 700px; margin: 40px auto; color: #111; line-height: 1.6; font-size: 14px; }
                  h1 { font-family: -apple-system, sans-serif; }
                  h2, h3 { font-family: -apple-system, sans-serif; margin-top: 24px; }
                  table { border-collapse: collapse; width: 100%; margin: 16px 0; }
                  td, th { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
                  th { background: #f5f5f5; font-weight: 600; }
                  ul, ol { padding-left: 24px; }
                  li { margin-bottom: 6px; }
                  blockquote { border-left: 3px solid #ccc; padding-left: 16px; color: #555; margin: 16px 0; }
                  .header { text-align: center; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 2px solid #333; }
                  .header h1 { font-size: 24px; margin: 0 0 4px; }
                  .header .meta { color: #666; font-size: 12px; }
                  @media print { body { margin: 20px; } }
                </style>
              </head><body>
                <div class="header">
                  <h1>${title}</h1>
                  <div class="meta">FundOps &mdash; ${new Date().toLocaleDateString()}</div>
                </div>
                ${allHtml}
              </body></html>`);
              printWin.document.close();
              setTimeout(() => printWin.print(), 300);
            }}
          >
            Export PDF
          </button>
          <button
            className="btn btn-ghost"
            style={{ width: '100%', fontSize: 10, padding: 6 }}
            disabled={!memoTicker || regenStatus === 'running'}
            onClick={async () => {
              if (!memoTicker) { alert('Search for a ticker first.'); return; }
              setRegenStatus('running');
              try {
                await (memoType === 'inv' ? api.generateInvestmentMemo(memoTicker) : api.generateResearchReport(memoTicker));
                queryClient.invalidateQueries({ queryKey: ['memo', memoTicker] });
                setRegenStatus('done');
                setTimeout(() => setRegenStatus('idle'), 3000);
              } catch { setRegenStatus('idle'); }
            }}
          >
            {regenStatus === 'running' ? 'Queued…' : regenStatus === 'done' ? '✓ Queued' : 'Re-generate'}
          </button>
        </div>
      </div>

      {/* Right panel: Section content */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', justifyContent: 'center' }}>
        {!memoTicker || (!hasMemos && memoTicker) ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1 }}>
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)', maxWidth: 340 }}>
              {!memoTicker && allMemoList.length === 0
                ? 'No memos generated yet. Approve a stock in Research and generate a memo to see it here.'
                : !memoTicker
                ? 'Search for a ticker to read its memos.'
                : `No memos found for ${memoTicker}. Generate one from the Research → Approved tab.`}
            </div>
          </div>
        ) : (
        <div style={{ maxWidth: 700, width: '100%', padding: '24px 32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>
              SECTION {safeActiveSection + 1} OF {totalSections}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: '3px 10px', opacity: safeActiveSection === 0 ? 0.3 : 1 }}
                disabled={safeActiveSection === 0}
                onClick={() => setActiveSection(prev => Math.max(0, prev - 1))}
              >
                &larr; Prev
              </button>
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: '3px 10px', opacity: safeActiveSection === totalSections - 1 ? 0.3 : 1 }}
                disabled={safeActiveSection === totalSections - 1}
                onClick={() => setActiveSection(prev => Math.min(totalSections - 1, prev + 1))}
              >
                Next &rarr;
              </button>
            </div>
          </div>
          {sections[safeActiveSection] && (
            <div className="reader-body memo-section-active" style={{ padding: 0 }} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(sections[safeActiveSection].html) }} />
          )}
        </div>
        )}
      </div>
    </div>
  );
}

// ─── Ask the Library Tab ──────────────────────────────────────────

function AskTab({ messages, setMessages }: {
  messages: { role: 'user' | 'ai'; content: string }[];
  setMessages: React.Dispatch<React.SetStateAction<{ role: 'user' | 'ai'; content: string }[]>>;
}) {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    const q = question.trim();
    if (!q || loading) return;
    setQuestion('');
    setMessages(prev => [...prev, { role: 'user', content: q }]);
    setLoading(true);
    try {
      const history = messages.map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }));
      const result = await api.askLibrary(q, history);
      setMessages(prev => [...prev, { role: 'ai', content: result.answer || 'No response.' }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'ai', content: 'Failed to get response. Check that your AI model is configured in Settings.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>LIBRARY</div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 600, margin: 0 }}>Ask the Library</h1>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          Query your entire research archive. The AI searches across thesis, IC review, memo, and outcome data to answer.
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', marginBottom: 8 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ marginBottom: 12, maxWidth: '85%', marginLeft: msg.role === 'user' ? 'auto' : undefined, marginRight: msg.role === 'ai' ? 'auto' : undefined }}>
            <div style={{
              padding: '8px 12px', borderRadius: 'var(--radius-lg)', fontSize: 'var(--text-sm)', lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              background: msg.role === 'user' ? 'var(--accent-subtle)' : 'var(--bg-ai)',
              color: msg.role === 'user' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: msg.role === 'ai' ? '1px solid var(--border)' : 'none',
              borderBottomRightRadius: msg.role === 'user' ? 2 : undefined,
              borderBottomLeftRadius: msg.role === 'ai' ? 2 : undefined,
            }}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ marginBottom: 12, maxWidth: '85%' }}>
            <div style={{ padding: '8px 12px', borderRadius: 'var(--radius-lg)', fontSize: 'var(--text-sm)', background: 'var(--bg-ai)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
              Searching library...
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexShrink: 0 }}>
        <input
          className="qa-input"
          style={{ flex: 1, padding: '8px 12px', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)', fontFamily: 'var(--font-ui)', fontSize: 'var(--text-sm)', outline: 'none' }}
          placeholder="Ask about predictions, accuracy patterns, assumption drift, or specific tickers..."
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleAsk(); }}
          disabled={loading}
        />
        <button className="btn btn-accent" style={{ padding: '8px 16px' }} onClick={handleAsk} disabled={loading}>
          {loading ? '...' : 'Ask'}
        </button>
      </div>
    </div>
  );
}

// ─── Empty State Tab ──────────────────────────────────────────────

function EmptyTab() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', maxWidth: 420 }}>
        <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>{'\uD83D\uDCDA'}</div>
        <div style={{ fontSize: 'var(--text-lg)', fontWeight: 500, marginBottom: 6 }}>No research archived yet</div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 16 }}>
          The library fills automatically as you run the pipeline. Every screener hit, thesis, IC review, memo, and portfolio event is archived here with full version history, structured data, and prediction tracking for the learning loops.
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          <Link to="/screener" className="btn btn-accent" style={{ textDecoration: 'none' }}>Run Screener</Link>
          <button className="btn btn-ghost">Import existing research</button>
        </div>
      </div>
    </div>
  );
}
