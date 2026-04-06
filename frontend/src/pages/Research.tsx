import React, { useState, type ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { VerdictBadge } from '../components/VerdictBadge';

// ── Types ──────────────────────────────────────────────────────────────

type TabId = 'thesis' | 'ic' | 'approved';

interface ThesisRow {
  ticker: string;
  company_name?: string;
  fair_value?: number;
  expected_return?: number;
  discount?: number;
  ic_verdict?: 'pass' | 'no_pass' | 'pending';
  conviction?: number | string;  // backend may return number or "LOW"/"MEDIUM"/"HIGH"
  conviction_max?: number;
  why_it_exists?: string;
  // Expanded detail
  thesis_summary?: string;
  thesis_narrative?: string;
  web_research_note?: string;
  // Constitution fit
  constitution_criteria?: { label: string; met: boolean; actual: string }[];
  anti_signals?: string[];
  similar_tickers?: { ticker: string; return_pct: number }[];
  // Valuation
  valuation_method?: string;
  current_pe?: string;
  fair_pe?: string;
  eps?: string;
  growth?: string;
  earnings_growth?: string;
  valuation_note?: string;
  // Pipeline stage
  stage?: 'screened' | 'thesis_complete';
}

interface ICReviewRow {
  ticker: string;
  company_name?: string;
  verdict: 'pass' | 'no_pass' | 'pending';
  base_return?: number;
  bear_return?: number;
  conviction?: number | string;  // backend may return number or string
  conviction_max?: number;
  key_risk?: string;
  criteria_met?: number;
  criteria_total?: number;
  anti_signal_count?: number;
  date?: string;
  // Expanded
  haircut_pct?: number;
  bear_hurdle?: number;
  bear_fail_reason?: string;
  discount_floor?: string;
  discount_actual?: string;
  discount_met?: boolean;
  scorecard?: { label: string; met: boolean; actual: string }[];
  anti_signals?: { label: string; value: string }[];
  ai_review?: string;
  key_assumptions?: string[];
}

interface ApprovedRow {
  ticker: string;
  company_name?: string;
  approved_date?: string;
  fair_value?: number;
  expected_return?: number;
  conviction?: number | string;
  conviction_max?: number;
  research_report_ready?: boolean;
  investment_memo_ready?: boolean;
  research_report_cost?: number;
  investment_memo_cost?: number;
}

// ── Helpers ──────────────────────────────────────────────────────────

/** Normalize conviction — backend may return a number (1-5) or string ("LOW"/"MEDIUM"/"HIGH") */
function formatConviction(conviction: number | string | undefined, max: number = 5): string {
  if (conviction == null) return '\u2014';
  if (typeof conviction === 'number') return `${conviction}/${max}`;
  const map: Record<string, string> = { LOW: '1/5', MEDIUM: '3/5', HIGH: '4/5', VERY_HIGH: '5/5' };
  return map[String(conviction).toUpperCase()] ?? String(conviction);
}

// ── Prose snippet — clean plain-text summary with View full link ─────
function stripMarkdown(raw: string): string {
  return raw
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')  // [text](url) → text
    .replace(/\*\*([^*]*)\*\*/g, '$1')          // **bold** → bold
    .replace(/\*([^*]*)\*/g, '$1')              // *italic* → italic
    .replace(/^#{1,6}\s+/gm, '')                // ## headers → plain
    .replace(/\|[^\n]*\|/g, '')                 // | table rows |
    .replace(/[-|]{3,}/g, '')                   // --- table separators
    .replace(/\n{2,}/g, ' ')                    // collapse multi-newlines
    .replace(/\n/g, ' ')                        // single newlines to space
    .replace(/\s{2,}/g, ' ')                    // collapse whitespace
    .trim();
}

function ProseSnippet({ text, ticker, limit = 600 }: { text?: string; ticker: string; limit?: number }) {
  if (!text) return <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>No narrative available. Run thesis for analysis.</span>;
  const clean = stripMarkdown(text);
  // Take up to 4-5 sentences within the char limit
  let cutoff = 0;
  let pos = 0;
  for (let s = 0; s < 5; s++) {
    const next = clean.indexOf('. ', pos);
    if (next < 0 || next + 1 > limit) break;
    cutoff = next + 1;
    pos = next + 2;
  }
  if (cutoff === 0) cutoff = Math.min(clean.length, limit);
  const summary = clean.length > cutoff ? clean.slice(0, cutoff).trimEnd() + '…' : clean;
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.6, flex: 1 }}>{summary}</span>
      <Link to={`/ticker/${ticker}`} style={{ fontSize: 10, color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap', flexShrink: 0, paddingTop: 2 }}>
        View full →
      </Link>
    </div>
  );
}

// ── Thesis Expanded Detail ────────────────────────────────────────────

function ThesisExpanded({ row }: { row: ThesisRow }) {
  const narrative = row.thesis_summary || row.thesis_narrative || row.why_it_exists;
  const q = (row as any).quality || {};
  const hasValuation = row.valuation_method && row.valuation_method !== 'screener';

  // Build metric items for the compact bar
  const metrics: { label: string; value: string; accent?: boolean; positive?: boolean }[] = [];
  if (hasValuation) {
    metrics.push({ label: 'Method', value: row.valuation_method?.replace(/_/g, ' ') || '\u2014' });
    metrics.push({ label: 'Fair Value', value: row.fair_value != null ? `$${row.fair_value}` : '\u2014', accent: true });
    if (row.current_pe) metrics.push({ label: 'P/E', value: `${row.current_pe}x` });
    if (row.fair_pe) metrics.push({ label: 'Fair P/E', value: `${row.fair_pe}x` });
    if (row.eps) metrics.push({ label: 'EPS', value: `$${row.eps}` });
  }
  if (row.growth) metrics.push({ label: 'Rev Growth', value: `${row.growth}%`, positive: Number(row.growth) > 0 });
  if (row.earnings_growth) metrics.push({ label: 'Earn Growth', value: `${row.earnings_growth}%`, positive: Number(row.earnings_growth) > 0 });
  if (q.gross_margin) metrics.push({ label: 'Gross Margin', value: `${q.gross_margin}%` });
  if (q.roic) metrics.push({ label: 'ROIC', value: `${q.roic}%` });
  if (q.roe) metrics.push({ label: 'ROE', value: `${q.roe}%` });
  if (q.debt_equity != null) metrics.push({ label: 'D/E', value: `${q.debt_equity}` });
  if (q.fcf_yield) metrics.push({ label: 'FCF Yield', value: `${q.fcf_yield}%` });

  return (
    <>
      {/* Full-width thesis narrative — use all available space */}
      {narrative && (
        <div className="expanded-card" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            {stripMarkdown(narrative)}
          </div>
        </div>
      )}

      {/* Compact metrics bar — all valuation + quality in one horizontal strip */}
      {metrics.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: '2px 16px', padding: '8px 12px',
          background: 'var(--bg-tertiary)', borderRadius: 'var(--radius)', marginBottom: 8,
          fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)',
        }}>
          {metrics.map((m) => (
            <div key={m.label} style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
              <span style={{ color: 'var(--text-muted)' }}>{m.label}</span>
              <span style={{
                fontWeight: m.accent ? 600 : 500,
                color: m.accent ? 'var(--accent)' : m.positive ? 'var(--positive)' : undefined,
              }}>
                {m.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Warnings */}
      {(row as any).return_validation?.warnings?.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          {(row as any).return_validation.warnings.map((w: string, i: number) => (
            <div key={i} className="grounding-warning">{'\u26A0'} {w}</div>
          ))}
        </div>
      )}

      {/* Precedent / similar research */}
      {(row as any).similar_research?.length > 0 && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 8 }}>
          <span style={{ fontFamily: 'var(--font-data)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>PRECEDENT </span>
          {(row as any).similar_research.map((s: any) => (
            <span key={s.ticker} style={{ marginRight: 8 }}>
              <Link to={`/ticker/${s.ticker}`} className="ticker">{s.ticker}</Link>
              <span style={{ color: s.verdict === 'PASS' ? 'var(--positive)' : s.verdict === 'NO_PASS' ? 'var(--negative)' : 'var(--text-muted)', marginLeft: 2 }}>
                {s.verdict || s.entry_type}
              </span>
              {s.expected_return && <span> {s.expected_return}%</span>}
            </span>
          ))}
        </div>
      )}

    </>
  );
}

