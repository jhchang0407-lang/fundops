import { useState } from 'react';
import DOMPurify from 'dompurify';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { parseOutput } from '../api/utils';
import { formatResearchProse, urlHostname } from '../utils/formatProse';
import ReaderPopup from '../components/ReaderPopup';
import { pct, fmtPct } from '../utils/formatFinancials';

type Tab = 'overview' | 'research' | 'health' | 'evidence';

/* ---------- tiny helpers ---------- */
function fmt(v: number | string | undefined | null, suffix = '') {
  if (v == null || v === '') return '\u2014';
  return `${v}${suffix}`;
}
// fmtPct and pct imported from ../utils/formatFinancials
function fmtUsd(v: number | undefined | null, decimals = 0) {
  if (v == null) return '\u2014';
  return `$${Number(v).toFixed(decimals)}`;
}
function fmtBigUsd(v: number | undefined | null) {
  if (v == null) return '\u2014';
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(0)}`;
}

function colorFor(v: number | undefined | null) {
  if (v == null) return undefined;
  return v >= 0 ? 'var(--positive)' : 'var(--negative)';
}

/* ---------- Sub-components ---------- */

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-data)', color }}>{value}</span>
    </div>
  );
}

function KpiMini({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="kpi-mini">
      <div className="kpi-mini-label">{label}</div>
      <div className="kpi-mini-value" style={{ color }}>{value}</div>
    </div>
  );
}

/* ============================================================
   OVERVIEW TAB
   ============================================================ */
function OverviewTab({ detail, timeline, portfolio }: { detail: any; timeline: any[]; portfolio: any }) {
  const metrics = detail?.metrics || detail?.fundamentals || {};
  const position = portfolio?.position || detail?.position;

  return (
    <div className="two-col">
      {/* Left: Key Metrics + Position */}
      <div>
        <div className="td-section-title">KEY METRICS</div>
        <div className="card" style={{ marginBottom: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 'var(--text-xs)' }}>
            <MetricRow label="Revenue Growth" value={fmtPct(metrics.revenue_growth ?? metrics.rev_growth)} color={colorFor(metrics.revenue_growth ?? metrics.rev_growth)} />
            <MetricRow label="Earnings Growth" value={fmtPct(metrics.earnings_growth)} color={colorFor(metrics.earnings_growth)} />
            <MetricRow label="Gross Margin" value={pct(metrics.gross_margin)} />
            <MetricRow label="Operating Margin" value={pct(metrics.op_margin ?? metrics.operating_margin)} />
            <MetricRow label="Net Margin" value={pct(metrics.net_margin)} />
            <MetricRow label="ROE" value={pct(metrics.roe)} />
            <MetricRow label="ROIC" value={pct(metrics.roic)} />
            <MetricRow label="FCF Yield" value={pct(metrics.fcf_yield)} />
            <MetricRow label="FCF Conversion" value={pct(metrics.fcf_conversion, 0)} />
            <MetricRow label="Debt/Equity" value={metrics.debt_equity != null ? `${Number(metrics.debt_equity).toFixed(2)}x` : '\u2014'} />
            <MetricRow label="Implied Growth" value={pct(metrics.implied_growth)} />
            <MetricRow label="Income Quality" value={metrics.income_quality != null ? `${Number(metrics.income_quality).toFixed(2)}` : '\u2014'} />
          </div>
        </div>

        {position && (
          <>
            <div className="td-section-title" style={{ marginTop: 12 }}>YOUR POSITION</div>
            <div className="card">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 'var(--text-xs)' }}>
                <MetricRow label="Shares" value={fmt(position.shares)} />
                <MetricRow label="Cost Basis" value={fmtUsd(position.cost_basis, 2)} />
                <MetricRow label="Market Value" value={fmtUsd(position.market_value)} />
                <MetricRow label="P&L" value={position.pnl != null ? `${position.pnl >= 0 ? '+' : ''}${fmtUsd(position.pnl)}${position.pnl_pct != null ? ` (${fmtPct(position.pnl_pct)})` : ''}` : '\u2014'} color={colorFor(position.pnl)} />
                <MetricRow label="Weight" value={fmt(position.weight, '%')} />
                <MetricRow label="Type" value={fmt(position.type ?? position.position_type)} />
              </div>
            </div>
          </>
        )}
      </div>

      {/* Right: Judgment Event Timeline */}
      <div>
        <div className="td-section-title">JUDGMENT EVENT TIMELINE</div>
        <TimelineView events={timeline} />
      </div>
    </div>
  );
}

/* ---------- Timeline ---------- */
const DOT_COLORS: Record<string, string> = {
  screened: 'var(--text-muted)',
  promoted: 'var(--info)',
  thesis: 'var(--info)',
  ic_pass: 'var(--positive)',
  ic_review: 'var(--positive)',
  ic_fail: 'var(--negative)',
  memo: 'var(--accent)',
  held: 'var(--positive)',
  outcome: 'var(--positive)',
};

const TYPE_COLORS: Record<string, string> = {
  screened: 'var(--text-muted)',
  promoted: 'var(--info)',
  thesis: 'var(--info)',
  ic_pass: 'var(--positive)',
  ic_review: 'var(--positive)',
  ic_fail: 'var(--negative)',
  memo: 'var(--accent)',
  held: 'var(--positive)',
  outcome: 'var(--positive)',
};

function TimelineView({ events }: { events: any[] }) {
  if (!events || events.length === 0) {
    return <div className="card"><div className="muted">No event timeline available yet.</div></div>;
  }

  return (
    <div className="timeline">
      {events.map((evt: any, i: number) => {
        const evtType = (evt.event_type || evt.type || evt.agent || '').toLowerCase().replace(/[\s-]/g, '_');
        const dotColor = DOT_COLORS[evtType] || 'var(--text-muted)';
        const typeColor = TYPE_COLORS[evtType] || 'var(--text-muted)';
        const label = (evt.label || evt.event_type || evt.type || evt.agent || '').toUpperCase();
        const isIC = evtType.includes('ic');
        const isOutcome = evtType === 'held' || evtType === 'outcome';

        return (
          <div key={i}>
            {evt.connector && (
              <div className="timeline-connector">{'\u2193'} {evt.connector}</div>
            )}
            <div className="timeline-event">
              <div className="timeline-dot" style={{ background: dotColor }} />
              <div className="timeline-content" style={isOutcome ? { borderColor: 'var(--positive)' } : undefined}>
                <div className="timeline-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="timeline-type" style={{ color: typeColor }}>{label}</span>
                    {isIC && evt.verdict && (
                      <span className={evt.verdict === 'PASS' ? 'verdict-pass' : 'verdict-fail'}>{evt.verdict}</span>
                    )}
                  </div>
                  <span className="timeline-date">{evt.date || evt.run_at?.slice(0, 10) || ''}</span>
                </div>
                {evt.body && <div className="timeline-body">{evt.body}</div>}
                {evt.meta && <div className="timeline-meta">{evt.meta}</div>}
                {evt.stats && (
                  <div style={{ display: 'flex', gap: 12, marginTop: 6, fontFamily: 'var(--font-data)', fontSize: 10 }}>
                    {evt.stats.map((s: any, j: number) => (
                      <span key={j} style={{ color: 'var(--text-muted)' }}>{s.label}: <span style={{ color: s.color || 'var(--text-primary)' }}>{s.value}</span></span>
                    ))}
                  </div>
                )}
                {/* Outcome data on timeline events */}
                {evt.data?.alpha_pct != null && (
                  <span style={{
                    fontSize: 10, fontFamily: 'var(--font-data)', marginLeft: 6,
                    color: evt.data.alpha_pct >= 0 ? 'var(--positive)' : 'var(--negative)',
                  }}>
                    α {evt.data.alpha_pct >= 0 ? '+' : ''}{evt.data.alpha_pct.toFixed(1)}%
                  </span>
                )}
                {evt.data?.thesis_played_out != null && (
                  <span style={{ fontSize: 10, marginLeft: 4, color: evt.data.thesis_played_out ? 'var(--positive)' : 'var(--negative)' }}>
                    {evt.data.thesis_played_out ? '✓ thesis worked' : '✗ thesis broke'}
                  </span>
                )}
                {evt.data?.narrative && (
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, maxHeight: 40, overflow: 'hidden' }}>
                    {evt.data.narrative.slice(0, 150)}...
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------- Memo content renderer ---------- */
function renderMemoContent(memo: any): any {
  if (!memo) return null;
  if (typeof memo === 'string') return memo;
  if (Array.isArray(memo)) {
    return memo.map((section: any, i: number) => (
      <div key={i} style={{ marginBottom: 16 }}>
        {section.title && <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 'var(--text-base)', marginBottom: 6 }}>{section.title}</div>}
        <div>{typeof section === 'string' ? section : section.content || section.text || JSON.stringify(section)}</div>
      </div>
    ));
  }
  if (typeof memo === 'object') {
    // Known memo section keys
    const sectionKeys = Object.keys(memo).filter(k =>
      !['word_count', 'type', 'created_at', 'ticker', 'run_at', 'version', 'model', 'cost', 'summary', 'executive_summary'].includes(k) &&
      typeof memo[k] === 'string' && memo[k].length > 50
    );
    if (sectionKeys.length > 0) {
      return sectionKeys.map((key, i) => (
        <div key={i} style={{ marginBottom: 16 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 'var(--text-base)', marginBottom: 6, textTransform: 'capitalize' }}>
            {key.replace(/_/g, ' ')}
          </div>
          <div>{memo[key]}</div>
        </div>
      ));
    }
    // Fallback: stringify
    return JSON.stringify(memo, null, 2);
  }
  return String(memo);
}

function getMemoPreview(memo: any): string {
  if (!memo) return '';
  if (memo.summary) return memo.summary;
  if (memo.executive_summary) return memo.executive_summary;
  if (typeof memo === 'string') return memo.slice(0, 300) + (memo.length > 300 ? '...' : '');
  // Try to find the first long text field
  for (const key of Object.keys(memo)) {
    if (typeof memo[key] === 'string' && memo[key].length > 50) {
      return memo[key].slice(0, 300) + (memo[key].length > 300 ? '...' : '');
    }
  }
  return JSON.stringify(memo).slice(0, 300) + '...';
}

/* ============================================================
   RESEARCH TAB
   ============================================================ */
function ResearchTab({ detail, thesis, ic, memoRaw, library, memoOpen, setMemoOpen, ticker }: {
  detail: any; thesis: any; ic: any; memoRaw: any; library: any;
  memoOpen: boolean; setMemoOpen: (v: boolean) => void; ticker: string;
}) {
  const screener = detail?.screener || detail?.screen || {};
  const _rawThesis = thesis || {};

  // Normalize return_sources: backend sends {discount, growth, margin, dividends} object
  // but this component renders it as [{label, value, color}] array
  const COLORS = ['var(--info)', 'var(--positive)', 'var(--accent)', 'var(--warning)'];
  const _rawSources = _rawThesis.return_sources;
  const normalizedReturnSources: { label: string; value: number; color: string }[] | undefined =
    !_rawSources
      ? undefined
      : Array.isArray(_rawSources)
      ? _rawSources
      : Object.entries(_rawSources as Record<string, number>)
          .filter(([, v]) => v != null && v > 0)
          .map(([k, v], i) => ({ label: k, value: v as number, color: COLORS[i % COLORS.length] }));

  const thesisData = { ..._rawThesis, return_sources: normalizedReturnSources };
  const icData = ic || {};

  return (
    <div>
      {/* ===== SCREENER SECTION ===== */}
      <ResearchSectionHeader
        dotColor="var(--text-muted)"
        label="SCREENER"
        labelColor="var(--text-muted)"
        badge={screener.date || screener.screened_at}
        badgeBg="rgba(95,99,104,0.15)"
        badgeColor="var(--text-muted)"
        rightMeta={[
          screener.lens && `${screener.lens} lens`,
          screener.rank && `Rank #${screener.rank}`,
          screener.composite && `Composite ${screener.composite}/100`,
        ].filter(Boolean).join(' \u00B7 ') || undefined}
      />
      <div className="card" style={{ marginBottom: 12, borderLeft: '3px solid var(--text-muted)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>HOW IT WAS FOUND</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 8 }}>
              {screener.narrative || screener.how_found || 'Screener narrative not available.'}
            </div>
            {(screener.universe || screener.run_id) && (
              <div style={{ display: 'flex', gap: 8, fontSize: 'var(--text-xs)' }}>
                {screener.universe && (<><span style={{ color: 'var(--text-muted)' }}>Universe:</span><span style={{ fontFamily: 'var(--font-data)' }}>{screener.universe}</span></>)}
                {screener.run_id && (<><span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>Run:</span><span style={{ fontFamily: 'var(--font-data)' }}>{screener.run_id}</span></>)}
              </div>
            )}
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 6 }}>SCORES &amp; SNAPSHOT AT SCREEN</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', fontSize: 'var(--text-xs)' }}>
              {(screener.scores || []).map((s: any, i: number) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{s.label}</span>
                  <span style={{ fontFamily: 'var(--font-data)', color: s.color }}>{s.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ height: 1, background: 'var(--border)', margin: '4px 0 16px' }} />

      {/* ===== THESIS SECTION ===== */}
      <ResearchSectionHeader
        dotColor="var(--info)"
        label="THESIS"
        labelColor="var(--info)"
        badge={thesisData.version ? `${thesisData.version} \u00B7 ${thesisData.date || ''}` : thesisData.date}
        badgeBg="rgba(66,133,244,0.12)"
        badgeColor="var(--info)"
        rightMeta={[
          thesisData.fair_value && `FV ${fmtUsd(thesisData.fair_value)}`,
          thesisData.discount_pct && `Discount ${thesisData.discount_pct}%`,
          thesisData.expected_return && `Expected return ${thesisData.expected_return}%`,
        ].filter(Boolean).join(' \u00B7 ') || undefined}
      />

      {/* Return decomposition bar */}
      {thesisData.return_sources && (
        <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--info)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${(thesisData.return_sources?.length ?? 0) + 1}, 1fr)`, gap: 8, textAlign: 'center', fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
            {thesisData.return_sources.map((src: any, i: number) => (
              <div key={i}>
                <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{(src.label || src.name || '').toUpperCase()}</div>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: src.color || 'var(--info)' }}>{fmtPct(src.value)}</div>
              </div>
            ))}
            <div style={{ borderLeft: '1px solid var(--border)', paddingLeft: 8 }}>
              <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>TOTAL</div>
              <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--positive)' }}>{fmtPct(thesisData.expected_return)}</div>
            </div>
          </div>
          <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginTop: 8 }}>
            {thesisData.return_sources.map((src: any, i: number) => (
              <div key={i} style={{ flex: src.value, background: src.color || ['var(--info)', 'var(--positive)', 'var(--accent)'][i % 3] }} />
            ))}
          </div>
        </div>
      )}

      {/* Conviction + Valuation + Quality strip */}
      {(thesisData.conviction || thesisData.valuation || thesisData.quality) && (
        <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--info)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '6px 16px', fontSize: 'var(--text-xs)' }}>
            {thesisData.conviction && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Conviction</span>
                <span style={{ fontFamily: 'var(--font-data)', fontWeight: 600, color: thesisData.conviction === 'HIGH' ? 'var(--positive)' : thesisData.conviction === 'LOW' ? 'var(--warning)' : 'var(--text-primary)' }}>{thesisData.conviction}</span>
              </div>
            )}
            {thesisData.valuation?.method && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Val Method</span>
                <span style={{ fontFamily: 'var(--font-data)' }}>{thesisData.valuation.method}</span>
              </div>
            )}
            {Object.entries(thesisData.quality || {}).map(([k, v]: [string, any]) => v != null && v !== 0 && (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--text-muted)' }}>{k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                <span style={{ fontFamily: 'var(--font-data)' }}>{typeof v === 'number' ? (k.includes('margin') || k.includes('yield') || k.includes('growth') || k.includes('roic') || k.includes('roe') ? pct(v) : `${v.toFixed(1)}`) : v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Full thesis text (variant view + web research) */}
      {thesisData.narrative && (() => {
        const { body, references } = formatResearchProse(typeof thesisData.narrative === 'string' ? thesisData.narrative : JSON.stringify(thesisData.narrative));
        return (
          <div className="card" style={{ lineHeight: 1.8, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 12, borderLeft: '3px solid var(--info)', maxHeight: 500, overflowY: 'auto' }}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{body}</div>
            {references.length > 0 && (
              <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 8 }}>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>SOURCES</div>
                {references.map((url, i) => (
                  <div key={i} style={{ fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)', marginBottom: 2 }}>
                    [{i + 1}] <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>{urlHostname(url)}</a>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })()}

      <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />

      {/* ===== IC REVIEW SECTION ===== */}
      <ResearchSectionHeader
        dotColor="var(--positive)"
        label="IC REVIEW"
        labelColor="var(--positive)"
        verdict={icData.verdict || icData.decision}
        badge={icData.conviction ? `Conviction ${icData.conviction}/5 \u00B7 ${icData.date || ''}` : icData.date}
        badgeBg={undefined}
        badgeColor="var(--text-muted)"
        rightMeta={[
          icData.base_return && `Base ${icData.base_return}%`,
          icData.bear_return && `Bear ${icData.bear_return}%`,
          icData.scorecard_total && `Scorecard ${icData.scorecard_total}/100`,
        ].filter(Boolean).join(' \u00B7 ') || undefined}
      />

      {/* Scorecard strip */}
      {icData.scorecard && (
        <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--positive)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${icData.scorecard.length}, 1fr)`, gap: 6, textAlign: 'center' }}>
            {icData.scorecard.map((sc: any, i: number) => {
              const isOverall = (sc.label || '').toLowerCase() === 'overall';
              return (
                <div key={i} style={{ background: isOverall ? 'var(--accent-subtle)' : 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', padding: 6 }}>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: isOverall ? 'var(--accent)' : 'var(--text-muted)' }}>{(sc.label || '').toUpperCase()}</div>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', fontWeight: 600, color: isOverall ? 'var(--accent)' : (sc.color || 'var(--text-primary)') }}>{sc.value}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Full IC decision text */}
      {icData.narrative && (
        <div className="card" style={{ lineHeight: 1.8, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 10, borderLeft: '3px solid var(--positive)' }}>
          {Array.isArray(icData.narrative) ? icData.narrative.map((p: string, i: number) => (
            <p key={i} style={{ marginBottom: i < icData.narrative.length - 1 ? 10 : 0 }} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(p) }} />
          )) : (
            <div style={{ whiteSpace: 'pre-wrap' }}>{icData.narrative}</div>
          )}

          {/* Stress-tested return sources */}
          {icData.stress_tested_sources && (
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${icData.stress_tested_sources.length}, 1fr)`, gap: 8, marginTop: 10, marginBottom: 10 }}>
              {icData.stress_tested_sources.map((src: any, i: number) => (
                <div key={i} style={{ background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 'var(--text-xs)' }}>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', marginBottom: 3 }}>{(src.label || '').toUpperCase()}</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Base</span>
                    <span style={{ fontFamily: 'var(--font-data)', color: src.base_color || 'var(--info)' }}>{fmtPct(src.base)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Bear (70% haircut)</span>
                    <span style={{ fontFamily: 'var(--font-data)' }}>{fmtPct(src.bear)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Override notice */}
      {icData.overridden && (
        <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--warning)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          <span style={{ fontFamily: 'var(--font-data)', color: 'var(--warning)', fontWeight: 600 }}>MANUAL OVERRIDE</span>
          {' — '} Verdict overridden to {icData.verdict?.toUpperCase()}.
          {icData.original_verdict && <> Original AI verdict: <span style={{ fontWeight: 600, color: icData.original_verdict === 'PASS' ? 'var(--positive)' : 'var(--negative)' }}>{icData.original_verdict}</span>.</>}
          {icData.override_note && <div style={{ marginTop: 4, color: 'var(--text-secondary)' }}>Note: {icData.override_note}</div>}
        </div>
      )}

      {/* Key risk + assumptions */}
      {(icData.key_risk || icData.key_assumptions) && (
        <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--positive)', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {icData.key_risk && (
            <div style={{ marginBottom: icData.key_assumptions ? 8 : 0 }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--negative)', letterSpacing: '0.06em' }}>KEY RISK</span>
              <div style={{ marginTop: 3 }}>{typeof icData.key_risk === 'string' ? icData.key_risk.replace(/^#{1,6}\s+/gm, '').trim() : icData.key_risk}</div>
            </div>
          )}
          {icData.key_assumptions && (
            <div>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>KEY ASSUMPTIONS TO MONITOR</span>
              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                {(Array.isArray(icData.key_assumptions) ? icData.key_assumptions : [icData.key_assumptions]).map((a: string, i: number) => (
                  <li key={i} style={{ marginBottom: 2 }}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* AI review */}
      {icData.ai_review && (() => {
        const reviewText = typeof icData.ai_review === 'string' ? icData.ai_review : Array.isArray(icData.ai_review) ? icData.ai_review.join('\n\n') : '';
        const { body, references } = formatResearchProse(reviewText);
        return (
          <div style={{ background: 'var(--bg-ai)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '10px 14px', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 10 }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--accent)', letterSpacing: '0.06em', marginBottom: 6 }}>AI REVIEW</div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{body}</div>
            {references.length > 0 && (
              <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 6 }}>
                {references.map((url, i) => (
                  <div key={i} style={{ fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)', marginBottom: 1 }}>
                    [{i + 1}] <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>{urlHostname(url)}</a>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })()}

      {/* Constitution fit */}
      {icData.constitution_fit && icData.constitution_fit.length > 0 && (
        <>
          <div className="td-section-title" style={{ marginTop: 12 }}>CONSTITUTION FIT</div>
          <div className="card">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px' }}>
              {icData.constitution_fit.map((item: any, i: number) => (
                <div key={i} className="fit-row">
                  <span className="fit-icon" style={{ color: item.pass !== false ? 'var(--positive)' : 'var(--negative)' }}>
                    {item.pass !== false ? '\u2713' : '\u2717'}
                  </span>
                  <span style={{ color: 'var(--text-secondary)' }}>{item.text || item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ===== INVESTMENT MEMO SECTION ===== */}
      {memoRaw && !(Array.isArray(memoRaw.memos) && memoRaw.memos.length === 0 && !memoRaw.summary && !memoRaw.executive_summary) && (
        <>
          <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />

          <ResearchSectionHeader
            dotColor="var(--accent)"
            label="INVESTMENT MEMO"
            labelColor="var(--accent)"
            badge={memoRaw.created_at ? new Date(memoRaw.created_at).toLocaleDateString() : (memoRaw.run_at ? memoRaw.run_at.slice(0, 10) : undefined)}
            badgeBg="rgba(138,80,255,0.12)"
            badgeColor="var(--accent)"
            rightMeta={[
              memoRaw.word_count && `${memoRaw.word_count.toLocaleString()} words`,
              memoRaw.type,
            ].filter(Boolean).join(' \u00B7 ') || undefined}
          />

          <div className="card" style={{ marginBottom: 12, borderLeft: '3px solid var(--accent)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, flex: 1 }}>
                {getMemoPreview(memoRaw)}
              </div>
              <button className="btn" onClick={() => setMemoOpen(true)} style={{ fontSize: 'var(--text-xs)', marginLeft: 12, flexShrink: 0 }}>
                Read Full Memo
              </button>
            </div>
            <div style={{ display: 'flex', gap: 16, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              {memoRaw.model && <span>{memoRaw.model}</span>}
              {memoRaw.cost && <span>${memoRaw.cost.toFixed(2)}</span>}
              {memoRaw.version && <span>v{memoRaw.version}</span>}
            </div>
          </div>

          {memoOpen && (
            <ReaderPopup title={`${ticker} \u2014 Investment Memo`} onClose={() => setMemoOpen(false)}>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 'var(--text-sm)', lineHeight: 1.8, color: 'var(--text-primary)' }}>
                {renderMemoContent(memoRaw)}
              </div>
            </ReaderPopup>
          )}
        </>
      )}

      {/* ===== RESEARCH HISTORY (Library) ===== */}
      {library?.entries && library.entries.length > 0 && (
        <>
          <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />

          <div className="td-section-title">RESEARCH HISTORY</div>
          <div className="card">
            {library.entries.map((entry: any, i: number) => (
              <div key={i} style={{ padding: '6px 0', borderBottom: i < library.entries.length - 1 ? '1px solid var(--border)' : 'none', fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', minWidth: 70 }}>{entry.entry_type || entry.type}</span>
                {entry.verdict && (
                  <span className={entry.verdict === 'PASS' ? 'verdict-pass' : 'verdict-fail'}>{entry.verdict}</span>
                )}
                {entry.expected_return != null && (
                  <span style={{ fontFamily: 'var(--font-data)', color: entry.expected_return >= 20 ? 'var(--positive)' : 'var(--text-secondary)' }}>
                    {entry.expected_return}% expected
                  </span>
                )}
                {entry.score != null && (
                  <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
                    Score {entry.score}
                  </span>
                )}
                {(entry.created_at || entry.date) && (
                  <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontFamily: 'var(--font-data)' }}>
                    {new Date(entry.created_at || entry.date).toLocaleDateString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ResearchSectionHeader({ dotColor, label, labelColor, verdict, badge, badgeBg, badgeColor, rightMeta }: {
  dotColor: string; label: string; labelColor: string; verdict?: string;
  badge?: string; badgeBg?: string; badgeColor?: string; rightMeta?: string;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
        <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: labelColor, letterSpacing: '0.08em' }}>{label}</span>
        {verdict && <span className={verdict === 'PASS' ? 'verdict-pass' : 'verdict-fail'}>{verdict}</span>}
        {badge && (
          <span style={{ fontFamily: 'var(--font-data)', fontSize: 9, background: badgeBg, color: badgeColor, padding: '1px 6px', borderRadius: 3 }}>{badge}</span>
        )}
      </div>
      {rightMeta && <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>{rightMeta}</span>}
    </div>
  );
}

/* ============================================================
   HEALTH TAB
   ============================================================ */
function HealthTab({ detail, portfolio }: { detail: any; portfolio: any }) {
  const health = detail?.health || {};
  const position = portfolio?.position || detail?.position;
  const score = health.score ?? health.health_score;
  const assumptions = health.assumptions || [];
  const fundamentals = health.fundamentals || [];
  const events = health.recent_events || [];
  const breakers = health.thesis_breakers || health.what_breaks || [];
  const catalysts = health.catalysts || health.upcoming_catalysts || [];
  const healthHistory = health.history || [];
  const alert = health.active_alert;

  const scoreColor = score != null ? (score >= 70 ? 'var(--positive)' : score >= 50 ? 'var(--warning)' : 'var(--negative)') : 'var(--text-muted)';
  const intactCount = assumptions.filter((a: any) => a.status === 'intact' || a.status === 'ok' || a.score >= 70).length;
  const monitorCount = assumptions.filter((a: any) => a.status === 'monitoring' || a.status === 'warning' || (a.score != null && a.score < 70 && a.score >= 40)).length;

  return (
    <div>
      {/* Thesis Integrity Score */}
      {health?.thesis_integrity != null && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>THESIS INTEGRITY</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{
              fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)',
              color: health.thesis_integrity >= 70 ? 'var(--positive)' : health.thesis_integrity >= 40 ? 'var(--accent)' : 'var(--negative)',
            }}>
              {Math.round(health.thesis_integrity)}/100
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              {health.thesis_integrity >= 70 ? 'Thesis intact' : health.thesis_integrity >= 40 ? 'Thesis at risk' : 'Thesis deteriorating'}
            </span>
          </div>
        </div>
      )}

      {/* Goal Alignment */}
      {health?.goal_alignment?.status && (
        <div style={{ fontSize: 'var(--text-xs)', marginBottom: 8 }}>
          <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>ALIGNMENT </span>
          <span style={{
            color: health.goal_alignment.status === 'aligned' ? 'var(--positive)' : health.goal_alignment.status === 'divergent' ? 'var(--accent)' : 'var(--negative)',
          }}>
            {health.goal_alignment.status === 'aligned' ? '✓ Aligned' : health.goal_alignment.status === 'divergent' ? '⚠ Divergent' : '✗ Failed'}
          </span>
          {health.goal_alignment.reason && <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{health.goal_alignment.reason}</span>}
        </div>
      )}

      {/* Health score hero + alerts banner */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div className="card" style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="health-dot" style={{ background: scoreColor, width: 12, height: 12 }} />
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700, color: scoreColor }}>{score ?? '\u2014'}</span>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>WEIGHTED THESIS HEALTH</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              {intactCount} of {assumptions.length} assumptions intact{monitorCount > 0 ? ` \u00B7 ${monitorCount} under monitoring` : ''}
            </div>
          </div>
        </div>
        {alert && (
          <div className="card" style={{ flex: 1, borderLeft: '3px solid var(--warning)' }}>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--warning)', letterSpacing: '0.06em', marginBottom: 4 }}>ACTIVE ALERT</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {typeof alert === 'string' ? alert : alert.text}
              {alert.next_data_point && <> <strong style={{ color: 'var(--text-primary)' }}>{alert.next_data_point}</strong></>}
            </div>
          </div>
        )}
      </div>

      <div className="two-col">
        {/* LEFT COLUMN */}
        <div>
          {/* Key assumptions with expanded detail */}
          <div className="td-section-title">KEY ASSUMPTIONS</div>
          <div className="card" style={{ marginBottom: 10 }}>
            {assumptions.map((a: any, i: number) => {
              const isWarning = a.status === 'monitoring' || a.status === 'warning' || (a.score != null && a.score < 70 && a.score >= 40);
              const isOk = !isWarning && a.score >= 40;
              const statusIcon = isWarning ? '\u26A0' : (isOk ? '\u2713' : '\u2717');
              const statusColor = isWarning ? 'var(--warning)' : (isOk ? 'var(--positive)' : 'var(--negative)');
              const trendArrow = a.trend > 0 ? '\u2191' : a.trend < 0 ? '\u2193' : '\u2192';
              const trendColor = a.trend > 0 ? 'var(--positive)' : a.trend < 0 ? 'var(--negative)' : 'var(--text-muted)';

              return (
                <div key={i} style={{
                  padding: '6px 0',
                  borderBottom: i < assumptions.length - 1 ? '1px solid var(--border)' : undefined,
                  ...(isWarning ? { background: 'rgba(251,188,4,0.04)', margin: '0 -12px', paddingLeft: 12, paddingRight: 12 } : {}),
                }}>
                  <div className="assumption-row" style={{ borderBottom: 'none', paddingBottom: 2 }}>
                    <span className="assumption-status" style={{ color: statusColor }}>{statusIcon}</span>
                    <span className="assumption-name" style={{ fontWeight: 500, color: isWarning ? 'var(--warning)' : 'var(--text-primary)' }}>{a.name || a.label}</span>
                    <span className="assumption-score" style={{ color: statusColor }}>{a.score != null ? `${a.score}/100` : '\u2014'}</span>
                    <span className="assumption-trend" style={{ color: trendColor }}>{trendArrow} {a.trend != null ? (a.trend >= 0 ? `+${a.trend}` : a.trend) : ''}</span>
                  </div>
                  {a.detail && (
                    <div style={{ paddingLeft: 22, fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.5 }}>{a.detail}</div>
                  )}
                  {isWarning && a.if_breaks && (
                    <div style={{ paddingLeft: 22, marginTop: 4, fontSize: 10, color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', padding: '4px 8px', borderRadius: 3 }}>
                      <strong>If this breaks:</strong> {a.if_breaks}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Fundamental tracking table */}
          {fundamentals.length > 0 && (
            <>
              <div className="td-section-title" style={{ marginTop: 12 }}>FUNDAMENTAL TRACKING</div>
              <div className="card">
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 9, color: 'var(--text-muted)', marginBottom: 6 }}>QUARTERLY ACTUALS VS THESIS EXPECTATIONS</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '3px 4px' }}>Metric</th>
                      <th style={{ textAlign: 'right', padding: '3px 4px' }}>Thesis</th>
                      {fundamentals[0]?.quarters?.map((q: any, j: number) => (
                        <th key={j} style={{ textAlign: 'right', padding: '3px 4px' }}>{q.label}</th>
                      ))}
                      <th style={{ textAlign: 'center', padding: '3px 4px' }}>Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fundamentals.map((f: any, i: number) => (
                      <tr key={i}>
                        <td style={{ padding: 4, color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)' }}>{f.metric}</td>
                        <td style={{ padding: 4, textAlign: 'right', fontFamily: 'var(--font-data)', borderBottom: '1px solid var(--border)' }}>{f.thesis_target}</td>
                        {f.quarters?.map((q: any, j: number) => (
                          <td key={j} style={{ padding: 4, textAlign: 'right', fontFamily: 'var(--font-data)', color: q.color, borderBottom: '1px solid var(--border)' }}>{q.value}</td>
                        ))}
                        <td style={{ padding: 4, textAlign: 'center', fontFamily: 'var(--font-data)', color: f.trend_color, borderBottom: '1px solid var(--border)' }}>{f.trend_icon || '\u2192'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Recent events */}
          {events.length > 0 && (
            <>
              <div className="td-section-title" style={{ marginTop: 12 }}>RECENT EVENTS</div>
              <div className="card">
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                  {events.map((evt: any, i: number) => {
                    const isPositive = evt.direction === 'up' || evt.impact === 'positive';
                    const icon = isPositive ? '\u25B2' : '\u25BC';
                    const iconColor = isPositive ? 'var(--positive)' : (evt.direction === 'neutral' ? 'var(--text-muted)' : 'var(--warning)');

                    return (
                      <div key={i} style={{ padding: '5px 0', borderBottom: i < events.length - 1 ? '1px solid var(--border)' : undefined, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <span style={{ color: iconColor, flexShrink: 0 }}>{icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={!isPositive && evt.direction !== 'neutral' ? { color: 'var(--warning)' } : undefined}>{evt.text || evt.description}</span>
                            <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>{evt.date}</span>
                          </div>
                          {evt.impact_text && (
                            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Impact: {evt.impact_text}</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div>
          {/* Health over time */}
          <div className="td-section-title">HEALTH OVER TIME</div>
          <div className="card" style={{ marginBottom: 10 }}>
            <div className="health-chart-placeholder">
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>
                HEALTH SCORE TREND<br />
                <span style={{ fontSize: 9 }}>{healthHistory.map((h: any) => h.score).join(' \u2192 ') || 'No history'}</span>
              </div>
            </div>
            {healthHistory.length > 0 && (
              <div style={{ display: 'flex', gap: 8, marginTop: 8, fontSize: 10 }}>
                {healthHistory.map((h: any, i: number) => {
                  const isNow = i === healthHistory.length - 1;
                  return (
                    <div key={i} style={{ flex: 1, background: isNow ? 'var(--accent-subtle)' : 'var(--bg-tertiary)', borderRadius: 3, padding: '4px 6px', textAlign: 'center' }}>
                      <div style={{ fontFamily: 'var(--font-data)', color: isNow ? 'var(--accent)' : 'var(--text-muted)' }}>{h.label}</div>
                      <div style={{ fontFamily: 'var(--font-data)', fontWeight: 600, color: isNow ? 'var(--accent)' : undefined }}>{h.score}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* What breaks the thesis */}
          {breakers.length > 0 && (
            <>
              <div className="td-section-title" style={{ marginTop: 12 }}>WHAT BREAKS THE THESIS</div>
              <div className="card" style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {breakers.map((b: any, i: number) => {
                    const isFatal = b.severity === 'fatal' || b.severity === 'critical';
                    const icon = isFatal ? '\u2717' : '\u26A0';
                    const iconColor = isFatal ? 'var(--negative)' : 'var(--warning)';

                    return (
                      <div key={i} style={{ padding: '5px 0', borderBottom: i < breakers.length - 1 ? '1px solid var(--border)' : undefined }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                          <span style={{ color: iconColor }}>{icon}</span>
                          <strong style={{ color: 'var(--text-primary)' }}>{b.condition || b.name}</strong>
                        </div>
                        <div style={{ paddingLeft: 18, fontSize: 10, color: 'var(--text-muted)' }}>{b.impact || b.description}{b.action ? ` Action: ${b.action}` : ''}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {/* Upcoming catalysts */}
          {catalysts.length > 0 && (
            <>
              <div className="td-section-title" style={{ marginTop: 12 }}>UPCOMING CATALYSTS</div>
              <div className="card" style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 'var(--text-xs)' }}>
                  {catalysts.map((c: any, i: number) => (
                    <div key={i} style={{ padding: '6px 0', borderBottom: i < catalysts.length - 1 ? '1px solid var(--border)' : undefined, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <span style={{ fontFamily: 'var(--font-data)', color: i === 0 ? 'var(--accent)' : 'var(--text-muted)', minWidth: 55 }}>{c.days_away != null ? `${c.days_away} days` : c.timeframe || ''}</span>
                      <div>
                        <span style={{ color: i === 0 ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: i === 0 ? 500 : undefined }}>{c.name || c.event}</span>
                        {c.watch_for && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Watch: {c.watch_for}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Position context */}
          {position && (
            <>
              <div className="td-section-title" style={{ marginTop: 12 }}>POSITION CONTEXT</div>
              <div className="card">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', fontSize: 'var(--text-xs)' }}>
                  <MetricRow label="Days held" value={fmt(position.days_held)} />
                  <MetricRow label="P&L" value={position.pnl != null ? `${position.pnl >= 0 ? '+' : ''}${fmtUsd(position.pnl)}${position.pnl_pct != null ? ` (${fmtPct(position.pnl_pct)})` : ''}` : '\u2014'} color={colorFor(position.pnl)} />
                  <MetricRow label="Weight" value={fmt(position.weight, '%')} />
                  <MetricRow label="Type" value={fmt(position.type ?? position.position_type)} />
                  <MetricRow label="Allocator status" value={fmt(position.allocator_status)} color={position.allocator_status === 'HOLD' ? 'var(--positive)' : undefined} />
                  <MetricRow label="Discount to FV" value={fmt(position.discount_to_fv)} color={position.discount_to_fv ? 'var(--positive)' : undefined} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   EVIDENCE TAB — Data lineage, quality, freshness
   ============================================================ */
function EvidenceTab({ ticker }: { ticker: string }) {
  const { data: review } = useQuery({
    queryKey: ['review-data', ticker],
    queryFn: () => api.getReviewData(ticker),
    staleTime: 60000,
  });
  const { data: evidenceData } = useQuery({
    queryKey: ['evidence', ticker],
    queryFn: () => api.getEvidence(ticker),
    staleTime: 60000,
  });

  const quality = review?.data_quality || {};
  const freshness = review?.fact_sheet?.data_freshness || {};
  const warnings = review?.fact_sheet?.data_warnings || [];
  const artifacts = evidenceData?.artifacts || [];

  return (
    <div>
      {/* Data Quality Score */}
      <div className="card" style={{ marginBottom: 8 }}>
        <div className="card-title">Data Quality</div>
        {quality.quality_score != null ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              fontSize: 'var(--text-xl)', fontWeight: 700, fontFamily: 'var(--font-data)',
              color: quality.quality_score >= 70 ? 'var(--positive)' : quality.quality_score >= 40 ? 'var(--warning)' : 'var(--negative)',
            }}>
              {quality.quality_score}/100
            </div>
            <div style={{ flex: 1 }}>
              {quality.missing_fields?.length > 0 && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)', marginBottom: 2 }}>
                  Missing: {quality.missing_fields.join(', ')}
                </div>
              )}
              {quality.anomalies?.length > 0 && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--negative)', marginBottom: 2 }}>
                  Anomalies: {quality.anomalies.length}
                </div>
              )}
              {quality.issues?.map((issue: string, i: number) => (
                <div key={i} style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{issue}</div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
            Run thesis to generate data quality report
          </div>
        )}
      </div>

      {/* Data Freshness */}
      <div className="card" style={{ marginBottom: 8 }}>
        <div className="card-title">Data Freshness</div>
        {freshness.age_days != null ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-sm)' }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: freshness.fresh ? 'var(--positive)' : 'var(--warning)',
            }} />
            <span>
              Most recent filing: <strong>{freshness.age_days} days ago</strong>
              {!freshness.fresh && <span style={{ color: 'var(--warning)', marginLeft: 6 }}>(stale)</span>}
            </span>
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>No freshness data available</div>
        )}
        {warnings.map((w: string, i: number) => (
          <div key={i} style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)', marginTop: 4, padding: '4px 8px', background: 'rgba(251,188,4,0.08)', borderRadius: 4 }}>
            {w}
          </div>
        ))}
      </div>

      {/* Evidence Artifacts */}
      <div className="card">
        <div className="card-title">Evidence Artifacts ({artifacts.length})</div>
        {artifacts.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
            No evidence artifacts captured yet. Run thesis to create data snapshots.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Type</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Source</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Hash</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Captured</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '4px 0' }}>
                    <span style={{
                      fontSize: 9, padding: '1px 6px', borderRadius: 3,
                      background: a.artifact_type === 'sec_filing' ? 'rgba(52,168,83,0.15)' : 'rgba(66,133,244,0.15)',
                      color: a.artifact_type === 'sec_filing' ? 'var(--positive)' : 'var(--accent)',
                    }}>
                      {a.artifact_type}
                    </span>
                  </td>
                  <td style={{ padding: '4px 0' }}>{a.source}</td>
                  <td style={{ padding: '4px 0', fontFamily: 'monospace', fontSize: 10, color: 'var(--text-muted)' }}>
                    {a.data_hash?.slice(0, 8)}...
                  </td>
                  <td style={{ padding: '4px 0', color: 'var(--text-muted)' }}>
                    {a.captured_at ? new Date(a.captured_at).toLocaleString() : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ============================================================
   MAIN PAGE COMPONENT
   ============================================================ */
export function TickerDetail() {
  const { ticker } = useParams();
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [memoOpen, setMemoOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['ticker-detail', ticker],
    queryFn: async () => {
      if (!ticker) return null;
      const [detail, thesisRaw, icRaw, memoRaw, timeline, events, library, portfolio] = await Promise.all([
        api.tickerDetail(ticker),
        api.getThesis(ticker).catch(() => null),
        api.getICReview(ticker).catch(() => null),
        api.getMemo(ticker).catch(() => null),
        api.tickerTimeline(ticker).catch(() => null),
        api.getTickerEvents(ticker).catch(() => null),
        api.getLibraryTicker(ticker).catch(() => null),
        api.getPortfolio().catch(() => null),
      ]);
      return { detail, thesisRaw, icRaw, memoRaw, timeline, events, library, portfolio };
    },
    enabled: !!ticker,
  });

  const detail = data?.detail || {};
  const thesisParsed = parseOutput(data?.thesisRaw);
  const icParsed = parseOutput(data?.icRaw);
  const timelineEvents = data?.timeline?.events || data?.timeline?.runs || data?.events?.events || [];
  const portfolio = data?.portfolio;

  // Build research-tab data structures from parsed outputs
  // Normalize narrative: backend stores as thesis_narrative (new) or variant_view (legacy)
  // Filter out raw LLM chatter from variant_view (starts with "Thanks —" etc.)
  const _rawNarrative = thesisParsed.thesis_narrative || thesisParsed.variant_view || '';
  const _cleanNarrative = _rawNarrative && !_rawNarrative.startsWith('Thanks') && !_rawNarrative.startsWith('I') ? _rawNarrative : '';

  // Build thesis web research narrative from why_cheap + bull_case
  const _webResearch = thesisParsed.web_research || (detail.thesis || {}).web_research || {};
  const _whyCheap = _webResearch.why_cheap || '';
  const _bullCase = _webResearch.bull_case || '';
  // Combine all thesis prose: variant view + web research
  const _thesisNarrative = [_cleanNarrative, _whyCheap, _bullCase].filter(Boolean).join('\n\n') || thesisParsed.narrative || '';

  const _detailThesis = detail.thesis || {};
  const thesisForResearch = {
    ...thesisParsed,
    ..._detailThesis,
    // Override with computed/correct values after spread
    fair_value: thesisParsed.fair_value ?? data?.thesisRaw?.fair_value ?? _detailThesis.fair_value,
    discount_pct: thesisParsed.discount_pct ?? data?.thesisRaw?.discount_pct ?? _detailThesis.discount_pct,
    expected_return: thesisParsed.expected_return ?? data?.thesisRaw?.expected_return ?? _detailThesis.expected_return,
    date: thesisParsed.date ?? data?.thesisRaw?.run_at?.slice(0, 10),
    narrative: _thesisNarrative,
    conviction: thesisParsed.conviction || _detailThesis.conviction,
    quality: thesisParsed.quality || _detailThesis.quality,
    valuation: thesisParsed.valuation || _detailThesis.valuation,
    constitution_fit: thesisParsed.constitution_fit || _detailThesis.constitution_fit,
  };

  // Parse memoRaw: API returns {memos: [...]} — extract the latest investment + research memos
  const _memoList: any[] = data?.memoRaw?.memos ?? [];
  const _latestInvMemo = _memoList.find((m: any) => m.run_type === 'investment');
  const _latestResMemo = _memoList.find((m: any) => m.run_type === 'research');
  const _bestMemo = _latestInvMemo || _latestResMemo || _memoList[0];
  const memoParsed = (() => {
    if (!_bestMemo) return null;
    const fo = _bestMemo.full_output;
    let parsed: any = null;
    if (typeof fo === 'string') { try { parsed = JSON.parse(fo); } catch { parsed = null; } }
    else if (typeof fo === 'object') { parsed = fo; }
    return {
      ...parsed,
      run_at: _bestMemo.run_at,
      run_type: _bestMemo.run_type,
      summary: _bestMemo.summary || parsed?.content?.slice(0, 300),
    };
  })();

  // Merge IC data from both the parsed agent run AND the enriched ticker detail
  const _detailIC = detail.ic_review || detail.ic || {};
  const _icBase = { ...icParsed, ..._detailIC };
  // Build stress-tested return sources for rendering
  const _stressSources = (() => {
    const baseSrc = _icBase.return_sources_base;
    const bearSrc = _icBase.return_sources_bear;
    if (!baseSrc || !bearSrc) return undefined;
    const COLORS = ['var(--info)', 'var(--positive)', 'var(--accent)', 'var(--warning)'];
    return Object.entries(baseSrc as Record<string, number>)
      .filter(([, v]) => v != null && (v as number) > 0)
      .map(([k, v], i) => ({
        label: k,
        base: v as number,
        bear: (bearSrc as Record<string, number>)[k] ?? 0,
        base_color: COLORS[i % COLORS.length],
      }));
  })();

  const icForResearch = {
    ..._icBase,
    verdict: _icBase.verdict ?? data?.icRaw?.verdict,
    conviction: _icBase.conviction ?? data?.icRaw?.scores?.conviction,
    base_return: _icBase.base_return ?? data?.icRaw?.scores?.base_return,
    bear_return: _icBase.bear_return ?? data?.icRaw?.scores?.bear_return,
    scorecard_total: _icBase.scorecard_total ?? data?.icRaw?.scores?.scorecard_total,
    date: _icBase.date ?? data?.icRaw?.run_at?.slice(0, 10) ?? _detailIC.run_at?.slice(0, 10),
    // Build narrative from ai_review for the rendering block
    narrative: _icBase.ai_review || _icBase.narrative || icParsed.narrative,
    // Build scorecard for the strip rendering
    scorecard: _icBase.scorecard || (() => {
      // Build scorecard from hurdle data if no explicit scorecard
      const items: any[] = [];
      if (_icBase.base_return != null) items.push({ label: 'Base Return', value: `${_icBase.base_return}%`, color: (_icBase.base_return >= (_icBase.hurdle_base || 20)) ? 'var(--positive)' : 'var(--negative)' });
      if (_icBase.bear_return != null) items.push({ label: 'Bear Return', value: `${_icBase.bear_return}%`, color: (_icBase.bear_return >= (_icBase.hurdle_bear || 15)) ? 'var(--positive)' : 'var(--negative)' });
      if (_icBase.conviction != null) items.push({ label: 'Conviction', value: `${_icBase.conviction}/5` });
      if (_icBase.discount_pct != null) items.push({ label: 'Discount', value: `${_icBase.discount_pct}%` });
      if (_icBase.discount_floor != null) items.push({ label: 'Floor', value: `${_icBase.discount_floor}%`, color: _icBase.discount_floor_met ? 'var(--positive)' : 'var(--negative)' });
      return items.length > 0 ? items : undefined;
    })(),
    stress_tested_sources: _stressSources,
    overridden: _icBase.overridden,
    override_note: _icBase.override_note,
    original_verdict: _icBase.original_verdict,
    key_risk: _icBase.key_risk,
    key_assumptions: _icBase.key_assumptions,
  };

  // Header-level data
  const _m = detail.metrics || {};
  const companyName = detail.company_name || thesisParsed.company_name || _m.company_name || ticker;
  const price = detail.price ?? detail.current_price ?? _m.price;
  const priceChange = detail.price_change;
  const priceChangePct = detail.price_change_pct;
  const fairValue = thesisForResearch.fair_value ?? detail.fair_value;
  const discountPct = thesisForResearch.discount_pct ?? detail.discount_pct;
  const exchange = detail.exchange;
  const sector = detail.sector || _m.sector;
  const industry = detail.industry || _m.industry;
  const country = detail.country;

  // KPI values — backend sends `metrics`, kpis is a frontend alias
  const kpis = detail.kpis || {
    market_cap: _m.market_cap,
    pe_fwd: _m.pe,
    rev_growth: _m.revenue_growth,
    op_margin: _m.operating_margin != null ? +(_m.operating_margin * 100).toFixed(1) : undefined,
    fcf_yield: _m.fcf_yield,
    thesis_health: detail.health?.score,
  };

  return (
    <div className="stack">
      {/* Back link */}
      <div>
        <Link to="/research" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', textDecoration: 'none' }}>
          {'\u2190'} Back to Research
        </Link>
      </div>

      {/* Ticker header */}
      <div className="ticker-header">
        <div>
          <div className="ticker-title">{ticker}</div>
          <div className="ticker-company">{companyName}</div>
          <div className="ticker-meta-line">
            {[exchange, sector, industry, country].filter(Boolean).join(' \u00B7 ')}
          </div>
        </div>
        <div className="price-block">
          {price != null && <div className="price-current">{fmtUsd(price, 2)}</div>}
          {priceChange != null && (
            <div className="price-change" style={{ color: colorFor(priceChange) }}>
              {priceChange >= 0 ? '+' : ''}{fmtUsd(priceChange, 2)} ({fmtPct(priceChangePct)}) today
            </div>
          )}
          {fairValue != null && (
            <div className="price-fv">
              Fair value {fmtUsd(fairValue)} {discountPct != null && (<> {'\u00B7'} Discount <span style={{ color: 'var(--positive)' }}>{discountPct}%</span></>)}
            </div>
          )}
        </div>
      </div>

      {/* KPI strip */}
      <div className="kpi-strip">
        <KpiMini label="MARKET CAP" value={fmtBigUsd(kpis.market_cap ?? detail.market_cap)} />
        <KpiMini label="PE (FWD)" value={kpis.pe_fwd != null ? `${Number(kpis.pe_fwd).toFixed(1)}x` : '\u2014'} />
        <KpiMini label="REV GROWTH" value={fmtPct(kpis.rev_growth ?? kpis.revenue_growth)} color={colorFor(kpis.rev_growth ?? kpis.revenue_growth)} />
        <KpiMini label="OP MARGIN" value={kpis.op_margin != null ? `${kpis.op_margin}%` : '\u2014'} />
        <KpiMini label="FCF YIELD" value={kpis.fcf_yield != null ? `${kpis.fcf_yield}%` : '\u2014'} />
        <KpiMini label="THESIS HEALTH" value={fmt(kpis.thesis_health ?? detail.health?.score)} color={kpis.thesis_health != null ? (kpis.thesis_health >= 70 ? 'var(--positive)' : kpis.thesis_health >= 50 ? 'var(--warning)' : 'var(--negative)') : undefined} />
      </div>

      {/* Tabs */}
      <div className="detail-tabs">
        {(['overview', 'research', 'health', 'evidence'] as Tab[]).map((tab) => (
          <button
            key={tab}
            className={`detail-tab${activeTab === tab ? ' active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {isLoading && <div className="card"><div className="muted">Loading ticker data...</div></div>}

      {!isLoading && activeTab === 'overview' && (
        <OverviewTab detail={detail} timeline={timelineEvents} portfolio={portfolio} />
      )}

      {!isLoading && activeTab === 'research' && (
        <ResearchTab detail={detail} thesis={thesisForResearch} ic={icForResearch} memoRaw={memoParsed} library={data?.library} memoOpen={memoOpen} setMemoOpen={setMemoOpen} ticker={ticker || ''} />
      )}

      {!isLoading && activeTab === 'health' && (
        <HealthTab detail={detail} portfolio={portfolio} />
      )}

      {!isLoading && activeTab === 'evidence' && (
        <EvidenceTab ticker={ticker || ''} />
      )}

      {/* Link to Library */}
      <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          Viewing latest research only. For all versions, historical artifacts, and prediction tracking:
        </div>
        <Link to="/library" className="btn btn-ghost" style={{ fontSize: 10, padding: '4px 10px', textDecoration: 'none' }}>
          Open in Library {'\u2192'}
        </Link>
      </div>
    </div>
  );
}
