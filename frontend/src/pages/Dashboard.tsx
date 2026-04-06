import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';

const DEFAULT_SCHEDULES = [
  { agent: 'Screener', description: 'Score universe against your strategy', frequency: 'Weekly', time: 'Sun 8:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Portfolio Monitor', description: 'Update prices, P&L, thesis health', frequency: 'Daily', time: '7:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Outcome Checker', description: 'Check prediction accuracy vs actuals', frequency: 'Daily', time: '6:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Library Sync', description: 'Collect and index new research artifacts', frequency: 'Weekly', time: 'Mon 6:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Full Pipeline', description: 'Scout → Thesis → IC → Pulse → Allocator', frequency: 'Weekly', time: 'Sun 9:00 AM', status: 'paused', cost: '~$0.50' },
  { agent: 'Thesis Batch', description: 'Run thesis on all promoted screener picks', frequency: 'Manual', time: '—', status: 'manual', cost: '~$0.10/ticker' },
  { agent: 'Memo Generation', description: 'Generate investment memo for IC-passed stocks', frequency: 'Manual', time: '—', status: 'manual', cost: '~$0.38/memo' },
];

export function Dashboard() {
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard, refetchInterval: 30000 });
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.getConfig });
  const { data: proposals } = useQuery({ queryKey: ['learning-proposals'], queryFn: api.getLearningProposals, staleTime: 120000 });
  const { data: outcomes } = useQuery({ queryKey: ['learning-outcomes'], queryFn: () => api.getLearningOutcomes(undefined, 20), staleTime: 120000 });
  const { data: drift } = useQuery({ queryKey: ['learning-drift'], queryFn: api.getLearningDrift, staleTime: 120000 });
  const autonomyMode = config?.system?.autonomy_mode || 'suggest';
  const { data: pendingData } = useQuery({ queryKey: ['pending-approvals'], queryFn: api.listPendingApprovals, staleTime: 30000 });
  const { data: portfolioData } = useQuery({ queryKey: ['portfolio'], queryFn: api.portfolioStatus, staleTime: 60000 });
  const qc = useQueryClient();
  const approveMut = useMutation({
    mutationFn: (id: number) => api.approvePending(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pending-approvals'] }),
  });
  const rejectMut = useMutation({
    mutationFn: (id: number) => api.rejectPending(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pending-approvals'] }),
  });
  const pending = pendingData?.pending || [];
  const d = data || {};
  // Use direct portfolio data if available, fall back to dashboard's cached snapshot
  const portfolio = portfolioData?.holdings?.length ? portfolioData : (d.latest_portfolio || {});
  const rawHoldings = portfolioData?.holdings || d.latest_portfolio?.holdings || [];
  const parsedHoldings = typeof rawHoldings === 'string' ? (() => { try { return JSON.parse(rawHoldings); } catch { return []; } })() : rawHoldings;
  const holdings: any[] = (Array.isArray(parsedHoldings) ? parsedHoldings : []).filter((h: any) => typeof h === 'object');
  const counts = d.agent_run_counts || {};
  const recent = d.recent_runs || [];
  const status = d.agent_status || {};
  const savedSchedules = config?.system?.schedules || DEFAULT_SCHEDULES;
  const savedAgents = new Set(savedSchedules.map((s: any) => s.agent));
  const schedules = [
    ...savedSchedules,
    ...DEFAULT_SCHEDULES.filter((d: any) => !savedAgents.has(d.agent)).map((d: any) => ({ ...d, frequency: 'Manual', time: '—', status: 'manual' })),
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 600 }}>Dashboard</h1>
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)' }}>
            {recent.length > 0 ? `updated ${new Date(recent[0]?.run_at).toLocaleString()}` : 'no data yet'}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 10 }}>
        <div className="kpi-card">
          <div className="kpi-label">Portfolio</div>
          <div className="kpi-value">{(() => { const v = portfolio.total_value || 0; return v >= 1_000_000 ? `$${(v/1_000_000).toFixed(2)}M` : v >= 1_000 ? `$${(v/1_000).toFixed(1)}K` : `$${v.toLocaleString()}`; })()}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Daily P&L</div>
          <div className="kpi-value" style={{ color: (portfolio.daily_pnl || 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
            ${(portfolio.daily_pnl || 0).toLocaleString()}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Agent Runs</div>
          <div className="kpi-value">{Object.values(counts).reduce((a: number, b: any) => a + (b as number), 0)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Pipeline</div>
          <div className="kpi-value" style={{ fontSize: 'var(--text-lg)' }}>
            {counts.screener || 0} → {counts.thesis || 0} → {counts.ic_review || 0}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Status</div>
          <div className="kpi-value" style={{ fontSize: 'var(--text-lg)', color: 'var(--positive)' }}>Online</div>
        </div>
      </div>

      {/* Learning Recommendation — only in suggest/autopilot mode */}
      {autonomyMode !== 'manual' && <LearningRecommendation proposals={proposals} drift={drift} outcomes={outcomes} autonomyMode={autonomyMode} />}

      {/* Main content */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 220px', gap: 8 }}>
        <div className="card">
          <div className="card-title">Recent Activity</div>
          {recent.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>No activity yet. Run the pipeline to get started.</div>}
          {recent.slice(0, 10).map((r: any, i: number) => (
            <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between' }}>
              <span>
                {r.agent}: <Link to={`/ticker/${r.ticker}`} className="ticker">{r.ticker}</Link>
                {r.verdict && <span className={`badge ${r.verdict === 'PASS' ? 'badge-pass' : 'badge-nopass'}`} style={{ marginLeft: 4 }}>{r.verdict}</span>}
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-data)' }}>
                {r.run_at ? new Date(r.run_at).toLocaleTimeString() : ''}
              </span>
            </div>
          ))}
        </div>

        <div>
          <div className="card">
            <div className="card-title">Agent Status</div>
            {Object.entries(status).map(([name, st]) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--text-sm)', padding: '3px 0' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: st === 'running' ? 'var(--accent)' : 'var(--text-muted)' }} />
                {name}: {st as string}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Portfolio Holdings */}
      {holdings.length > 0 && (
        <div className="card" style={{ marginTop: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>
              Holdings ({holdings.length})
            </div>
            <Link to="/portfolio" style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none' }}>
              View Portfolio {'\u2192'}
            </Link>
          </div>
          <table style={{ width: '100%', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                <th style={{ padding: '3px 0', fontWeight: 500 }}>Ticker</th>
                <th style={{ padding: '3px 0', fontWeight: 500, textAlign: 'right' }}>Shares</th>
                <th style={{ padding: '3px 0', fontWeight: 500, textAlign: 'right' }}>Avg Cost</th>
                <th style={{ padding: '3px 0', fontWeight: 500, textAlign: 'right' }}>Price</th>
                <th style={{ padding: '3px 0', fontWeight: 500, textAlign: 'right' }}>P&L</th>
                <th style={{ padding: '3px 0', fontWeight: 500, textAlign: 'right' }}>Weight</th>
              </tr>
            </thead>
            <tbody>
              {holdings.slice(0, 10).map((h: any, i: number) => {
                const pnlPct = h.pnl_pct ?? 0;
                return (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '4px 0' }}>
                      <Link to={`/ticker/${h.ticker}`} className="ticker">{h.ticker}</Link>
                      {h.lots?.length > 1 && (
                        <span style={{ color: 'var(--text-muted)', fontSize: 9, marginLeft: 4 }}>
                          {h.lots.length} lots
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '4px 0', textAlign: 'right' }}>{(h.shares ?? 0).toLocaleString()}</td>
                    <td style={{ padding: '4px 0', textAlign: 'right' }}>${(h.cost_basis ?? 0).toFixed(2)}</td>
                    <td style={{ padding: '4px 0', textAlign: 'right' }}>${(h.current_price ?? 0).toFixed(2)}</td>
                    <td style={{ padding: '4px 0', textAlign: 'right', color: pnlPct >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                    </td>
                    <td style={{ padding: '4px 0', textAlign: 'right', color: 'var(--text-muted)' }}>
                      {(h.weight ?? 0).toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {holdings.length > 10 && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 4, textAlign: 'center' }}>
              + {holdings.length - 10} more positions
            </div>
          )}
        </div>
      )}

      {/* Pending Approvals */}
      {pending.length > 0 && (
        <div className="card" style={{ marginTop: 8, border: '1px solid var(--warning)' }}>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--warning)', display: 'inline-block' }} />
            Pending Approvals ({pending.length})
          </div>
          {pending.map((p: any) => {
            const decision = p.decision_data ? (typeof p.decision_data === 'string' ? JSON.parse(p.decision_data) : p.decision_data) : {};
            return (
              <div key={p.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-sm)' }}>
                <div>
                  <Link to={`/ticker/${p.ticker}`} className="ticker" style={{ fontWeight: 600 }}>{p.ticker}</Link>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                    IC {decision.verdict || 'PASS'} → waiting for {p.next_agent}
                  </span>
                  {decision.base_return && (
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 6, fontFamily: 'var(--font-data)', fontSize: 10 }}>
                      base {decision.base_return}% / bear {decision.bear_return}%
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    onClick={() => approveMut.mutate(p.id)}
                    disabled={approveMut.isPending}
                    style={{ padding: '2px 10px', fontSize: 11, background: 'var(--positive)', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer' }}
                  >Approve</button>
                  <button
                    onClick={() => rejectMut.mutate(p.id)}
                    disabled={rejectMut.isPending}
                    style={{ padding: '2px 10px', fontSize: 11, background: 'transparent', color: 'var(--text-muted)', border: '1px solid var(--border)', borderRadius: 3, cursor: 'pointer' }}
                  >Skip</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Learning Context (compact footer) */}
      {outcomes?.outcomes?.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '8px 0', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)', borderTop: '1px solid var(--border)', marginTop: 8 }}>
          <span style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}>LEARNING</span>
          {(() => {
            const alphas = outcomes.outcomes.filter((o: any) => o.alpha_pct != null).map((o: any) => o.alpha_pct);
            const avg = alphas.length ? alphas.reduce((a: number, b: number) => a + b, 0) / alphas.length : null;
            return avg != null ? (
              <span style={{ color: avg >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                Alpha: {avg >= 0 ? '+' : ''}{avg.toFixed(1)}%
              </span>
            ) : null;
          })()}
          <Link to="/mirror" style={{ color: 'var(--accent)', textDecoration: 'none', marginLeft: 'auto' }}>→ Open Mirror</Link>
        </div>
      )}

      {/* Schedules */}
      <div className="card" style={{ marginTop: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Schedules</div>
          <Link to="/settings" style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none', opacity: 0.8 }}>
            Edit in Settings →
          </Link>
        </div>
        <table style={{ width: '100%', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '20%' }}>Agent</th>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '30%' }}>Description</th>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '15%' }}>Frequency</th>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '15%' }}>Time</th>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '10%' }}>Status</th>
              <th style={{ padding: '4px 0', fontWeight: 500, width: '10%' }}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {schedules.map((s: any, i: number) => (
              <tr key={i} style={{ borderBottom: i < schedules.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <td style={{ padding: '6px 0', fontWeight: 600 }}>{s.agent}</td>
                <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{s.description}</td>
                <td style={{ padding: '6px 0' }}>{s.frequency}</td>
                <td style={{ padding: '6px 0' }}>{s.time}</td>
                <td style={{ padding: '6px 0' }}>
                  <span style={{
                    fontSize: 9, padding: '1px 6px', borderRadius: 3,
                    background: s.status === 'active' ? 'rgba(52,168,83,0.15)' : s.status === 'paused' ? 'rgba(251,188,4,0.15)' : 'rgba(255,255,255,0.05)',
                    color: s.status === 'active' ? 'var(--positive)' : s.status === 'paused' ? 'var(--warning)' : 'var(--text-muted)',
                  }}>
                    {s.status === 'active' ? 'ACTIVE' : s.status === 'paused' ? 'PAUSED' : 'MANUAL'}
                  </span>
                </td>
                <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{s.cost || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Learning Recommendation Card ──────────────────────────────────

function LearningRecommendation({ proposals, drift, outcomes, autonomyMode }: {
  proposals: any; drift: any; outcomes: any; autonomyMode: string;
}) {
  const [dismissed, setDismissed] = useState(false);
  void useQueryClient; // available for future use

  const proposalCount = proposals?.count || 0;
  const hasDrift = drift?.has_enough_data && (
    (drift.style_drift?.length > 0) ||
    (drift.signal_drift?.length > 0) ||
    (drift.anti_signal_violations?.length > 0)
  );
  const driftSummary = drift?.summary || '';

  // Build recommendation messages
  const messages: { icon: string; text: string; detail: string; action?: string; link?: string }[] = [];

  if (proposalCount > 0) {
    const p = proposals.proposals?.[0];
    messages.push({
      icon: '\u2699',
      text: `${proposalCount} scoring refinement${proposalCount > 1 ? 's' : ''} ready for review`,
      detail: p?.proposal || 'Pattern detected in your feedback — a scoring adjustment is suggested.',
      action: 'Discuss',
      link: '/',
    });
  }

  if (hasDrift) {
    const driftItems = [
      ...(drift.style_drift || []),
      ...(drift.signal_drift || []),
    ];
    const firstDrift = driftItems[0];
    messages.push({
      icon: '\u26A0',
      text: 'Behavioral drift detected',
      detail: firstDrift || driftSummary || 'Your IC decisions are diverging from your stated strategy.',
      link: '/',
    });
  }

  if (outcomes?.outcomes?.length > 0) {
    const alphas = outcomes.outcomes.filter((o: any) => o.alpha_pct != null).map((o: any) => o.alpha_pct);
    const avg = alphas.length ? alphas.reduce((a: number, b: number) => a + b, 0) / alphas.length : null;
    if (avg != null && Math.abs(avg) > 2) {
      messages.push({
        icon: avg >= 0 ? '\u2191' : '\u2193',
        text: `Outcome tracking: ${avg >= 0 ? '+' : ''}${avg.toFixed(1)}% alpha across ${alphas.length} predictions`,
        detail: avg >= 0
          ? 'Your screener picks are outperforming the benchmark.'
          : 'Screener picks are underperforming — consider reviewing scoring weights.',
        link: '/',
      });
    }
  }

  if (messages.length === 0 || dismissed) return null;

  return (
    <div className="card" style={{
      marginBottom: 8,
      border: '1px solid var(--accent-muted)',
      background: 'linear-gradient(135deg, rgba(245,166,35,0.06) 0%, var(--bg-secondary) 100%)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', animation: 'pulse 2s ease-in-out infinite' }} />
          <span className="card-title" style={{ marginBottom: 0, fontSize: 'var(--text-sm)' }}>
            FundOps has recommendations for you
          </span>
          <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 3, background: 'var(--accent-subtle)', color: 'var(--accent)', fontFamily: 'var(--font-data)', textTransform: 'uppercase' }}>
            {autonomyMode}
          </span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14, padding: '0 4px' }}
        >&times;</button>
      </div>

      {messages.map((msg, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0',
          borderTop: i > 0 ? '1px solid var(--border)' : 'none',
        }}>
          <span style={{ fontSize: 16, lineHeight: 1, marginTop: 2 }}>{msg.icon}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
              {msg.text}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
              {msg.detail}
            </div>
          </div>
          {msg.link && (
            <Link to={msg.link} style={{
              fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none',
              padding: '4px 10px', border: '1px solid var(--accent-muted)', borderRadius: 'var(--radius-sm)',
              whiteSpace: 'nowrap', alignSelf: 'center',
            }}>
              {msg.action || 'View'} →
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}