// ── IC Review Expanded Detail ─────────────────────────────────────────

function ICExpanded({ row }: { row: ICReviewRow }) {
  return (
    <div className="expanded-cards" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginBottom: 8 }}>
      {/* Card 1: Bear Case Stress Test */}
      <div className="expanded-card">
        <div className="expanded-card-title">BEAR CASE STRESS TEST</div>
        <div style={{
          fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)',
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginBottom: 8,
        }}>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Base return</span>
            <div style={{ fontSize: 'var(--text-sm)' }}>{row.base_return ?? '\u2014'}%</div>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Bear return</span>
            <div style={{ fontSize: 'var(--text-sm)', color: (row.bear_return ?? 0) < (row.bear_hurdle ?? 15) ? 'var(--negative)' : undefined }}>
              {row.bear_return ?? '\u2014'}%
            </div>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Haircut applied</span>
            <div style={{ fontSize: 'var(--text-sm)' }}>{row.haircut_pct ?? 70}%</div>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Bear hurdle</span>
            <div style={{ fontSize: 'var(--text-sm)' }}>{row.bear_hurdle ?? 15}%</div>
          </div>
        </div>
        {row.bear_fail_reason && (
          <div style={{
            fontSize: 'var(--text-xs)', padding: '6px 8px',
            background: 'rgba(234,67,53,0.08)', borderRadius: 4, color: 'var(--negative)',
          }}>
            {row.bear_fail_reason}
          </div>
        )}
        {row.discount_floor && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 6 }}>
            Discount floor: {row.discount_floor} (steady-state). Actual: {row.discount_actual}.{' '}
            <span style={{ color: row.discount_met ? 'var(--positive)' : 'var(--negative)' }}>
              {row.discount_met ? 'Met.' : 'Not met.'}
            </span>
          </div>
        )}
      </div>

      {/* Card 2: Constitution Scorecard */}
      <div className="expanded-card">
        <div className="expanded-card-title">CONSTITUTION SCORECARD</div>
        {row.scorecard && row.scorecard.length > 0 ? (
          <div style={{ fontSize: 'var(--text-xs)', marginBottom: 8 }}>
            {row.scorecard.map((c) => (
              <div key={c.label} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 0', borderBottom: '1px solid var(--border)',
              }}>
                <span style={{ color: c.met ? 'var(--positive)' : 'var(--negative)' }}>
                  {c.met ? '\u2713' : '\u2717'}
                </span>
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{c.label}</span>
                <span style={{
                  fontFamily: 'var(--font-data)',
                  color: c.met ? 'var(--text-primary)' : 'var(--negative)',
                }}>{c.actual}</span>
                {(c as any).metric && <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 10, marginLeft: 4 }}>({(c as any).metric})</span>}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 8 }}>
            {row.criteria_met ?? 0}/{row.criteria_total ?? 0} criteria met, {row.anti_signal_count ?? 0} anti-signals
          </div>
        )}
        {row.anti_signals && row.anti_signals.length > 0 && (
          <>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>
              ANTI-SIGNALS
            </div>
            {row.anti_signals.map((a) => (
              <div key={a.label} style={{
                fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0',
              }}>
                <span style={{ color: 'var(--negative)' }}>{'\u26A0'}</span>
                <span style={{ color: 'var(--negative)' }}>{a.label}</span>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', marginLeft: 'auto' }}>{a.value}</span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Card 3: AI IC Review — truncated */}
      <div className="expanded-card">
        <div className="expanded-card-title">AI IC REVIEW</div>
        <div style={{ marginBottom: 8 }}>
          <ProseSnippet text={row.ai_review} ticker={row.ticker} />
        </div>
        {row.key_assumptions && row.key_assumptions.length > 0 && (
          <>
            <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>
              KEY ASSUMPTIONS TO MONITOR
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {row.key_assumptions.map((a) => (
                <span key={a} style={{
                  fontSize: 10, padding: '2px 7px', borderRadius: 10,
                  background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)',
                  border: '1px solid var(--border)',
                }}>{a}</span>
              ))}
            </div>
          </>
        )}
        {(row as any).similar_research?.length > 0 && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 8 }}>
            <span style={{ fontFamily: 'var(--font-data)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>PRECEDENT </span>
            {(row as any).similar_research.map((s: any) => (
              <span key={s.ticker} style={{ marginRight: 8 }}>
                <Link to={`/ticker/${s.ticker}`} className="ticker">{s.ticker}</Link>
                <span style={{ color: s.verdict === 'PASS' ? 'var(--positive)' : s.verdict === 'NO_PASS' ? 'var(--negative)' : 'var(--text-muted)', marginLeft: 2 }}>
                  {s.verdict || s.entry_type}
                </span>
                {s.expected_return && <span> {s.expected_return}%</span>}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Why It Exists — truncated with expand ────────────────────────────

export function _WhyItExists({ text }: { text?: string }) {
  const [expanded, setExpanded] = React.useState(false);
  if (!text) return <span style={{ color: 'var(--text-muted)' }}>{'\u2014'}</span>;

  const LIMIT = 120;
  const isLong = text.length > LIMIT;
  const display = (!isLong || expanded) ? text : text.slice(0, LIMIT).trimEnd() + '…';

  return (
    <div>
      <span style={{ lineHeight: 1.5 }}>{display}</span>
      {isLong && (
        <span
          onClick={() => setExpanded(v => !v)}
          style={{ marginLeft: 4, color: 'var(--accent)', cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'var(--font-data)', fontSize: 9 }}
        >
          {expanded ? 'less' : 'more'}
        </span>
      )}
    </div>
  );
}

// ── Thesis Tab ────────────────────────────────────────────────────────

function ThesisTab() {
  const queryClient = useQueryClient();
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<Record<string, string>>({});

  const { data } = useQuery<{ results: ThesisRow[] }>({
    queryKey: ['theses'],
    queryFn: api.listTheses,
  });

  const runThesis = useMutation({
    mutationFn: (ticker: string) => api.runThesis(ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['theses'] });
    },
  });

  const promoteTicker = useMutation({
    mutationFn: (ticker: string) => api.promoteTicker(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'overridden' }));
      queryClient.invalidateQueries({ queryKey: ['theses'] });
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
    },
  });

  const dismissTicker = useMutation({
    mutationFn: (ticker: string) => api.dismissTicker(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'dismissed' }));
      queryClient.invalidateQueries({ queryKey: ['theses'] });
    },
  });

  const rows: ThesisRow[] = data?.results ?? [];

  const screenedPending = rows.filter((r) => r.stage === 'screened');
  // Sort thesis-complete by expected return descending to identify top 10
  const thesisComplete = rows
    .filter((r) => r.stage === 'thesis_complete' || r.fair_value != null)
    .sort((a, b) => (b.expected_return ?? 0) - (a.expected_return ?? 0));
  const top10Tickers = new Set(thesisComplete.slice(0, 10).map((r) => r.ticker));
  const pendingIC = rows.filter((r) => r.stage === 'thesis_complete' && (!r.ic_verdict || r.ic_verdict === 'pending'));
  void thesisComplete; void pendingIC; // used for display-only derived counts

  const actionsCell = (row: ThesisRow) => {
    const status = actionStatus[row.ticker];
    if (status === 'overridden') return <span className="pill pill-positive" style={{ fontSize: 10 }}>Promoted</span>;
    if (status === 'dismissed') return <span className="pill" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Dismissed</span>;

    // + button: promote to next stage
    // For screened → runs thesis. For thesis_complete → moves to IC Review tab.
    const isPending = row.stage === 'screened'
      ? (runThesis.isPending && runThesis.variables === row.ticker)
      : (promoteTicker.isPending && promoteTicker.variables === row.ticker);

    const handlePromote = () => {
      if (row.stage === 'screened') {
        runThesis.mutate(row.ticker);
      } else {
        // Thesis-complete → promote to IC Review (just moves, doesn't run IC)
        promoteTicker.mutate(row.ticker);
      }
    };

    return (
      <span onClick={(e) => e.stopPropagation()} style={{ display: 'inline-flex', gap: 4 }}>
        <button
          className="btn btn-accent"
          style={{ fontSize: 10, padding: '3px 8px', minWidth: 24 }}
          onClick={handlePromote}
          disabled={isPending}
          title={row.stage === 'screened' ? 'Run Thesis' : 'Move to IC Review'}
        >
          {isPending ? '...' : '+'}
        </button>
        <button
          className="btn btn-ghost"
          style={{ fontSize: 10, padding: '3px 8px', minWidth: 24 }}
          onClick={() => dismissTicker.mutate(row.ticker)}
          disabled={dismissTicker.isPending && dismissTicker.variables === row.ticker}
          title="Dismiss"
        >
          {'\u2717'}
        </button>
      </span>
    );
  };

  if (rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
        No theses yet. Run the Screener to discover candidates, then generate theses here.
      </div>
    );
  }

  return (
    <>
    {/* Stats line */}
    <div style={{ marginBottom: 12 }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
        {screenedPending.length} screened · {thesisComplete.length} thesis complete · {pendingIC.length} pending IC
      </span>
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th className="num">Fair Value</th>
            <th className="num">Expected Return</th>
            <th className="num">Discount</th>
            <th className="num">Conviction</th>
            <th>Stage</th>
            <th style={{ textAlign: 'right', width: 70 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {/* Top 10 thesis-complete items — yellow border */}
          {thesisComplete.length > 0 && (
            <tr>
              <td colSpan={7} style={{ padding: '6px 0 2px', borderBottom: 'none' }}>
                <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--accent)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  TOP IDEAS — BEST {Math.min(10, thesisComplete.length)} BY EXPECTED RETURN
                </span>
              </td>
            </tr>
          )}
          {thesisComplete.map((row) => {
            if (actionStatus[row.ticker] === 'dismissed') return null;
            const isExpanded = expandedTicker === row.ticker;
            const isTop10 = top10Tickers.has(row.ticker);
            return (
              <React.Fragment key={row.ticker}>
                <tr
                  style={{ cursor: 'pointer', borderLeft: isTop10 ? '2px solid var(--accent)' : '2px solid var(--positive)' }}
                  onClick={() => setExpandedTicker(isExpanded ? null : row.ticker)}
                >
                  <td>
                    <Link to={`/ticker/${row.ticker}`} className="ticker" onClick={(e) => e.stopPropagation()}>
                      {row.ticker}
                    </Link>
                    {row.company_name && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
                        {row.company_name}
                      </div>
                    )}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {row.fair_value != null ? `$${row.fair_value}` : '\u2014'}
                  </td>
                  <td className="num" style={{
                    fontFamily: 'var(--font-data)',
                    color: (row.expected_return ?? 0) >= 20 ? 'var(--positive)' : undefined,
                  }}>
                    {row.expected_return != null ? `${row.expected_return.toFixed(1)}%` : '\u2014'}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {row.discount != null ? `${row.discount.toFixed(1)}%` : '\u2014'}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {formatConviction(row.conviction, row.conviction_max ?? 5)}
                  </td>
                  <td>
                    <span className="pill pill-positive" style={{ fontSize: 10 }}>COMPLETE</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>{actionsCell(row)}</td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan={7} style={{ padding: 0, borderTop: 'none' }}>
                      <div className="expanded-area">
                        <ThesisExpanded row={row} />
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                          <button
                            className="btn btn-ghost"
                            style={{ padding: '5px 12px', fontSize: 'var(--text-xs)' }}
                            onClick={(e) => { e.stopPropagation(); runThesis.mutate(row.ticker); }}
                            disabled={runThesis.isPending && runThesis.variables === row.ticker}
                          >
                            {runThesis.isPending && runThesis.variables === row.ticker ? 'Running...' : 'Re-run Thesis'}
                          </button>
                          <Link
                            to={`/library?ticker=${row.ticker}`}
                            className="btn btn-ghost"
                            style={{ padding: '5px 12px', fontSize: 'var(--text-xs)', textDecoration: 'none' }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            View in Library
                          </Link>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
          {/* Separator between thesis-complete and screened */}
          {thesisComplete.length > 0 && screenedPending.length > 0 && (
            <tr>
              <td colSpan={7} style={{ padding: '10px 0 2px', borderBottom: 'none' }}>
                <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  SCREENED — PENDING THESIS ({screenedPending.length})
                </span>
              </td>
            </tr>
          )}
          {screenedPending.map((row) => {
            if (actionStatus[row.ticker] === 'dismissed') return null;
            const isExpanded = expandedTicker === row.ticker;
            return (
              <React.Fragment key={row.ticker}>
                <tr
                  style={{ cursor: 'pointer' }}
                  onClick={() => setExpandedTicker(isExpanded ? null : row.ticker)}
                >
                  <td>
                    <Link to={`/ticker/${row.ticker}`} className="ticker" onClick={(e) => e.stopPropagation()}>
                      {row.ticker}
                    </Link>
                    {row.company_name && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
                        {row.company_name}
                      </div>
                    )}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {'\u2014'}
                  </td>
                  <td className="num" style={{
                    fontFamily: 'var(--font-data)',
                    color: (row.expected_return ?? 0) >= 20 ? 'var(--positive)' : undefined,
                  }}>
                    {row.expected_return != null ? `${row.expected_return.toFixed(1)}%` : '\u2014'}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {'\u2014'}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {'\u2014'}
                  </td>
                  <td>
                    <span className="pill" style={{ fontSize: 10, background: 'rgba(255,179,0,0.12)', color: 'var(--warning, #e6a700)' }}>SCREENED</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>{actionsCell(row)}</td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan={7} style={{ padding: 0, borderTop: 'none' }}>
                      <div className="expanded-area">
                        <ThesisExpanded row={row} />
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                          <button
                            className="btn btn-accent"
                            style={{ padding: '5px 12px', fontSize: 'var(--text-xs)' }}
                            onClick={(e) => { e.stopPropagation(); runThesis.mutate(row.ticker); }}
                            disabled={runThesis.isPending && runThesis.variables === row.ticker}
                          >
                            {runThesis.isPending && runThesis.variables === row.ticker ? 'Running...' : 'Run Thesis'}
                          </button>
                          <Link
                            to={`/library?ticker=${row.ticker}`}
                            className="btn btn-ghost"
                            style={{ padding: '5px 12px', fontSize: 'var(--text-xs)', textDecoration: 'none' }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            View in Library
                          </Link>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}

// ── IC Review Tab ─────────────────────────────────────────────────────

function ICReviewTab() {
  const queryClient = useQueryClient();
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<Record<string, string>>({});

  const { data } = useQuery<{ results: ICReviewRow[] }>({
    queryKey: ['ic-reviews'],
    queryFn: api.listICReviews,
  });

  const runIC = useMutation({
    mutationFn: (ticker: string) => api.runICReview(ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
      queryClient.invalidateQueries({ queryKey: ['approved'] });
    },
  });

  const overrideIC = useMutation({
    mutationFn: (ticker: string) => api.overrideICReview(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'overridden' }));
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
      queryClient.invalidateQueries({ queryKey: ['approved'] });
    },
  });

  const promoteTicker = useMutation({
    mutationFn: (ticker: string) => api.promoteTicker(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'overridden' }));
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
      queryClient.invalidateQueries({ queryKey: ['approved'] });
      queryClient.invalidateQueries({ queryKey: ['approved-list'] });
    },
  });

  const dismissTicker = useMutation({
    mutationFn: (ticker: string) => api.dismissTicker(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'dismissed' }));
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
    },
  });

  const rows: ICReviewRow[] = data?.results ?? [];

  // Counts for action bar
  const pendingIC = rows.filter((r) => r.verdict === 'pending');
  const passedIC = rows.filter((r) => r.verdict === 'pass');
  const failedIC = rows.filter((r) => r.verdict === 'no_pass');

  if (rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
        No theses ready for IC review yet. Generate theses first from the Thesis tab.
      </div>
    );
  }

  return (
    <>
    {/* Stats line */}
    <div style={{ marginBottom: 12 }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
        {pendingIC.length} pending · {passedIC.length} passed · {failedIC.length} failed
      </span>
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Verdict</th>
            <th className="num">Base Return</th>
            <th className="num">Bear Return</th>
            <th className="num">Conviction</th>
            <th>Key Risk</th>
            <th>Constitution Scorecard</th>
            <th>Date</th>
            <th style={{ textAlign: 'right', width: 70 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isExpanded = expandedTicker === row.ticker;
            const status = actionStatus[row.ticker];
            if (status === 'dismissed') return null;
            return (
              <React.Fragment key={row.ticker}>
                <tr
                  style={{ cursor: 'pointer' }}
                  onClick={() => setExpandedTicker(isExpanded ? null : row.ticker)}
                >
                  <td>
                    <Link to={`/ticker/${row.ticker}`} className="ticker" onClick={(e) => e.stopPropagation()}>
                      {row.ticker}
                    </Link>
                    {row.company_name && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
                        {row.company_name}
                      </div>
                    )}
                  </td>
                  <td><VerdictBadge verdict={row.verdict} /></td>
                  <td className="num" style={{
                    fontFamily: 'var(--font-data)',
                    color: (row.base_return ?? 0) >= 20 ? 'var(--positive)' : undefined,
                  }}>
                    {row.base_return != null ? `${row.base_return}%` : '\u2014'}
                  </td>
                  <td className="num" style={{
                    fontFamily: 'var(--font-data)',
                    color: (row.bear_return ?? 0) < 15 ? 'var(--negative)' : undefined,
                  }}>
                    {row.bear_return != null ? `${row.bear_return}%` : '\u2014'}
                  </td>
                  <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                    {formatConviction(row.conviction, row.conviction_max ?? 5)}
                  </td>
                  <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                    {row.key_risk || '\u2014'}
                  </td>
                  <td>
                    <span className="pill pill-positive">
                      {row.criteria_met ?? 0}/{row.criteria_total ?? 0} met
                    </span>
                    {(row.anti_signal_count ?? 0) > 0 ? (
                      <span className="pill pill-negative">{row.anti_signal_count} anti</span>
                    ) : (
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>0 anti</span>
                    )}
                  </td>
                  <td style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                    {row.date ? new Date(row.date).toLocaleDateString() : '\u2014'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {status === 'overridden' ? (
                      <span className="pill pill-positive" style={{ fontSize: 10 }}>Approved</span>
                    ) : status === 'dismissed' ? (
                      <span className="pill" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Dismissed</span>
                    ) : (
                      <span onClick={(e) => e.stopPropagation()} style={{ display: 'inline-flex', gap: 4 }}>
                        <button
                          className="btn btn-accent"
                          style={{ fontSize: 10, padding: '3px 8px', minWidth: 24 }}
                          onClick={() => {
                            if (row.verdict === 'pass') {
                              promoteTicker.mutate(row.ticker);
                            } else if (row.verdict === 'no_pass') {
                              overrideIC.mutate(row.ticker);
                            } else {
                              runIC.mutate(row.ticker);
                            }
                          }}
                          disabled={
                            (promoteTicker.isPending && promoteTicker.variables === row.ticker) ||
                            (runIC.isPending && runIC.variables === row.ticker) ||
                            (overrideIC.isPending && overrideIC.variables === row.ticker)
                          }
                          title={row.verdict === 'pass' ? 'Promote to Approved' : row.verdict === 'no_pass' ? 'Override to Approved' : 'Run IC Review'}
                        >
                          {(promoteTicker.isPending && promoteTicker.variables === row.ticker) || (runIC.isPending && runIC.variables === row.ticker) || (overrideIC.isPending && overrideIC.variables === row.ticker) ? '...' : '+'}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: 10, padding: '3px 8px', minWidth: 24 }}
                          onClick={() => dismissTicker.mutate(row.ticker)}
                          disabled={dismissTicker.isPending && dismissTicker.variables === row.ticker}
                          title="Dismiss"
                        >
                          {'\u2717'}
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan={9} style={{ padding: 0, borderTop: 'none' }}>
                      <div className="expanded-area">
                        <ICExpanded row={row} />
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                          <button
                            className="btn btn-accent"
                            style={{ padding: '5px 12px', fontSize: 'var(--text-xs)' }}
                            onClick={(e) => { e.stopPropagation(); runIC.mutate(row.ticker); }}
                            disabled={runIC.isPending && runIC.variables === row.ticker}
                          >
                            {runIC.isPending && runIC.variables === row.ticker ? 'Running...' : 'Run IC Review'}
                          </button>
                          {row.verdict === 'no_pass' && !actionStatus[row.ticker] && (
                            <>
                              <button
                                className="btn btn-ghost"
                                style={{ padding: '5px 12px', fontSize: 'var(--text-xs)' }}
                                onClick={(e) => { e.stopPropagation(); overrideIC.mutate(row.ticker); }}
                                disabled={overrideIC.isPending}
                              >
                                Override: Approve
                              </button>
                              <button
                                className="btn btn-ghost"
                                style={{ padding: '5px 12px', fontSize: 'var(--text-xs)' }}
                                onClick={(e) => { e.stopPropagation(); dismissTicker.mutate(row.ticker); }}
                                disabled={dismissTicker.isPending}
                              >
                                Dismiss
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}

// ── Approved Tab ──────────────────────────────────────────────────────

function ApprovedTab() {
  const queryClient = useQueryClient();
  const [actionStatus, setActionStatus] = useState<Record<string, string>>({});

  const dismissTicker = useMutation({
    mutationFn: (ticker: string) => api.dismissTicker(ticker),
    onSuccess: (_data, ticker) => {
      setActionStatus((s) => ({ ...s, [ticker]: 'dismissed' }));
      queryClient.invalidateQueries({ queryKey: ['approved'] });
    },
  });

  const { data } = useQuery<{ results: ApprovedRow[] }>({
    queryKey: ['approved'],
    queryFn: api.listApproved,
  });

  const genReport = useMutation({
    mutationFn: (ticker: string) => api.generateResearchReport(ticker),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approved'] }),
  });

  const genMemo = useMutation({
    mutationFn: (ticker: string) => api.generateInvestmentMemo(ticker),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approved'] }),
  });

  const rows: ApprovedRow[] = data?.results ?? [];

  const memoCount = rows.filter((r) => r.investment_memo_ready).length;
  const reportCount = rows.filter((r) => r.research_report_ready).length;

  const memoCell = (ready: boolean | undefined, onGenerate: () => void, _cost?: number, colorVar?: string, ticker?: string) => {
    if (ready) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--positive)' }} />
          <Link
            to={`/library?tab=memos${ticker ? `&ticker=${ticker}` : ''}`}
            className="btn btn-ghost"
            style={{ fontSize: 10, padding: '3px 8px', textDecoration: 'none' }}
          >
            Read
          </Link>
        </div>
      );
    }
    const isResearch = colorVar === 'info';
    return (
      <button
        className={isResearch ? 'btn btn-ghost' : 'btn btn-accent'}
        style={{
          fontSize: 10,
          padding: '3px 8px',
          ...(isResearch ? { color: 'var(--info)', borderColor: 'rgba(66,133,244,0.3)' } : {}),
        }}
        onClick={onGenerate}
      >
        Generate
      </button>
    );
  };

  if (rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
        <div style={{ marginBottom: 8 }}>No approved stocks yet.</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          Workflow: IC Review tab → run IC Review on pending tickers → pass verdict → click <strong>+</strong> to promote here.
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Stats line */}
      <div style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
          {rows.length} approved · {memoCount} memos · {reportCount} reports
        </span>
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 10 }}>
        IC-passed stocks ready for memo generation. Two memo types:{' '}
        <strong style={{ color: 'var(--info)' }}>Research Report</strong> (fixed template) and{' '}
        <strong style={{ color: 'var(--accent)' }}>Investment Memo</strong> (tailored to your strategy).
      </div>
      <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Approved</th>
              <th className="num">FV</th>
              <th className="num">Return</th>
              <th className="num">Conv.</th>
              <th style={{ textAlign: 'center' }}>Research Report</th>
              <th style={{ textAlign: 'center' }}>Investment Memo</th>
              <th style={{ textAlign: 'right', width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const status = actionStatus[row.ticker];
              if (status === 'dismissed') return null;
              return (
              <tr key={row.ticker}>
                <td>
                  <Link to={`/ticker/${row.ticker}`} className="ticker">{row.ticker}</Link>
                  {row.company_name && (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
                      {row.company_name}
                    </div>
                  )}
                </td>
                <td style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                  {row.approved_date ? new Date(row.approved_date).toLocaleDateString() : '\u2014'}
                </td>
                <td className="num" style={{ fontFamily: 'var(--font-data)' }}>
                  {row.fair_value != null ? `$${row.fair_value}` : '\u2014'}
                </td>
                <td className="num" style={{
                  fontFamily: 'var(--font-data)',
                  color: (row.expected_return ?? 0) >= 20 ? 'var(--positive)' : undefined,
                }}>
                  {row.expected_return != null ? `${row.expected_return}%` : '\u2014'}
                </td>
                <td className="num" style={{
                  fontFamily: 'var(--font-data)',
                  color: typeof row.conviction === 'number' && row.conviction <= 2 ? 'var(--warning)' : undefined,
                }}>
                  {formatConviction(row.conviction, row.conviction_max ?? 5)}
                </td>
                <td style={{ textAlign: 'center' }}>
                  {memoCell(row.research_report_ready, () => genReport.mutate(row.ticker), row.research_report_cost, 'info', row.ticker)}
                </td>
                <td style={{ textAlign: 'center' }}>
                  {memoCell(row.investment_memo_ready, () => genMemo.mutate(row.ticker), row.investment_memo_cost, 'accent', row.ticker)}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    className="btn btn-ghost"
                    style={{ fontSize: 10, padding: '3px 8px', minWidth: 24 }}
                    onClick={() => dismissTicker.mutate(row.ticker)}
                    disabled={dismissTicker.isPending && dismissTicker.variables === row.ticker}
                    title="Remove from approved"
                  >
                    {'\u2717'}
                  </button>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Explanation bar */}
      <div style={{
        marginTop: 10, padding: '8px 12px', background: 'var(--bg-secondary)',
        border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
        fontSize: 'var(--text-xs)', color: 'var(--text-muted)', display: 'flex', gap: 20,
      }}>
        <div>
          <strong style={{ color: 'var(--info)' }}>Research Report</strong> {'\u2014'} Fixed template. Industry analysis, TAM, peer comps, financial deep dive, risks. Same structure for every stock.
        </div>
        <div>
          <strong style={{ color: 'var(--accent)' }}>Investment Memo</strong> {'\u2014'} Tailored to your constitution. Thesis fit, return sources through your lens, structured decision outputs, strategy-aware scenarios.
        </div>
      </div>
    </>
  );
}

// ── Tab Config ────────────────────────────────────────────────────────

// ── Main Component ────────────────────────────────────────────────────

export default function Research() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabId>('thesis');
  // Refetch every 15s so pipeline results appear without manual refresh
  const { data: thesisData } = useQuery<{ results: ThesisRow[] }>({ queryKey: ['thesis-list'], queryFn: api.listTheses, refetchInterval: 15_000, staleTime: 10_000 });
  const { data: icData } = useQuery<{ results: ICReviewRow[] }>({ queryKey: ['ic-review-list'], queryFn: api.listICReviews, refetchInterval: 15_000, staleTime: 10_000 });
  const { data: approvedData } = useQuery<{ results: ApprovedRow[] }>({ queryKey: ['approved-list'], queryFn: api.listApproved, refetchInterval: 15_000, staleTime: 10_000 });

  // Derive counts for action buttons
  const thesisRows = thesisData?.results ?? [];
  // screenedPending count available via thesisRows.filter if needed
  const icRows = icData?.results ?? [];
  const _pendingIC = icRows.filter((r) => r.verdict === 'pending');
  void _pendingIC; // count available for tab badges
  const approvedRows = approvedData?.results ?? [];
  const approvedWithoutMemo = approvedRows.filter((r) => !r.investment_memo_ready);
  const approvedWithoutReport = approvedRows.filter((r) => !r.research_report_ready);

  // Batch progress tracking
  const [batchStatus, setBatchStatus] = useState<string | null>(null);

  // Page-level batch mutations — all run sequentially with progress
  const runBatchThesis = useMutation({
    mutationFn: async () => {
      const tickers = thesisRows.map((r) => r.ticker);
      for (let i = 0; i < tickers.length; i++) {
        setBatchStatus(`Running thesis ${i + 1}/${tickers.length}: ${tickers[i]}...`);
        const result = await api.runThesis(tickers[i]);
        // Wait for job to complete before starting the next one
        if (result?.job_id) {
          for (let j = 0; j < 120; j++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
              const job = await api.jobStatus(result.job_id);
              if (job?.status === 'complete' || job?.status === 'failed') break;
            } catch { break; }
          }
        }
      }
      setBatchStatus(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['theses'] });
      queryClient.invalidateQueries({ queryKey: ['thesis-list'] });
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
      queryClient.invalidateQueries({ queryKey: ['ic-review-list'] });
    },
  });

  const runBatchIC = useMutation({
    mutationFn: async () => {
      const tickers = icRows.map((r: any) => r.ticker);
      for (let i = 0; i < tickers.length; i++) {
        setBatchStatus(`Running IC review ${i + 1}/${tickers.length}: ${tickers[i]}...`);
        const result = await api.runICReview(tickers[i]);
        if (result?.job_id) {
          for (let j = 0; j < 120; j++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
              const job = await api.jobStatus(result.job_id);
              if (job?.status === 'complete' || job?.status === 'failed') break;
            } catch { break; }
          }
        }
      }
      setBatchStatus(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ic-reviews'] });
      queryClient.invalidateQueries({ queryKey: ['ic-review-list'] });
      queryClient.invalidateQueries({ queryKey: ['approved'] });
      queryClient.invalidateQueries({ queryKey: ['approved-list'] });
    },
  });

  const runBatchMemo = useMutation({
    mutationFn: async () => {
      for (let i = 0; i < approvedWithoutMemo.length; i++) {
        setBatchStatus(`[${i + 1}/${approvedWithoutMemo.length}] Investment Memo: ${approvedWithoutMemo[i].ticker}...`);
        const res = await api.generateInvestmentMemo(approvedWithoutMemo[i].ticker);
        if (res?.job_id) {
          for (let j = 0; j < 180; j++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
              const job = await api.jobStatus(res.job_id);
              if (job?.status === 'complete' || job?.status === 'failed') break;
            } catch { break; }
          }
        }
        queryClient.invalidateQueries({ queryKey: ['approved-list'] });
      }
      setBatchStatus(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approved'] });
      queryClient.invalidateQueries({ queryKey: ['approved-list'] });
    },
  });

  const runBatchReport = useMutation({
    mutationFn: async () => {
      for (let i = 0; i < approvedWithoutReport.length; i++) {
        setBatchStatus(`[${i + 1}/${approvedWithoutReport.length}] Research Report: ${approvedWithoutReport[i].ticker}...`);
        const res = await api.generateResearchReport(approvedWithoutReport[i].ticker);
        if (res?.job_id) {
          for (let j = 0; j < 180; j++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
              const job = await api.jobStatus(res.job_id);
              if (job?.status === 'complete' || job?.status === 'failed') break;
            } catch { break; }
          }
        }
        queryClient.invalidateQueries({ queryKey: ['approved-list'] });
      }
      setBatchStatus(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approved'] });
      queryClient.invalidateQueries({ queryKey: ['approved-list'] });
    },
  });

  const approvedWithoutBoth = approvedRows.filter((r) => !r.investment_memo_ready || !r.research_report_ready);

  const runBatchBoth = useMutation({
    mutationFn: async () => {
      // Build a sequential queue: one memo at a time to respect API limits
      const queue: { ticker: string; type: 'report' | 'memo'; label: string }[] = [];
      for (const row of approvedRows) {
        if (!row.research_report_ready) queue.push({ ticker: row.ticker, type: 'report', label: 'Research Report' });
        if (!row.investment_memo_ready) queue.push({ ticker: row.ticker, type: 'memo', label: 'Investment Memo' });
      }

      for (let i = 0; i < queue.length; i++) {
        const item = queue[i];
        setBatchStatus(`[${i + 1}/${queue.length}] ${item.label}: ${item.ticker}...`);
        const res = item.type === 'report'
          ? await api.generateResearchReport(item.ticker)
          : await api.generateInvestmentMemo(item.ticker);
        // Wait for job to finish before starting next
        if (res?.job_id) {
          for (let j = 0; j < 180; j++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
              const job = await api.jobStatus(res.job_id);
              if (job?.status === 'complete' || job?.status === 'failed') break;
            } catch { break; }
          }
        }
        // Refresh list after each so UI updates progressively
        queryClient.invalidateQueries({ queryKey: ['approved-list'] });
      }
      setBatchStatus(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approved'] });
      queryClient.invalidateQueries({ queryKey: ['approved-list'] });
    },
  });

  // Build the action button based on active tab
  let headerAction: ReactNode = null;
  if (activeTab === 'thesis') {
    headerAction = (
      <button
        className="btn btn-accent"
        onClick={() => runBatchThesis.mutate()}
        disabled={runBatchThesis.isPending || thesisRows.length === 0}
        style={{ fontSize: 'var(--text-xs)' }}
      >
        {runBatchThesis.isPending ? 'Generating Theses...' : `Run Thesis Generation${thesisRows.length > 0 ? ` (${thesisRows.length})` : ''}`}
      </button>
    );
  } else if (activeTab === 'ic' && icRows.length > 0) {
    headerAction = (
      <button
        className="btn btn-accent"
        onClick={() => runBatchIC.mutate()}
        disabled={runBatchIC.isPending}
        style={{ fontSize: 'var(--text-xs)' }}
      >
        {runBatchIC.isPending ? 'Running IC Reviews...' : `Run IC Review (${icRows.length})`}
      </button>
    );
  } else if (activeTab === 'approved' && approvedRows.length > 0) {
    const bothPending = runBatchBoth.isPending || runBatchReport.isPending || runBatchMemo.isPending;
    headerAction = (
      <>
        <button
          className="btn btn-ghost"
          onClick={() => runBatchReport.mutate()}
          disabled={bothPending || approvedWithoutReport.length === 0}
          style={{ fontSize: 'var(--text-xs)', color: 'var(--info)', borderColor: 'rgba(66,133,244,0.3)' }}
        >
          {runBatchReport.isPending ? 'Generating...' : `Reports${approvedWithoutReport.length > 0 ? ` (${approvedWithoutReport.length})` : ''}`}
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => runBatchMemo.mutate()}
          disabled={bothPending || approvedWithoutMemo.length === 0}
          style={{ fontSize: 'var(--text-xs)' }}
        >
          {runBatchMemo.isPending ? 'Generating...' : `Memos${approvedWithoutMemo.length > 0 ? ` (${approvedWithoutMemo.length})` : ''}`}
        </button>
        <button
          className="btn btn-accent"
          onClick={() => runBatchBoth.mutate()}
          disabled={bothPending || approvedWithoutBoth.length === 0}
          style={{ fontSize: 'var(--text-xs)' }}
        >
          {runBatchBoth.isPending ? 'Generating...' : `Generate Both${approvedWithoutBoth.length > 0 ? ` (${approvedWithoutBoth.length})` : ''}`}
        </button>
      </>
    );
  }

  const tabConfig = [
    { id: 'thesis' as TabId, label: 'Thesis', count: (thesisData?.results ?? []).length },
    { id: 'ic' as TabId, label: 'IC Review', count: (icData?.results ?? []).length },
    { id: 'approved' as TabId, label: 'Approved', count: (approvedData?.results ?? []).length },
  ];

  return (
    <div>
      <PageHeader
        sectionLabel="Research"
        title="Thesis + IC Pipeline"
        subtitle="Validated ideas, IC verdicts, and what still needs memo-level work."
        actions={headerAction}
      />

      {/* Batch progress */}
      {batchStatus && (
        <div style={{ padding: '6px 14px', background: 'var(--accent-subtle)', borderRadius: 'var(--radius)', marginBottom: 8, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--accent)' }}>
          {batchStatus}
        </div>
      )}

      {/* Tab bar */}
      <div className="tab-bar">
        {tabConfig.map((tab) => (
          <button
            key={tab.id}
            className={`tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}{' '}
            <span className="tab-count">{tab.count}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'thesis' && <ThesisTab />}
      {activeTab === 'ic' && <ICReviewTab />}
      {activeTab === 'approved' && <ApprovedTab />}
    </div>
  );
}
