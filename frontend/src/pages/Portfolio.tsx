/**
 * Portfolio — ledger-backed holdings. Entries carry explicit intent
 * ("Record purchase" / "Record sale" — never inferred), corrections are data
 * fixes (not trades), and price refresh never touches thesis health.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addLot,
  correctLot,
  getLedger,
  getPortfolio,
  recordSale,
  refreshPortfolio,
} from '../api/client';
import type { HoldingRow } from '../api/client';
import { exportUrls, getPortfolioAnalytics } from '../api/client';
import { TickerLink } from '../components/workflow/StageTable';
import { ask } from '../components/AskAnywhere';
import { useToast } from '../components/Toast';
import { fmtDate, fmtPct, fmtPnl, fmtPrice, fmtShares, fmtUsdCompact, localToday, pct } from '../utils/formatFinancials';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ────────────────────────── Analytics (phase 3) ────────────────────────── */

function fmtSignedPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
}

function AnalyticsSection() {
  const [range, setRange] = useState('1y');
  const { data, isPending } = useQuery({
    queryKey: ['portfolio-analytics', range],
    queryFn: () => getPortfolioAnalytics(range),
    retry: 1,
  });
  if (isPending) return <div className="empty-note">Computing analytics…</div>;
  if (!data) return null;
  const perf = data.performance;
  const merged = perf.portfolio_series.map((p) => ({
    date: p.date,
    portfolio: p.indexed,
    benchmark: perf.benchmark_series.find((b) => b.date === p.date)?.indexed,
  }));
  const exp = data.exposure;
  const risk = data.risk;

  // Plain-language read, composed from the same numbers shown below —
  // every sentence is checkable against a KPI on this page.
  const readBits: string[] = [];
  if (perf.portfolio_return != null) {
    let s = `${perf.portfolio_return >= 0 ? 'Up' : 'Down'} ${Math.abs(perf.portfolio_return * 100).toFixed(1)}% over the past ${range.toUpperCase()}`;
    if (perf.benchmark_available && perf.excess_return != null) {
      s += `, ${Math.abs(perf.excess_return * 100).toFixed(1)}pp ${perf.excess_return >= 0 ? 'ahead of' : 'behind'} the ${perf.benchmark_label}`;
    }
    readBits.push(s + '.');
  }
  const flaggedSectors = exp.sectors.filter((s) => s.over_threshold);
  if (exp.top_position_weight != null && (exp.flags?.length || flaggedSectors.length)) {
    readBits.push(
      `Concentration is the active risk: your largest position is ${(exp.top_position_weight * 100).toFixed(1)}% of the book${
        flaggedSectors.length ? ` and ${flaggedSectors.map((s) => s.sector).join(', ')} ${flaggedSectors.length > 1 ? 'are' : 'is'} over the sector threshold` : ''
      }.`,
    );
  }
  const sortedPnl = [...data.contribution].sort((a, b) => b.total_pnl - a.total_pnl);
  if (sortedPnl.length >= 2 && sortedPnl[0].total_pnl > 0) {
    const top = sortedPnl[0];
    const bottom = sortedPnl[sortedPnl.length - 1];
    let s = `${top.ticker} has carried the book (${top.total_pnl >= 0 ? '+' : ''}$${Math.round(top.total_pnl).toLocaleString()})`;
    if (bottom.total_pnl < 0) s += `; ${bottom.ticker} is the drag ($${Math.round(bottom.total_pnl).toLocaleString()})`;
    readBits.push(s + '.');
  }
  if (data.decisions.events_measured > 0 && data.decisions.promoted_avg_return != null && data.decisions.dismissed_avg_return != null) {
    readBits.push(
      `Your promote calls have averaged ${fmtSignedPct(data.decisions.promoted_avg_return)} forward vs ${fmtSignedPct(data.decisions.dismissed_avg_return)} for dismissals (${data.decisions.events_measured} measured).`,
    );
  }

  return (
    <div className="dash-section" style={{ marginBottom: 16 }}>
      {readBits.length > 0 && (
        <div
          className="card askable"
          style={{ marginBottom: 12, borderLeft: '3px solid var(--teal)', cursor: 'pointer' }}
          title="Click to ask about this read"
          onClick={(e) =>
            ask(e, {
              title: 'Portfolio read',
              questions: [
                'What is driving my performance vs the benchmark?',
                'Which holdings drive my concentration risk?',
                'How have my promote and dismiss decisions worked out?',
              ],
            })
          }
        >
          <div className="card-title">
            <span style={{ color: 'var(--teal)' }}>✦</span> The read
          </div>
          <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.65, color: 'var(--text-primary)' }}>
            {readBits.join(' ')}
          </div>
          <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Composed from the numbers below — click to question any of it.
          </div>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>Analytics</div>
        <div className="seg-control">
          {['1m', '6m', '1y', '5y'].map((k) => (
            <button key={k} className={`seg-option${range === k ? ' active' : ''}`} onClick={() => setRange(k)}>
              {k.toUpperCase()}
            </button>
          ))}
        </div>
        <a className="btn btn-ghost" style={{ marginLeft: 'auto' }} href={exportUrls.portfolio}>
          CSV
        </a>
      </div>
      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        <div className="kpi-card">
          <div className="kpi-label">Return ({range.toUpperCase()}, TWR)</div>
          <div className="kpi-value num" style={{ textAlign: 'left', color: (perf.portfolio_return ?? 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
            {fmtSignedPct(perf.portfolio_return)}
          </div>
          <div className="kpi-detail">{perf.benchmark_label} {fmtSignedPct(perf.benchmark_return)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">vs {perf.benchmark_label}</div>
          <div className="kpi-value num" style={{ textAlign: 'left', color: (perf.excess_return ?? 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
            {perf.excess_return == null ? '—' : `${perf.excess_return >= 0 ? '+' : ''}${(perf.excess_return * 100).toFixed(1)}pp`}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Max drawdown</div>
          <div className="kpi-value num" style={{ textAlign: 'left' }}>{fmtSignedPct(risk.max_drawdown)}</div>
          {risk.volatility != null && (
            <div className="kpi-detail">volatility {(risk.volatility * 100).toFixed(0)}% ann.</div>
          )}
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Beta vs {perf.benchmark_label}</div>
          <div className="kpi-value num" style={{ textAlign: 'left' }}>
            {risk.beta != null ? risk.beta.toFixed(2) : '—'}
          </div>
          {risk.correlation != null && (
            <div className="kpi-detail">correlation {risk.correlation.toFixed(2)}</div>
          )}
        </div>
      </div>
      {merged.length > 1 && (
        <div className="card" style={{ padding: '12px 14px', marginBottom: 12 }}>
          <div className="card-title">Performance vs {perf.benchmark_label} (indexed to 100)</div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={merged} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" axisLine={false} tickLine={false} minTickGap={64}
                     tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
              <YAxis domain={['auto', 'auto']} width={44} orientation="right" axisLine={false} tickLine={false}
                     tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
              <ChartTooltip
                contentStyle={{
                  background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-data)', fontSize: 11,
                }}
              />
              <Line type="monotone" dataKey="portfolio" name="Portfolio" stroke="var(--accent)"
                    strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="benchmark" name={perf.benchmark_label} stroke="var(--text-muted)"
                    strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          {perf.note && <div className="empty-note">{perf.note}</div>}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="card-title">Contribution (pp of capital deployed)</div>
          {data.contribution.length === 0 ? (
            <div className="empty-note">No positions yet.</div>
          ) : (
            data.contribution.slice(0, 8).map((c) => (
              <div key={c.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 'var(--text-sm)' }}>
                <span style={{ fontFamily: 'var(--font-data)' }}>
                  {c.ticker}
                  {c.exited && (
                    <span className="health-chip" title="Position fully sold — shown for realized P&L attribution, not a current holding." style={{ marginLeft: 6 }}>
                      closed
                    </span>
                  )}
                </span>
                <span style={{ fontFamily: 'var(--font-data)', color: c.total_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                  {c.contribution_pp == null ? fmtPnl(c.total_pnl) : `${c.contribution_pp >= 0 ? '+' : ''}${c.contribution_pp.toFixed(1)}pp`}
                </span>
              </div>
            ))
          )}
        </div>
        <div
          className="card askable"
          style={{ padding: '12px 14px' }}
          title="Click to ask about exposure"
          onClick={(e) =>
            ask(e, {
              title: 'Portfolio · sector exposure',
              questions: [
                'What would trimming my largest position to the policy line look like?',
                'Why is my concentration flag set where it is?',
                'Which holdings drive my sector concentration?',
              ],
            })
          }
        >
          <div className="card-title">Sector exposure</div>
          {exp.sectors.map((s) => (
            <div key={s.sector} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                <span>{s.sector}</span>
                <span style={{ fontFamily: 'var(--font-data)' }}>{s.weight == null ? '—' : `${(s.weight * 100).toFixed(0)}%`}</span>
              </div>
              <div style={{ height: 5, background: 'var(--bg-elevated)', borderRadius: 3 }}>
                <div style={{ width: `${(s.weight ?? 0) * 100}%`, height: 5, borderRadius: 3,
                              background: s.over_threshold ? 'var(--warning)' : 'var(--accent-muted)' }} />
              </div>
            </div>
          ))}
          {(exp.flags ?? []).map((f, i) => (
            <div key={i} style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>
              ⚠ {f}
            </div>
          ))}
          {exp.top_position_weight != null && (
            <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              top position {(exp.top_position_weight * 100).toFixed(0)}%{exp.top3_weight != null ? ` · top 3 ${(exp.top3_weight * 100).toFixed(0)}%` : ''}
            </div>
          )}
        </div>
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="card-title">Factor tilts (percentile vs universe)</div>
          {data.factor_tilts.every((f) => f.percentile == null) ? (
            <div className="empty-note">Needs metric coverage across the universe.</div>
          ) : (
            data.factor_tilts.map((f) => (
              <div key={f.factor} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                  <span>{f.label}</span>
                  <span style={{ fontFamily: 'var(--font-data)' }}>
                    {f.percentile == null ? '—' : `p${f.percentile.toFixed(0)}`}
                  </span>
                </div>
                <div style={{ height: 5, background: 'var(--bg-elevated)', borderRadius: 3, position: 'relative' }}>
                  <div style={{ position: 'absolute', left: '50%', top: -1, width: 1, height: 7, background: 'var(--border-hover)' }} />
                  <div style={{ width: `${f.percentile ?? 0}%`, height: 5, background: 'var(--accent-muted)', borderRadius: 3 }} />
                </div>
              </div>
            ))
          )}
          <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
            p50 = universe-typical · weighted by position size
          </div>
        </div>
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="card-title">Decision attribution</div>
          {data.decisions.events_measured === 0 ? (
            <div className="empty-note">
              Fills as promote/dismiss choices age past {data.decisions.min_age_days} days.
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 16, marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>Promoted · fwd return</div>
                  <div className="num" style={{ fontSize: 'var(--text-lg)', color: (data.decisions.promoted_avg_return ?? 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                    {fmtSignedPct(data.decisions.promoted_avg_return)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>Dismissed · fwd return</div>
                  <div className="num" style={{ fontSize: 'var(--text-lg)' }}>
                    {fmtSignedPct(data.decisions.dismissed_avg_return)}
                  </div>
                </div>
              </div>
              {data.decisions.recent.slice(0, 5).map((d, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', padding: '2px 0', color: 'var(--text-secondary)' }}>
                  <span style={{ fontFamily: 'var(--font-data)' }}>{d.ticker} · {d.action}</span>
                  <span style={{ fontFamily: 'var(--font-data)', color: d.forward_return >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                    {fmtSignedPct(d.forward_return)} / {d.days}d
                  </span>
                </div>
              ))}
            </>
          )}
          <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
            {data.decisions.note}
          </div>
        </div>
      </div>
    </div>
  );
}

const COLS = 11;

const POSITION_TYPES = ['core', 'tactical', 'starter', 'hedge', 'legacy'];

async function setPositionType(ticker: string, positionType: string | null): Promise<void> {
  const res = await fetch('/api/portfolio/position-type', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, position_type: positionType }),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

/* ── small render helpers ── */

function weightLabel(w: number | null | undefined): string {
  if (w == null || Number.isNaN(w)) return '—';
  return Math.abs(w) <= 1 ? pct(w) : fmtPct(w, 1).replace('+', '');
}

function HealthChip({ label }: { label?: string | null }) {
  if (!label) return <span className="muted">—</span>;
  const cls =
    label === 'Intact' ? 'health-chip intact' : label === 'Watching' ? 'health-chip watching' : label === 'Broken' ? 'health-chip broken' : 'health-chip';
  return <span className={cls}>{label}</span>;
}

function CoverageChip({ state }: { state?: string | null }) {
  const title = 'FundOps keeps memo-backed thesis coverage for holdings.';
  if (!state || state === 'none') return <span className="health-chip" title={title}>no coverage</span>;
  if (state === 'covered') return <span className="health-chip intact" title={title}>covered</span>;
  if (state === 'stale') return <span className="health-chip watching" title={`${title} Coverage memo is older than 90 days.`}>stale</span>;
  if (state === 'failed') {
    return (
      <span className="opfail-tag" title={`${title} The coverage run hit an operational error — it will retry.`}>
        coverage failed
      </span>
    );
  }
  if (state === 'running') {
    return (
      <span className="pulse-text" style={{ fontSize: 'var(--text-xs)' }} title={title}>
        <span className="pulse-dot" />
        running
      </span>
    );
  }
  return <span className="health-chip" title={title}>{state}</span>;
}

/* ── lots / sales expansion ── */

function asNum(v: unknown): number | null {
  return typeof v === 'number' && !Number.isNaN(v) ? v : null;
}
function asStr(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function HoldingDetail({
  ticker,
  onFixLot,
}: {
  ticker: string;
  onFixLot: (lot: { id: string; shares: number | null; cost_basis: number | null; purchase_date: string | null }) => void;
}) {
  const { data, isPending } = useQuery({
    queryKey: ['ledger', ticker],
    queryFn: () => getLedger(ticker),
  });

  if (isPending) return <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>Loading ledger…</div>;

  const lots = (data?.lots ?? []).map((r) => ({
    id: asStr(r.id) ?? String(r.id ?? r.lot_id ?? ''),
    shares: asNum(r.shares),
    cost_basis: asNum(r.cost_basis),
    purchase_date: asStr(r.purchase_date) ?? asStr(r.date),
    corrected: r.corrected_by != null,
  }));
  const sales = (data?.sales ?? []).map((r, i) => ({
    id: asStr(r.id) ?? String(r.id ?? i),
    shares: asNum(r.shares),
    price: asNum(r.price),
    sale_date: asStr(r.sale_date) ?? asStr(r.date),
    realized_pnl: asNum(r.realized_pnl),
  }));

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 8 }}>
      <div className="expanded-card">
        <div className="expanded-card-title">Lots ({lots.length})</div>
        {lots.length === 0 ? (
          <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>No open lots.</div>
        ) : (
          lots.map((lot) => (
            <div key={lot.id} className="alert-row" style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
              <span style={{ width: 100, flexShrink: 0, color: 'var(--text-secondary)' }}>{fmtDate(lot.purchase_date)}</span>
              <span>
                {fmtShares(lot.shares)} @ {fmtPrice(lot.cost_basis)}
              </span>
              {lot.corrected && <span className="badge badge-muted">corrected</span>}
              <button
                className="btn btn-ghost"
                style={{ marginLeft: 'auto', padding: '2px 8px', fontSize: 10 }}
                onClick={() => onFixLot(lot)}
                title="Data correction — not a trade"
              >
                fix entry
              </button>
            </div>
          ))
        )}
      </div>
      <div className="expanded-card">
        <div className="expanded-card-title">Sales ({sales.length})</div>
        {sales.length === 0 ? (
          <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>No sales recorded.</div>
        ) : (
          sales.map((s) => (
            <div key={s.id} className="alert-row" style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
              <span style={{ width: 100, flexShrink: 0, color: 'var(--text-secondary)' }}>{fmtDate(s.sale_date)}</span>
              <span>
                {fmtShares(s.shares)} @ {fmtPrice(s.price)}
              </span>
              <span
                style={{ marginLeft: 'auto', color: s.realized_pnl == null ? undefined : s.realized_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}
              >
                {fmtPnl(s.realized_pnl)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ── entry forms ── */

interface EntryDraft {
  ticker: string;
  shares: string;
  price: string;
  date: string;
  positionType: string;
  note: string;
}

const emptyDraft = (): EntryDraft => ({
  ticker: '',
  shares: '',
  price: '',
  date: localToday(),
  positionType: '',
  note: '',
});

function EntryForm({
  kind,
  onClose,
}: {
  kind: 'purchase' | 'sale';
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<EntryDraft>(emptyDraft);

  const mutation = useMutation({
    mutationFn: async () => {
      const ticker = draft.ticker.trim().toUpperCase();
      const shares = Number(draft.shares);
      const price = Number(draft.price);
      if (!ticker || !Number.isFinite(shares) || shares <= 0 || !Number.isFinite(price) || price <= 0 || !draft.date) {
        throw new Error('Ticker, positive shares, a positive price and a date are required.');
      }
      if (kind === 'purchase') {
        return addLot({
          ticker,
          shares,
          cost_basis: price,
          purchase_date: draft.date,
          ...(draft.positionType ? { position_type: draft.positionType } : {}),
          ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
        });
      }
      return recordSale({
        ticker,
        shares,
        price,
        sale_date: draft.date,
        ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] });
      qc.invalidateQueries({ queryKey: ['ledger'] });
      onClose();
    },
  });

  const set = (k: keyof EntryDraft) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ width: 500, maxWidth: 'calc(100vw - 32px)' }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            {kind === 'purchase' ? 'Record purchase lot' : 'Record sale'}
          </div>
          <button className="reader-popup-close" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close transaction form">
            Close
          </button>
        </div>
        <div className="muted" style={{ fontSize: 'var(--text-xs)', marginBottom: 12, lineHeight: 1.5 }}>
          {kind === 'purchase'
            ? 'Adds one explicit purchase lot to the ledger.'
            : 'Records a sale against open lots using the ledger FIFO matcher.'}
        </div>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <label style={{ fontSize: 'var(--text-xs)' }}>
            Ticker
            <input
              className="field"
              style={{ marginTop: 4, textTransform: 'uppercase', fontFamily: 'var(--font-data)' }}
              placeholder="AAPL"
              value={draft.ticker}
              onChange={set('ticker')}
              autoFocus
              aria-label="Ticker"
            />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
            <label style={{ fontSize: 'var(--text-xs)' }}>
              Shares
              <input className="field" style={{ marginTop: 4 }} inputMode="decimal" value={draft.shares} onChange={set('shares')} aria-label="Shares" />
            </label>
            <label style={{ fontSize: 'var(--text-xs)' }}>
              {kind === 'purchase' ? 'Cost / share' : 'Sale price'}
              <input className="field" style={{ marginTop: 4 }} inputMode="decimal" value={draft.price} onChange={set('price')} aria-label={kind === 'purchase' ? 'Cost per share' : 'Sale price'} />
            </label>
            <label style={{ fontSize: 'var(--text-xs)' }}>
              Date
              <input className="field" type="date" style={{ marginTop: 4 }} value={draft.date} onChange={set('date')} aria-label="Date" />
            </label>
          </div>
          {kind === 'purchase' && (
            <label style={{ fontSize: 'var(--text-xs)' }}>
              Position type
              <select
                className="field"
                style={{ marginTop: 4 }}
                value={draft.positionType}
                onChange={(e) => setDraft((d) => ({ ...d, positionType: e.target.value }))}
                aria-label="Position type"
              >
                <option value="">Not set</option>
                {POSITION_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label style={{ fontSize: 'var(--text-xs)' }}>
            Note
            <input className="field" style={{ marginTop: 4 }} value={draft.note} onChange={set('note')} placeholder="Optional" aria-label="Note" />
          </label>
          {mutation.isError && (
            <div className="banner banner-warning">
              {(mutation.error as Error).message}
              <div className="muted" style={{ fontSize: 'var(--text-xs)', marginTop: 4 }}>
                Check shares/price/date and try again. If you are correcting an already-recorded entry rather than recording a trade, use “fix entry” on the lot instead.
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn-accent" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Recording…' : kind === 'purchase' ? 'Record purchase' : 'Record sale'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── lot correction modal ── */

function FixLotModal({
  lot,
  onClose,
}: {
  lot: { id: string; shares: number | null; cost_basis: number | null; purchase_date: string | null };
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [shares, setShares] = useState(lot.shares != null ? String(lot.shares) : '');
  const [cost, setCost] = useState(lot.cost_basis != null ? String(lot.cost_basis) : '');
  const [date, setDate] = useState(lot.purchase_date ?? '');
  const [remove, setRemove] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      correctLot(lot.id, {
        ...(remove
          ? { remove: true }
          : {
              ...(shares !== '' ? { shares: Number(shares) } : {}),
              ...(cost !== '' ? { cost_basis: Number(cost) } : {}),
              ...(date !== '' ? { purchase_date: date } : {}),
            }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] });
      qc.invalidateQueries({ queryKey: ['ledger'] });
      onClose();
    },
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-title">Fix entry — data correction, not a trade</div>
        <div className="muted" style={{ fontSize: 'var(--text-xs)', marginBottom: 12 }}>
          Corrections rewrite this lot record; they never count as buys or sells.
        </div>
        <div className="stack">
          <label style={{ fontSize: 'var(--text-xs)' }}>
            Shares
            <input className="field" style={{ marginTop: 4 }} value={shares} onChange={(e) => setShares(e.target.value)} disabled={remove} />
          </label>
          <label style={{ fontSize: 'var(--text-xs)' }}>
            Cost / share
            <input className="field" style={{ marginTop: 4 }} value={cost} onChange={(e) => setCost(e.target.value)} disabled={remove} />
          </label>
          <label style={{ fontSize: 'var(--text-xs)' }}>
            Purchase date
            <input className="field" type="date" style={{ marginTop: 4 }} value={date} onChange={(e) => setDate(e.target.value)} disabled={remove} />
          </label>
          <label style={{ fontSize: 'var(--text-xs)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={remove} onChange={(e) => setRemove(e.target.checked)} />
            Remove this lot (entered in error)
          </label>
          {mutation.isError && <div className="banner banner-warning">{(mutation.error as Error).message}</div>}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn-accent" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              {mutation.isPending ? 'Saving…' : 'Apply correction'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── page ── */

export default function Portfolio() {
  const qc = useQueryClient();
  const toast = useToast();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [entryForm, setEntryForm] = useState<'purchase' | 'sale' | null>(null);
  const [fixLot, setFixLot] = useState<{ id: string; shares: number | null; cost_basis: number | null; purchase_date: string | null } | null>(null);

  const { data, isPending, isError, error } = useQuery({ queryKey: ['portfolio'], queryFn: getPortfolio });

  const refresh = useMutation({
    mutationFn: refreshPortfolio,
    onSuccess: (res) =>
      toast(res?.updated ? `Prices refreshed for ${res.updated} holding${res.updated === 1 ? '' : 's'}.`
                         : 'Prices refreshed — nothing to update (no holdings or markets closed).'),
    onSettled: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  });

  const typeMutation = useMutation({
    mutationFn: ({ ticker, positionType }: { ticker: string; positionType: string | null }) => setPositionType(ticker, positionType),
    onSettled: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  });

  const holdings = data?.holdings ?? [];
  const totals = data?.totals;

  const renderRow = (h: HoldingRow) => {
    const isOpen = expanded === h.ticker;
    const rows = [
      <tr key={h.ticker} className="stage-row" onClick={() => setExpanded(isOpen ? null : h.ticker)}>
        <td>
          <TickerLink ticker={h.ticker} />
        </td>
        <td className="num">{fmtShares(h.shares)}</td>
        <td className="num">{fmtPrice(h.avg_cost)}</td>
        <td className="num">
          {h.price == null ? (
            <span
              className="muted"
              title="No retained market data for this ticker yet — it's an unknown or manually-entered symbol. Coverage will try to fetch a price and financials."
            >
              unpriced
            </span>
          ) : (
            fmtPrice(h.price)
          )}
        </td>
        <td className="num">{fmtUsdCompact(h.market_value)}</td>
        <td className="num" style={{ color: h.unrealized_pnl == null ? undefined : h.unrealized_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
          {fmtPnl(h.unrealized_pnl)}
        </td>
        <td className="num">{weightLabel(h.weight)}</td>
        <td onClick={(e) => e.stopPropagation()}>
          <select
            className="editor-select"
            value={h.position_type ?? ''}
            disabled={typeMutation.isPending}
            onChange={(e) => typeMutation.mutate({ ticker: h.ticker, positionType: e.target.value || null })}
            aria-label={`Position type for ${h.ticker}`}
          >
            <option value="">—</option>
            {POSITION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </td>
        <td>
          <HealthChip label={h.thesis_health_label} />
        </td>
        <td>
          <CoverageChip state={h.coverage_state} />
        </td>
        <td>
          <span className="pill-row">
            {(h.flags ?? []).map((f, i) => (
              <span key={`${f.kind}-${i}`} className="tag-amber" title={f.kind.replace(/_/g, ' ')}>
                {f.detail || f.kind.replace(/_/g, ' ')}
              </span>
            ))}
          </span>
        </td>
      </tr>,
    ];
    if (isOpen) {
      rows.push(
        <tr key={`${h.ticker}-detail`}>
          <td colSpan={COLS} className="expanded-area" style={{ cursor: 'default' }}>
            <HoldingDetail ticker={h.ticker} onFixLot={setFixLot} />
          </td>
        </tr>,
      );
    }
    return rows;
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-kicker">Portfolio</div>
          <h1 className="page-title">Holdings</h1>
          <div className="page-subtitle">Ledger-backed positions with memo-backed thesis coverage.</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => setEntryForm(entryForm === 'purchase' ? null : 'purchase')}>
            Record purchase
          </button>
          <button className="btn" onClick={() => setEntryForm(entryForm === 'sale' ? null : 'sale')}>
            Record sale
          </button>
          <button
            className="btn"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
            title="Updates prices and P&L only — never thesis health or your entered records."
          >
            {refresh.isPending ? 'Refreshing…' : 'Refresh prices'}
          </button>
        </div>
      </div>

      {entryForm && <EntryForm kind={entryForm} onClose={() => setEntryForm(null)} />}

      <div className="kpi-grid" style={{ marginBottom: 14 }}>
        <div className="kpi-card">
          <div className="kpi-label">Total Value</div>
          <div className="kpi-value num" style={{ textAlign: 'left' }}>{fmtUsdCompact(totals?.market_value)}</div>
          <div className="kpi-detail">cost basis {fmtUsdCompact(totals?.cost_basis)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Unrealized P&L</div>
          <div
            className="kpi-value num"
            style={{ textAlign: 'left', color: totals?.unrealized_pnl == null ? undefined : totals.unrealized_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            {fmtPnl(totals?.unrealized_pnl)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Realized P&L</div>
          <div
            className="kpi-value num"
            style={{ textAlign: 'left', color: totals?.realized_pnl == null ? undefined : totals.realized_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            {fmtPnl(totals?.realized_pnl)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Positions</div>
          <div className="kpi-value num" style={{ textAlign: 'left' }}>{totals?.positions ?? holdings.length}</div>
        </div>
      </div>

      {holdings.length > 0 && <AnalyticsSection />}

      {refresh.isError && (
        <div className="banner banner-warning" style={{ marginBottom: 12 }}>
          Price refresh failed: {(refresh.error as Error).message}
        </div>
      )}
      {typeMutation.isError && (
        <div className="banner banner-warning" style={{ marginBottom: 12 }}>
          Could not save position type: {(typeMutation.error as Error).message}
        </div>
      )}

      {isPending ? (
        <div className="stage-empty">Loading holdings…</div>
      ) : isError ? (
        <div className="stage-empty">Holdings unavailable: {(error as Error).message}</div>
      ) : holdings.length === 0 ? (
        <div className="stage-empty">
          No holdings recorded. Use “Record purchase” to add your first lot — held tickers get memo-backed thesis coverage automatically.
        </div>
      ) : (
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th style={{ width: 80 }}>Ticker</th>
                <th className="num" style={{ width: 80 }}>Shares</th>
                <th className="num" style={{ width: 90 }}>Avg Cost</th>
                <th className="num" style={{ width: 90 }}>Price</th>
                <th className="num" style={{ width: 100 }}>Mkt Value</th>
                <th className="num" style={{ width: 110 }}>Unreal P&L</th>
                <th className="num" style={{ width: 80 }}>Weight</th>
                <th style={{ width: 100 }}>Type</th>
                <th style={{ width: 100 }}>Thesis Health</th>
                <th style={{ width: 110 }}>Coverage</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>{holdings.flatMap(renderRow)}</tbody>
          </table>
        </div>
      )}

      <div className="inline-metadata" style={{ marginTop: 10 }}>
        <span>Price refresh is market-data only — it never re-judges thesis health.</span>
        <span>Coverage: FundOps keeps memo-backed thesis coverage for holdings.</span>
      </div>

      {fixLot && <FixLotModal lot={fixLot} onClose={() => setFixLot(null)} />}
    </div>
  );
}
