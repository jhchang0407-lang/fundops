import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/PageHeader';
import { KpiCard, KpiRow } from '../components/KpiCard';
import { HealthDot } from '../components/HealthDot';
import { ExpandableRow } from '../components/ExpandableRow';
import { fmtPct } from '../utils/formatFinancials';
import ThesisHealthBar from '../components/ThesisHealthBar';

// ── Types ──────────────────────────────────────────────────────────────

interface Lot {
  shares: number;
  cost_basis: number;
  date: string;
}

interface Holding {
  ticker: string;
  company_name?: string;
  shares?: number;
  cost_basis?: number;
  current_price?: number;
  pnl?: number;
  pnl_pct?: number;
  weight?: number;
  market_value?: number;
  health_score?: number;
  health_trend?: string; // 'up' | 'down' | 'flat'
  type?: string;
  buy_date?: string;
  lots?: Lot[];
  fair_value?: number;
  conviction?: number;
  thesis_synopsis?: string;
  assumptions?: Assumption[];
  recent_event?: string;
  thesis_health?: Assumption[];
  thesis_events?: { assumption: string; status: string; finding?: string }[];
}

interface Assumption {
  text: string;
  status: 'ok' | 'warning' | 'breach';
  score?: number;
  recent?: string;
}

interface ThesisAlert {
  type: string;
  ticker: string;
  message: string;
  severity?: 'warning' | 'info' | 'critical';
}

interface PortfolioData {
  holdings: Holding[];
  alerts: ThesisAlert[];
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  daily_change: number;
  positions_count: number;
  avg_health: number;
  position_breakdown?: string;
  cash?: number;
}

interface EditorRow {
  ticker: string;
  shares: string;
  cost_basis: string;
  date: string;
}

type PageState = 'data' | 'empty' | 'sync';

// ── Helpers ────────────────────────────────────────────────────────────

function fmtDollar(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toLocaleString()}`;
}

// fmtPct imported from ../utils/formatFinancials

function trendArrow(trend?: string): string {
  if (trend === 'down') return ' \u2198';    // ↘
  if (trend === 'falling') return ' \u2193';  // ↓
  return '';
}

function assumptionIcon(status: string) {
  if (status === 'ok') return <span style={{ color: 'var(--positive)' }}>{'\u2713'}</span>;
  if (status === 'warning') return <span style={{ color: 'var(--warning)' }}>{'\u25CF'}</span>;
  return <span style={{ color: 'var(--negative)' }}>{'\u2717'}</span>;
}

function assumptionColor(status: string) {
  if (status === 'ok') return 'var(--positive)';
  if (status === 'warning') return 'var(--warning)';
  return 'var(--negative)';
}

// ── Position Editor Popup ──────────────────────────────────────────────

function PositionEditor({
  holdings,
  hasStrategy,
  initialCash,
  onClose,
}: {
  holdings: Holding[];
  hasStrategy: boolean;
  initialCash?: number | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [cash, setCash] = useState<string>(initialCash != null ? initialCash.toFixed(2) : '');

  const [rows, setRows] = useState<EditorRow[]>(() => {
    // Expand holdings into individual lots (one row per lot)
    const existing: EditorRow[] = [];
    for (const h of holdings) {
      if (h.lots && h.lots.length > 0) {
        // Show each lot as a separate row
        for (const lot of h.lots) {
          existing.push({
            ticker: h.ticker,
            shares: String(lot.shares ?? ''),
            cost_basis: (lot.cost_basis ?? 0).toFixed(2),
            date: lot.date ?? '',
          });
        }
      } else {
        // No lots — show as single row
        existing.push({
          ticker: h.ticker,
          shares: String(h.shares ?? ''),
          cost_basis: h.cost_basis?.toFixed(2) ?? '',
          date: h.buy_date ?? '',
        });
      }
    }
    existing.push({ ticker: '', shares: '', cost_basis: '', date: '' });
    return existing;
  });

  const updateRow = useCallback(
    (idx: number, field: keyof EditorRow, value: string) => {
      setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));
    },
    [],
  );

  const removeRow = useCallback((idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const addRow = useCallback(() => {
    setRows((prev) => [...prev, { ticker: '', shares: '', cost_basis: '', date: '' }]);
  }, []);

  const handleSave = useCallback(async () => {
    const positions = rows
      .filter(r => r.ticker && parseFloat(r.shares) > 0)
      .map(r => ({
        ticker: r.ticker.trim().toUpperCase(),
        shares: parseFloat(r.shares),
        cost_basis: parseFloat(r.cost_basis) || 0,
        date: r.date || undefined,
      }));
    if (positions.length === 0 && !cash) { onClose(); return; }
    setSaveStatus('saving');
    try {
      const cashValue = cash ? parseFloat(cash) : undefined;
      const result = await api.savePositions(positions, cashValue);
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });

      // Warn about removed tickers (invalid, no price data)
      if (result.removed_tickers?.length) {
        const removed = result.removed_tickers.join(', ');
        setSaveStatus('idle');
        setRows(prev => {
          const invalidSet = new Set(result.removed_tickers.map((t: string) => t.toUpperCase()));
          return prev.filter(r => !invalidSet.has(r.ticker.toUpperCase()));
        });
        alert(`Removed invalid ticker(s): ${removed}\nNo price data found. Please check the ticker symbol and re-add.`);
        return;
      }

      setSaveStatus('saved');
      setTimeout(() => onClose(), 800);
    } catch {
      setSaveStatus('error');
    }
  }, [rows, holdings, hasStrategy, queryClient, onClose]);

  return (
    <div className="editor-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="editor-popup">
        <div className="editor-popup-header">
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 600 }}>
              Edit Positions
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Add, edit, or remove positions. Click Save when done.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {saveStatus === 'error' && <span style={{ fontSize: 10, color: 'var(--negative)' }}>Save failed</span>}
            {saveStatus === 'saved' && <span style={{ fontSize: 10, color: 'var(--positive)' }}>Saved!</span>}
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn btn-accent" onClick={handleSave} disabled={saveStatus === 'saving'}>
              {saveStatus === 'saving' ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        <div className="editor-popup-body">
          {/* Cash balance */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, padding: '8px 10px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius)' }}>
            <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 500, whiteSpace: 'nowrap' }}>Cash Balance</label>
            <div style={{ position: 'relative', flex: '0 0 160px' }}>
              <span style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>$</span>
              <input
                className="editor-input editor-input-num"
                style={{ paddingLeft: 20, width: '100%' }}
                value={cash}
                placeholder="0.00"
                onChange={(e) => setCash(e.target.value)}
              />
            </div>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Uninvested cash. Included in total portfolio value and weight calculations.
            </span>
          </div>

          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 8, padding: '6px 10px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius)' }}>
            Multiple rows with the same ticker are treated as separate lots. Cost basis will be automatically averaged by share count.
          </div>

          {/* Editable table */}
          <table>
            <thead>
              <tr>
                <th style={{ width: 100 }}>Ticker</th>
                <th className="num" style={{ width: 80 }}>Shares</th>
                <th className="num" style={{ width: 100 }}>Cost Basis</th>
                <th className="num" style={{ width: 110 }}>Date</th>
                <th style={{ width: 40 }} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => {
                const isLast = idx === rows.length - 1 && !row.ticker;
                return (
                  <tr key={idx}>
                    <td>
                      <input
                        className="editor-input editor-input-ticker"
                        value={row.ticker}
                        placeholder={isLast ? 'TICKER' : undefined}
                        onChange={(e) => updateRow(idx, 'ticker', e.target.value.toUpperCase())}
                      />
                    </td>
                    <td className="num">
                      <input
                        className="editor-input editor-input-num"
                        value={row.shares}
                        placeholder={isLast ? '0' : undefined}
                        onChange={(e) => updateRow(idx, 'shares', e.target.value)}
                      />
                    </td>
                    <td className="num">
                      <input
                        className="editor-input editor-input-num"
                        style={{ width: 80 }}
                        value={row.cost_basis}
                        placeholder={isLast ? '0.00' : undefined}
                        onChange={(e) => updateRow(idx, 'cost_basis', e.target.value)}
                      />
                    </td>
                    <td className="num">
                      <input
                        type="date"
                        className="editor-input"
                        value={row.date}
                        onChange={(e) => updateRow(idx, 'date', e.target.value)}
                      />
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {!(isLast) && (
                        <button className="editor-remove" onClick={() => removeRow(idx)}>
                          {'\u2715'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <button
            className="btn btn-ghost"
            style={{ width: '100%', padding: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 8 }}
            onClick={addRow}
          >
            + Add another position
          </button>

          <div style={{ marginTop: 12, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            {hasStrategy
              ? '✓ Strategy active — new positions will auto-run thesis research. Position type (core / tactical) is assigned by the Allocator after research completes.'
              : 'No strategy set — only P&L will be tracked. Set up your strategy in Chat to enable thesis tracking and health scores.'}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sync Panel ─────────────────────────────────────────────────────────

function SyncPanel({ onOpenEditor, hasStrategy }: { onOpenEditor: () => void; hasStrategy: boolean }) {
  return (
    <>
      <PageHeader
        sectionLabel="Portfolio"
        title="Sync Positions"
        subtitle="Add your holdings to track P&L, thesis health, and allocation."
      />

      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
        <div className="sync-card" style={{ maxWidth: 400, textAlign: 'center' }}>
          <div style={{ fontSize: 'var(--text-lg)', marginBottom: 8 }}>{'\u270E'}</div>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>Add Positions</div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 10 }}>
            Enter ticker, shares, cost basis, and purchase date. Multiple purchases of the same stock are tracked as separate lots and automatically combined.
          </div>
          <button className="btn btn-accent" style={{ width: '100%' }} onClick={onOpenEditor}>
            Open Editor
          </button>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', textAlign: 'center' }}>
        FundOps does not connect to brokerages. You execute trades externally and sync your positions here.
        {hasStrategy && (
          <span style={{ color: 'var(--positive)', marginLeft: 6 }}>
            ✓ Strategy active — thesis will auto-run on new positions.
          </span>
        )}
        {!hasStrategy && (
          <span style={{ color: 'var(--accent)', marginLeft: 6 }}>
            <Link to="/" style={{ color: 'var(--accent)' }}>Set up your strategy</Link> to enable thesis tracking.
          </span>
        )}
      </div>
    </>
  );
}

// ── Empty State ────────────────────────────────────────────────────────

function EmptyState({ onSync }: { onSync: () => void }) {
  return (
    <>
      <PageHeader sectionLabel="Portfolio" title="Held Positions" />
      <div className="card" style={{ textAlign: 'center', padding: 40 }}>
        <div style={{ fontSize: 'var(--text-lg)', fontWeight: 500, marginBottom: 6 }}>
          Add your portfolio
        </div>
        <div style={{
          fontSize: 'var(--text-sm)', color: 'var(--text-secondary)',
          marginBottom: 16, maxWidth: 420, marginLeft: 'auto', marginRight: 'auto',
        }}>
          Import your positions so FundOps can track P&amp;L, monitor thesis health, and recommend
          allocator actions. FundOps does not connect to brokers. You execute trades externally and sync back.
        </div>
        <button className="btn btn-accent" style={{ padding: '10px 24px', fontSize: 'var(--text-sm)' }} onClick={onSync}>
          Sync Positions
        </button>
      </div>
    </>
  );
}

// ── Holding Row (expanded content) ─────────────────────────────────────

function HoldingExpandedContent({ h, hasStrategy }: { h: Holding; hasStrategy: boolean }) {
  return (
    <>
      {/* Card 0: Purchase Lots */}
      {h.lots && h.lots.length > 1 && (
        <div className="expanded-card">
          <div className="expanded-card-title">Purchase History ({h.lots.length} lots)</div>
          <table style={{ width: '100%', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th style={{ textAlign: 'left', padding: '2px 0', fontWeight: 500 }}>Date</th>
                <th style={{ textAlign: 'right', padding: '2px 0', fontWeight: 500 }}>Shares</th>
                <th style={{ textAlign: 'right', padding: '2px 0', fontWeight: 500 }}>Cost/Share</th>
                <th style={{ textAlign: 'right', padding: '2px 0', fontWeight: 500 }}>Total Cost</th>
              </tr>
            </thead>
            <tbody>
              {h.lots.map((lot, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '3px 0' }}>{lot.date || 'N/A'}</td>
                  <td style={{ padding: '3px 0', textAlign: 'right' }}>{lot.shares.toLocaleString()}</td>
                  <td style={{ padding: '3px 0', textAlign: 'right' }}>${lot.cost_basis.toFixed(2)}</td>
                  <td style={{ padding: '3px 0', textAlign: 'right' }}>${(lot.shares * lot.cost_basis).toLocaleString()}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 600 }}>
                <td style={{ padding: '3px 0' }}>Total</td>
                <td style={{ padding: '3px 0', textAlign: 'right' }}>{(h.shares ?? 0).toLocaleString()}</td>
                <td style={{ padding: '3px 0', textAlign: 'right' }}>${(h.cost_basis ?? 0).toFixed(2)} avg</td>
                <td style={{ padding: '3px 0', textAlign: 'right' }}>${((h.shares ?? 0) * (h.cost_basis ?? 0)).toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Card 1: Thesis */}
      <div className="expanded-card">
        <div className="expanded-card-title">Thesis</div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 8 }}>
          {h.thesis_synopsis || (hasStrategy ? 'Thesis pending — will populate after next run.' : 'Set up your strategy to enable thesis tracking.')}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
          {h.buy_date && <>Bought {h.buy_date}</>}
          {h.lots && h.lots.length > 1 && <>{h.lots.length} lots</>}
          {h.fair_value != null && <> {'\u00B7'} FV ${h.fair_value}</>}
          {h.conviction != null && <> {'\u00B7'} IC conviction {h.conviction}/5</>}
        </div>
      </div>

      {/* Card 2: Key Assumptions */}
      <div className="expanded-card">
        <div className="expanded-card-title">Key Assumptions</div>
        {!hasStrategy ? (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Requires strategy — <Link to="/" style={{ color: 'var(--accent)' }}>set up strategy</Link>
          </div>
        ) : h.assumptions && h.assumptions.length > 0 ? (
          <div style={{ fontSize: 'var(--text-xs)' }}>
            {h.assumptions.map((a, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0',
                  borderBottom: i < h.assumptions!.length - 1 ? '1px solid var(--border)' : undefined,
                }}
              >
                {assumptionIcon(a.status)}
                <span style={{ flex: 1, color: 'var(--text-secondary)' }}>{a.text}</span>
                {a.score != null && (
                  <span style={{ fontFamily: 'var(--font-data)', color: assumptionColor(a.status) }}>
                    {a.score}/100
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>Pending — will populate after thesis run.</div>
        )}
        {h.recent_event && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 8 }}>
            Recent: {h.recent_event}
          </div>
        )}
      </div>

      {/* Thesis Health */}
      {h.thesis_health && h.thesis_health.length > 0 && (
        <div className="expanded-card">
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>THESIS HEALTH</div>
          <ThesisHealthBar assumptions={h.thesis_health as any} />
        </div>
      )}

      {/* Thesis Events (weekly web monitoring) */}
      {h.thesis_events && h.thesis_events.length > 0 && (
        <div className="expanded-card">
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>RECENT THESIS EVENTS</div>
          {h.thesis_events.map((evt: any, i: number) => (
            <div key={i} style={{ fontSize: 'var(--text-xs)', padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ color: evt.status === 'breach' ? 'var(--negative)' : 'var(--text-secondary)' }}>
                {evt.status === 'breach' ? '\u2717' : '\u2713'} {evt.assumption}
              </span>
              {evt.finding && <div style={{ color: 'var(--text-muted)', marginTop: 2, fontSize: 10 }}>{evt.finding.slice(0, 120)}...</div>}
            </div>
          ))}
        </div>
      )}

      {/* View full detail link */}
      <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', marginTop: 2 }}>
        <Link to={`/ticker/${h.ticker}`} className="ticker" style={{ fontSize: 'var(--text-xs)' }}>
          View full detail {'\u2192'}
        </Link>
      </div>
    </>
  );
}

// ── Main Component ─────────────────────────────────────────────────────

export function Portfolio() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<PortfolioData>({
    queryKey: ['portfolio'],
    queryFn: api.portfolioStatus,
  });

  const { data: strategyData } = useQuery({
    queryKey: ['strategy'],
    queryFn: api.getStrategy,
  });

  const hasStrategy = !!(strategyData?.strategy?.id || strategyData?.strategy_profile);

  const refreshMutation = useMutation({
    mutationFn: api.runPortfolio,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
  });

  const holdings = data?.holdings ?? [];
  const alerts = data?.alerts ?? [];
  const totalValue = data?.total_value ?? 0;
  const totalPnlPct = data?.total_pnl_pct ?? 0;
  const dailyChange = data?.daily_change ?? 0;
  const avgHealth = data?.avg_health ?? 0;
  const posBreakdown = data?.position_breakdown ?? '';

  // Positions with no thesis yet (health_score === 0 or undefined, no thesis_synopsis)
  const [pageState, setPageState] = useState<PageState>('data');
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [memoRunning, setMemoRunning] = useState(false);
  const [memoStatus, setMemoStatus] = useState<string | null>(null);

  const runMemosSequentially = async () => {
    const tickers = holdings.map(h => h.ticker);
    if (tickers.length === 0) return;
    setMemoRunning(true);
    let completed = 0;
    let failed = 0;
    for (const ticker of tickers) {
      // Research report first, then investment memo
      setMemoStatus(`Research report ${completed + 1}/${tickers.length}: ${ticker}...`);
      try {
        await api.generateResearchReport(ticker);
      } catch {
        failed++;
      }
      setMemoStatus(`Investment memo ${completed + 1}/${tickers.length}: ${ticker}...`);
      try {
        await api.generateInvestmentMemo(ticker);
      } catch {
        failed++;
      }
      completed++;
    }
    queryClient.invalidateQueries({ queryKey: ['portfolio'] });
    setMemoStatus(
      `Done: ${completed} ticker${completed !== 1 ? 's' : ''} (both memo types)${failed ? `, ${failed} failed` : ''}.`
    );
    setMemoRunning(false);
  };

  // Derive page state from data
  const effectiveState = !isLoading && holdings.length === 0 && pageState === 'data' ? 'empty' : pageState;

  const toggleExpand = useCallback((ticker: string) => {
    setExpandedTicker((prev) => (prev === ticker ? null : ticker));
  }, []);

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className="stack">
      {/* Sync panel state */}
      {effectiveState === 'sync' && (
        <SyncPanel onOpenEditor={() => setShowEditor(true)} hasStrategy={hasStrategy} />
      )}

      {/* Empty state */}
      {effectiveState === 'empty' && (
        <EmptyState onSync={() => setPageState('sync')} />
      )}

      {/* With data state */}
      {effectiveState === 'data' && (
        <>
          <PageHeader
            sectionLabel="Portfolio"
            title="Held Positions"
            subtitle={[
              fmtDollar(totalValue),
              dailyChange !== 0 ? `${dailyChange >= 0 ? '+' : ''}${fmtDollar(Math.abs(dailyChange))} today` : null,
              `${holdings.length} positions`,
              avgHealth ? `Health: ${avgHealth}` : null,
            ].filter(Boolean).join(' \u00B7 ')}
            actions={
              <>
                <button
                  className="btn btn-ghost"
                  onClick={() => refreshMutation.mutate()}
                  disabled={refreshMutation.isPending}
                >
                  {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Prices'}
                </button>
                <button className="btn btn-accent" onClick={() => setShowEditor(true)}>
                  Edit Positions
                </button>
              </>
            }
          />

          {/* KPIs */}
          <KpiRow>
            <KpiCard
              label="Portfolio Value"
              value={fmtDollar(totalValue)}
              detail={
                dailyChange !== 0 ? (
                  <span style={{ color: dailyChange >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                    {dailyChange >= 0 ? '+' : ''}{fmtDollar(Math.abs(dailyChange))} today
                  </span>
                ) : undefined
              }
            />
            <KpiCard
              label="Total P&L"
              value={fmtPct(totalPnlPct)}
              valueColor={totalPnlPct >= 0 ? 'var(--positive)' : 'var(--negative)'}
              detail={<span style={{ color: 'var(--text-muted)' }}>since inception</span>}
            />
            <KpiCard
              label="Positions"
              value={String(holdings.length)}
              detail={posBreakdown ? <span style={{ color: 'var(--text-muted)' }}>{posBreakdown}</span> : undefined}
            />
            <KpiCard
              label="Thesis Health"
              value={hasStrategy ? (avgHealth ? String(avgHealth) : '—') : 'No strategy'}
              valueColor={
                !hasStrategy ? 'var(--text-muted)'
                : avgHealth >= 70 ? 'var(--positive)'
                : avgHealth >= 40 ? 'var(--warning)'
                : avgHealth > 0 ? 'var(--negative)'
                : 'var(--text-muted)'
              }
              detail={
                hasStrategy
                  ? <span style={{ color: 'var(--text-muted)' }}>weighted avg</span>
                  : <Link to="/" style={{ color: 'var(--accent)', fontSize: 10 }}>Set up strategy →</Link>
              }
            />
          </KpiRow>

          {/* Strategy-aware banners */}
          {!hasStrategy && (
            <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 14px' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>Tracking P&amp;L only</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginLeft: 8 }}>
                  Set up your investment strategy to enable thesis tracking, health scores, and allocation recommendations.
                </span>
              </div>
              <Link to="/" className="btn btn-accent" style={{ whiteSpace: 'nowrap', textDecoration: 'none', padding: '5px 14px', fontSize: 'var(--text-xs)' }}>
                Set up strategy
              </Link>
            </div>
          )}

          {/* Memo Generation — runs sequentially to avoid API rate limits */}
          {holdings.length > 0 && (
            <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 14px' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                  Investment Memos
                </span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginLeft: 8 }}>
                  Full research reports. Runs one at a time to respect API limits.
                </span>
                {memoStatus && (
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{memoStatus}</div>
                )}
              </div>
              <button
                className="btn btn-accent"
                style={{ whiteSpace: 'nowrap', fontSize: 'var(--text-xs)' }}
                onClick={runMemosSequentially}
                disabled={memoRunning}
              >
                {memoRunning ? 'Running...' : `Generate Memos (${holdings.length})`}
              </button>
            </div>
          )}

          {/* Holdings Table */}
          <div className="table-shell" style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className="num">Shares</th>
                  <th className="num">Cost</th>
                  <th className="num">Price</th>
                  <th className="num">P&amp;L</th>
                  <th className="num">Weight</th>
                  <th>Health</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <ExpandableRow
                    key={h.ticker}
                    isExpanded={expandedTicker === h.ticker}
                    onToggle={() => toggleExpand(h.ticker)}
                    colSpan={8}
                    summaryColumns={[
                      // Ticker + company name
                      <span key="t">
                        <Link
                          to={`/ticker/${h.ticker}`}
                          className="ticker"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {h.ticker}
                        </Link>
                        {h.company_name && (
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 1 }}>
                            {h.company_name}
                          </div>
                        )}
                      </span>,
                      // Shares
                      <span key="s" className="num" style={{ fontFamily: 'var(--font-data)' }}>
                        {h.shares?.toLocaleString()}
                      </span>,
                      // Cost
                      <span key="c" className="num" style={{ fontFamily: 'var(--font-data)' }}>
                        ${h.cost_basis?.toFixed(2)}
                      </span>,
                      // Price
                      <span key="p" className="num" style={{ fontFamily: 'var(--font-data)' }}>
                        ${h.current_price?.toFixed(2)}
                      </span>,
                      // P&L
                      <span
                        key="pl"
                        className="num"
                        style={{
                          fontFamily: 'var(--font-data)',
                          color: (h.pnl_pct ?? 0) >= 0 ? 'var(--positive)' : 'var(--negative)',
                        }}
                      >
                        {fmtPct(h.pnl_pct ?? 0)}
                      </span>,
                      // Weight (red if concentration breach > 15%)
                      <span
                        key="w"
                        className="num"
                        style={{
                          fontFamily: 'var(--font-data)',
                          color: (h.weight ?? 0) > 15 ? 'var(--negative)' : undefined,
                        }}
                      >
                        {h.weight?.toFixed(1)}%
                      </span>,
                      // Health
                      <span key="h" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <HealthDot score={h.health_score ?? 0} showScore />
                        {h.health_trend && h.health_trend !== 'flat' && (
                          <span style={{ fontSize: 10, color: 'var(--negative)' }}>
                            {trendArrow(h.health_trend)}
                          </span>
                        )}
                        {h.thesis_health?.some((a: any) => a.status === 'breach') && (
                          <span style={{ color: 'var(--negative)', fontSize: 10, marginLeft: 4 }}>BREACH</span>
                        )}
                      </span>,
                      // Type (Allocator-assigned, read-only)
                      <span key="type" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                        {h.type ?? '—'}
                      </span>,
                    ]}
                    columnClasses={[undefined, 'num', 'num', 'num', 'num', 'num', undefined, undefined]}
                    expandedContent={<HoldingExpandedContent h={h} hasStrategy={hasStrategy} />}
                  />
                ))}
                {holdings.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 20 }}>
                      No positions loaded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Thesis Alerts */}
          {alerts.length > 0 && (
            <div className="card" style={{ marginTop: 8 }}>
              <div className="card-title">Thesis Alerts ({alerts.length})</div>
              {alerts.map((a, i) => (
                <div key={i} className={`alert-row${a.type === 'thesis_breach' || a.severity === 'critical' ? ' severity-critical' : ''}`}>
                  <span className="alert-icon" style={{
                    color: a.type === 'thesis_breach' || a.severity === 'critical' ? 'var(--negative)' : a.severity === 'warning' ? 'var(--warning)' : 'var(--text-muted)',
                  }}>
                    {a.type === 'thesis_breach' || a.severity === 'critical' ? '\u2717' : a.severity === 'warning' ? '\u26A0' : '\u25CF'}
                  </span>
                  <span>
                    <Link to={`/ticker/${a.ticker}`} className="ticker">{a.ticker}</Link>
                    {' '}{a.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Position Editor Popup (overlay, independent of page state) */}
      {showEditor && (
        <PositionEditor
          holdings={holdings}
          hasStrategy={hasStrategy}
          initialCash={data?.cash}
          onClose={() => setShowEditor(false)}
        />
      )}
    </div>
  );
}
