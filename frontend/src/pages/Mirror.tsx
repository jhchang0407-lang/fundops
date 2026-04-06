import { useState, useRef, useEffect } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { pctSigned } from '../utils/formatFinancials';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

type ChatMessage = { role: string; content: string };

/* ------------------------------------------------------------------ */
/*  Helper: format money                                               */
/* ------------------------------------------------------------------ */
function formatMoney(value: number | undefined) {
  const amount = value || 0;
  if (Math.abs(amount) >= 1_000_000) return `$${(amount / 1_000_000).toFixed(2)}M`;
  if (Math.abs(amount) >= 1_000) return `$${(amount / 1_000).toFixed(1)}K`;
  return `$${amount.toFixed(0)}`;
}

/* ------------------------------------------------------------------ */
/*  Helper: extract signals from strategy dimensions                   */
/* ------------------------------------------------------------------ */
function extractSignals(strategy: any) {
  const dims = strategy?.dimensions || {};
  const mustHave: string[] = [];
  const antiSignals: string[] = [];

  // Look for explicit must_have / anti_signal arrays first
  if (Array.isArray(dims.must_have_signals)) {
    mustHave.push(...dims.must_have_signals);
  }
  if (Array.isArray(dims.anti_signals)) {
    antiSignals.push(...dims.anti_signals);
  }

  // Fallback: generate pill-friendly labels from dimension keys
  // The dimension values are long descriptions, so we map known keys to short labels
  const keyToPill: Record<string, string> = {
    margin_quality: 'High margins',
    roic_quality: 'High ROIC',
    growth: 'Revenue growth',
    time_horizon: '3-5yr horizon',
    fcf: 'FCF positive',
    free_cash_flow: 'FCF positive',
    position_sizing: 'Concentrated',
    cheapness_valuation: 'Meaningful discount',
    valuation_approach: 'Valuation discipline',
  };

  if (mustHave.length === 0) {
    const positiveKeys = Object.keys(dims).filter(key =>
      !['north_star_summary', 'style_identity', 'horizon', 'cheapness_valuation'].includes(key)
    );
    for (const key of positiveKeys.slice(0, 4)) {
      mustHave.push(keyToPill[key] || key.replace(/_/g, ' '));
    }
  }
  if (antiSignals.length === 0) {
    // Check if cheapness/valuation dimension exists (it's about what to avoid = cheap traps)
    if (dims.cheapness_valuation) {
      antiSignals.push(keyToPill.cheapness_valuation || 'Value traps');
    }
  }

  return { mustHave, antiSignals };
}

/* ------------------------------------------------------------------ */
/*  View Toggle: Mirror / Configure                                    */
/* ------------------------------------------------------------------ */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function _ViewToggle({ active }: { active: 'mirror' | 'configure' }) {
  const activeStyle: React.CSSProperties = {
    padding: '5px 16px',
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font-ui)',
    fontWeight: 600,
    border: 'none',
    textDecoration: 'none',
    display: 'inline-block',
    background: 'var(--accent-subtle)',
    color: 'var(--accent)',
  };
  const inactiveStyle: React.CSSProperties = {
    padding: '5px 16px',
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font-ui)',
    fontWeight: 500,
    border: 'none',
    textDecoration: 'none',
    display: 'inline-block',
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 20px', borderBottom: '1px solid var(--border)', marginBottom: 12, marginLeft: -20, marginRight: -20, marginTop: -16 }}>
      <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>HOME</span>
      <div style={{ display: 'flex', gap: 0, border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        {active === 'mirror' ? (
          <span style={activeStyle}>Mirror</span>
        ) : (
          <Link to="/" style={inactiveStyle}>Mirror</Link>
        )}
        {active === 'configure' ? (
          <span style={activeStyle}>Chat</span>
        ) : (
          <Link to="/" style={inactiveStyle}>Chat</Link>
        )}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  MODE A: Onboarding Conversation                                    */
/* ================================================================== */
function OnboardingConversation() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [pendingProfile, setPendingProfile] = useState<any>(null);
  const [lastResponse, setLastResponse] = useState<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Hydrate conversation history from backend on mount
  const { data: savedHistory } = useQuery({
    queryKey: ['conversation-history'],
    queryFn: () => api.getConversationHistory(),
    staleTime: Infinity, // Only load once
  });

  useEffect(() => {
    if (savedHistory?.messages?.length > 0 && history.length === 0) {
      setHistory(savedHistory.messages.map((m: any) => ({
        role: m.role as string,
        content: m.content as string,
      })));
    }
  }, [savedHistory]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  const conversation = useMutation({
    mutationFn: (nextMessage: string) => api.strategyConversation(nextMessage, history),
    onSuccess: (data, nextMessage) => {
      const nextHistory = [...history, { role: 'user', content: nextMessage }, { role: 'assistant', content: data.message }];
      setHistory(nextHistory);
      setLastResponse(data);
      if (data.strategy_profile) {
        setPendingProfile(data.strategy_profile);
      }
      // Invalidate strategy when agent actions were applied or strategy was auto-saved
      if ((data.applied_actions && data.applied_actions.length > 0) || data.strategy_saved) {
        queryClient.invalidateQueries({ queryKey: ['strategy'] });
        queryClient.invalidateQueries({ queryKey: ['config'] });
      }
      setMessage('');
    },
  });

  const saveStrategy = useMutation({
    mutationFn: (profile: any) => api.saveStrategy(profile),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['strategy'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ]);
      setPendingProfile(null);
    },
  });

  const resolveProposal = useMutation({
    mutationFn: (data: { id: string; action: 'accept' | 'reject' }) =>
      api.resolveLearningProposal(data.id, data.action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['learning-proposals'] });
      queryClient.invalidateQueries({ queryKey: ['refinement-proposals'] });
      queryClient.invalidateQueries({ queryKey: ['strategy'] });
    },
  });

  const send = (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || conversation.isPending) return;
    conversation.mutate(trimmed);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    send(message);
  };

  if (pendingProfile) {
    return (
      <div style={{ maxWidth: 640, margin: '0 auto', padding: '48px 20px' }}>
        <div className="section-label">REVIEW</div>
        <h2 style={{ margin: '6px 0 4px', fontFamily: 'var(--font-display)' }}>Your compiled investment constitution</h2>
        <div className="page-subtitle">This is the system's first draft of how you invest. Approve it when it feels true.</div>
        <div className="card">
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', marginBottom: 8 }}>
            {pendingProfile.north_star}
          </div>
          {pendingProfile.north_star_summary && (
            <div style={{ color: 'var(--text-secondary)', marginBottom: 14 }}>{pendingProfile.north_star_summary}</div>
          )}
          <div className="two-col">
            <div className="stack">
              <div className="card-title">Dimensions</div>
              {Object.entries(pendingProfile.dimensions || {}).map(([key, value]) => (
                <div key={key} style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' as const }}>{key.replace(/_/g, ' ')}</div>
                  <div style={{ marginTop: 4 }}>{String(value)}</div>
                </div>
              ))}
            </div>
            <div className="stack">
              <div className="card-title">Agent Defaults</div>
              {Object.entries(pendingProfile.agent_defaults || {}).length === 0 && (
                <div className="muted">The strategy profile is ready. Detailed agent tuning can happen afterward in Settings.</div>
              )}
              {Object.entries(pendingProfile.agent_defaults || {}).map(([key, value]) => (
                <div key={key} style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' as const }}>{key}</div>
                  <div style={{ marginTop: 4, color: 'var(--text-secondary)' }}>{JSON.stringify(value)}</div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
            <button className="btn" onClick={() => setPendingProfile(null)}>Keep refining</button>
            <button className="btn btn-accent" onClick={() => saveStrategy.mutate(pendingProfile)} disabled={saveStrategy.isPending}>
              {saveStrategy.isPending ? 'Saving...' : 'Approve Constitution'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 60px)', padding: '0 20px' }}>
      {/* Header */}
      <div style={{ textAlign: 'center', padding: '48px 0 24px' }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700, marginBottom: 8 }}>
          FundOps
        </h1>
        <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-base)', maxWidth: 420, margin: '0 auto' }}>
          Tell me about your investment approach. I'll configure the system around how you think, what you approve, and what actually works.
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {history.map((entry, index) => (
          <div
            key={`${entry.role}-${index}`}
            className={`convo-msg ${entry.role === 'user' ? 'convo-msg-user' : 'convo-msg-ai'}`}
            style={{
              padding: '10px 14px',
              borderRadius: 10,
              marginBottom: 6,
              lineHeight: 1.6,
              fontSize: 'var(--text-sm)',
              ...(entry.role === 'user'
                ? { background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.15)', maxWidth: '80%', marginLeft: 'auto' }
                : { background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)' }),
            }}
          >
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' as const, marginBottom: 4 }}>
              {entry.role === 'assistant' ? 'FundOps' : 'You'}
            </div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{entry.content}</div>
          </div>
        ))}
        {conversation.isPending && (
          <div style={{ padding: '10px 14px', borderRadius: 10, background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />

        {/* Quick-reply options */}
        {lastResponse?.options?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '6px 0' }}>
            {lastResponse.options.map((option: string) => (
              <button
                key={option}
                onClick={() => send(option)}
                type="button"
                style={{
                  padding: '6px 14px',
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border)',
                  borderRadius: 20,
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--text-xs)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-ui)',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
              >
                {option}
              </button>
            ))}
          </div>
        )}

        {/* Quick actions for learning proposals */}
        {lastResponse?.proposal_actions?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, padding: '6px 0' }}>
            {lastResponse.proposal_actions.map((pa: any) => (
              <div key={pa.id} style={{ display: 'flex', gap: 4 }}>
                <button className="quick-action-btn accept" onClick={() => resolveProposal.mutate({ id: pa.id, action: 'accept' })}>
                  Accept: {pa.label || 'Proposal'}
                </button>
                <button className="quick-action-btn reject" onClick={() => resolveProposal.mutate({ id: pa.id, action: 'reject' })}>
                  Skip
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} style={{ padding: '10px 0', borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSubmit(e as unknown as FormEvent); } }}
          placeholder="I'm a concentrated value investor who wants durable businesses with room for rerating..."
          style={{
            flex: 1,
            padding: '12px 16px',
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-ui)',
            fontSize: 'var(--text-sm)',
            outline: 'none',
            resize: 'none',
            minHeight: 44,
          }}
        />
        <button className="btn btn-accent" type="submit" disabled={conversation.isPending || !message.trim()} style={{ alignSelf: 'flex-end' }}>
          Send
        </button>
      </form>
      <div style={{ display: 'flex', gap: 16, fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)', marginTop: 4, paddingBottom: 12 }}>
        <span>Conversation builds your constitution</span>
        <span>Scoring logic compiles from your words</span>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Constitution Snapshot Card                                         */
/* ================================================================== */
export function _ConstitutionSnapshot({ strategy, version, versionsData }: { strategy: any; version: any; versionsData: any }) {
  const { mustHave, antiSignals } = extractSignals(strategy);
  const versionNumber = version?.version_number || versionsData?.versions?.[0]?.version_number || 1;
  const icHurdles = strategy?.agent_defaults?.ic_review || strategy?.dimensions?.ic_hurdles || {};

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 500, lineHeight: 1.4, marginBottom: 6 }}>
            "{strategy?.north_star || strategy?.name}"
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)', marginBottom: 14 }}>
            <span>Style: {strategy?.dimensions?.style_identity || 'concentrated quality compounder'}</span>
            <span>Horizon: {strategy?.dimensions?.horizon || '3-5 years'}</span>
            <span>v{versionNumber} {version?.updated_at ? `-- updated ${formatRelativeDate(version.updated_at)}` : ''}</span>
          </div>
        </div>
        <Link to="/" style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap', cursor: 'pointer' }}>
          Refine via conversation
        </Link>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginBottom: 6 }}>
            MUST-HAVE SIGNALS
          </div>
          <div>
            {(mustHave.length ? mustHave : ['Still learning your signal set']).map((s) => (
              <span key={s} className={`pill ${mustHave.length ? 'pill-positive' : 'pill-muted'}`}>{s}</span>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginBottom: 6 }}>
            ANTI-SIGNALS
          </div>
          <div>
            {(antiSignals.length ? antiSignals : ['Will emerge through decisions']).map((s) => (
              <span key={s} className={`pill ${antiSignals.length ? 'pill-negative' : 'pill-muted'}`}>{s}</span>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginBottom: 6 }}>
            IC HURDLES
          </div>
          <div style={{ display: 'grid', gap: 3, fontSize: 'var(--text-sm)', fontFamily: 'var(--font-data)' }}>
            <span>Base: <strong style={{ color: 'var(--accent)' }}>{icHurdles.base_return_pct || 20}%</strong></span>
            <span>Bear: <strong style={{ color: 'var(--accent)' }}>{icHurdles.bear_return_pct || 15}%</strong></span>
            <span>Haircut: <strong style={{ color: 'var(--accent)' }}>{icHurdles.bear_case_haircut || 70}%</strong></span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Said vs Did Section                                                */
/* ------------------------------------------------------------------ */
function SaidVsDid({ mirrorData, icDecisions, drift }: { mirrorData: any; icDecisions: any[]; drift?: any }) {
  const decisionsNeeded = Math.max(0, 5 - icDecisions.length);

  if (icDecisions.length < 5) {
    return (
      <div className="card">
        <div className="card-title">Said vs Did</div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 3 }}>
            <span>IC decisions needed for behavioral analysis</span>
            <span style={{ fontFamily: 'var(--font-data)' }}>{icDecisions.length}/5</span>
          </div>
          <div style={{ height: 4, background: 'var(--bg-tertiary)', borderRadius: 2 }}>
            <div style={{ width: `${Math.min(100, (icDecisions.length / 5) * 100)}%`, height: 4, background: 'var(--accent)', borderRadius: 2 }} />
          </div>
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          Keep researching. Every IC decision teaches the system about your actual preferences
          vs your stated constitution. Behavioral insights unlock at 5 decisions.
          {decisionsNeeded > 0 && ` ${decisionsNeeded} more needed.`}
        </div>
      </div>
    );
  }

  const signalDrifts = drift?.signal_drift || mirrorData?.signal_drifts || [];
  const antiBreaches = drift?.anti_signal_violations || mirrorData?.anti_signal_breaches || [];

  return (
    <div className="two-col">
      {/* Signal Drift */}
      <div className="card">
        <div className="card-title">Signal Drift</div>
        <table style={{ width: '100%', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '4px 0', color: 'var(--text-muted)', fontWeight: 500, borderBottom: '1px solid var(--border)' }}>Signal</th>
              <th style={{ textAlign: 'left', padding: '4px 0', color: 'var(--text-muted)', fontWeight: 500, borderBottom: '1px solid var(--border)' }}>Violated</th>
              <th style={{ textAlign: 'left', padding: '4px 0', color: 'var(--text-muted)', fontWeight: 500, borderBottom: '1px solid var(--border)' }}>In</th>
            </tr>
          </thead>
          <tbody>
            {signalDrifts.length === 0 && (
              <tr><td colSpan={3} style={{ padding: '8px 0', color: 'var(--text-muted)' }}>No signal drift detected yet</td></tr>
            )}
            {signalDrifts.map((d: any) => {
              const violatedPct = d.violated_pct ?? (d.violation_rate != null ? Math.round(d.violation_rate * 100) : 0);
              const count = d.count ?? d.violations ?? 0;
              return (
                <tr key={d.signal}>
                  <td style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>{d.signal}</td>
                  <td style={{ padding: '6px 0', borderBottom: '1px solid var(--border)', color: violatedPct > 0 ? 'var(--negative)' : 'var(--text-muted)' }}>
                    {violatedPct}%
                  </td>
                  <td style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>{count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {signalDrifts.some((d: any) => d.affected_tickers?.length) && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            Affected: {signalDrifts.flatMap((d: any) => d.affected_tickers || []).map((t: string) => (
              <Link key={t} to={`/ticker/${t}`} className="ticker" style={{ marginRight: 4 }}>{t}</Link>
            ))}
          </div>
        )}
      </div>

      {/* Anti-Signal Breaches */}
      <div className="card">
        <div className="card-title">Anti-Signal Breaches</div>
        {antiBreaches.length === 0 && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', padding: '6px 0' }}>No anti-signal breaches detected</div>
        )}
        {antiBreaches.map((breach: any) => {
          const breachCount = breach.count ?? breach.violations ?? 0;
          const breachPct = breach.pct ?? '';
          return (
          <div key={breach.signal} style={{ fontSize: 'var(--text-xs)', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--negative)', fontFamily: 'var(--font-data)' }}>{breach.signal}</span>
            {' '}triggered in <strong>{breachCount}</strong> approvals{breachPct ? ` (${breachPct}%)` : ''}
            {breach.affected_tickers?.length > 0 && (
              <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>
                Affected: {breach.affected_tickers.map((t: string) => (
                  <Link key={t} to={`/ticker/${t}`} className="ticker" style={{ marginRight: 4 }}>{t}</Link>
                ))}
              </div>
            )}
          </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Approval Profile                                                   */
/* ------------------------------------------------------------------ */
function ApprovalProfile({ icDecisions }: { icDecisions: any[] }) {
  if (icDecisions.length < 5) return null;

  const passCount = icDecisions.filter((r: any) => r.verdict === 'PASS').length;
  const failCount = icDecisions.length - passCount;
  const convictions = icDecisions.map((r: any) => Number(r.scores?.conviction || 0)).filter(Boolean);
  const meanConviction = convictions.length ? (convictions.reduce((a, b) => a + b, 0) / convictions.length).toFixed(1) : '0';
  const baseReturns = icDecisions.map((r: any) => Number(r.scores?.base_return || 0)).filter(Boolean);
  const bearReturns = icDecisions.map((r: any) => Number(r.scores?.bear_return || 0)).filter(Boolean);
  const lowConviction = convictions.filter((c) => c <= 2).length;

  const baseMin = baseReturns.length ? Math.min(...baseReturns) : 0;
  const baseMax = baseReturns.length ? Math.max(...baseReturns) : 0;
  const bearMin = bearReturns.length ? Math.min(...bearReturns) : 0;
  const bearMax = bearReturns.length ? Math.max(...bearReturns) : 0;

  return (
    <div className="card">
      <div className="card-title">Approval Profile</div>
      <div style={{ display: 'flex', gap: 20, fontSize: 'var(--text-sm)', fontFamily: 'var(--font-data)', marginBottom: 10 }}>
        <span>{passCount} passes</span>
        <span>{failCount} fails</span>
        <span>Mean conviction: <strong style={{ color: 'var(--accent)' }}>{meanConviction}/5</strong></span>
      </div>

      {/* Range bars */}
      <RangeBar label="Base return" min={baseMin} max={baseMax} />
      <RangeBar label="Bear return" min={bearMin} max={bearMax} />

      {lowConviction > 0 && (
        <div style={{ padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)', lineHeight: 1.5, marginTop: 8, background: 'rgba(251,188,4,0.08)', borderLeft: '3px solid var(--warning)', color: 'var(--text-secondary)' }}>
          {lowConviction}/{passCount} approvals had conviction &lt;= 2. Your IC gate may be too loose.
        </div>
      )}
    </div>
  );
}

function RangeBar({ label, min, max }: { label: string; min: number; max: number }) {
  const markerPos = max > 0 ? Math.min(90, Math.max(10, ((min + max) / 2 / 50) * 100)) : 30;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', marginBottom: 6 }}>
      <span style={{ width: 80, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ color: 'var(--text-muted)', width: 35, textAlign: 'right' }}>{Math.round(min)}%</span>
      <div style={{ flex: 1, height: 4, background: 'var(--bg-tertiary)', borderRadius: 2, position: 'relative' }}>
        <div style={{ position: 'absolute', top: -3, width: 10, height: 10, background: 'var(--accent)', borderRadius: '50%', left: `${markerPos}%` }} />
      </div>
      <span style={{ color: 'var(--text-muted)', width: 35, textAlign: 'right' }}>{Math.round(max)}%</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Constitution Evolution                                             */
/* ------------------------------------------------------------------ */
function ConstitutionEvolution({ changelog }: { changelog: any[] }) {
  if (!changelog || changelog.length === 0) return null;

  return (
    <div className="card">
      <div className="card-title">Constitution Evolution</div>
      <div style={{ paddingLeft: 16, borderLeft: '2px solid var(--border)' }}>
        {changelog.map((entry: any, i: number) => (
          <div key={i} style={{ position: 'relative', padding: '0 0 14px 14px' }}>
            <div style={{
              position: 'absolute',
              left: -22,
              top: 3,
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: entry.source === 'behavioral' ? 'var(--info)' : 'var(--accent)',
            }} />
            <div style={{ fontSize: 'var(--text-sm)' }}>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                {entry.from_version ? `v${entry.from_version} -> v${entry.to_version}` : `v${entry.version || 1}`}
              </span>
              {' '}{entry.description || entry.change}
            </div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)' }}>
              {entry.source || 'conversation'} -- {formatRelativeDate(entry.created_at || entry.date)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Portfolio KPIs                                                     */
/* ------------------------------------------------------------------ */
function PortfolioKpis({ portfolio }: { portfolio: any }) {
  if (!portfolio?.total_value && !portfolio?.position_count) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: 24 }}>
        <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', marginBottom: 8 }}>
          Import your portfolio to see P&L, thesis health, and action items.
        </div>
        <Link to="/settings" className="btn btn-ghost" style={{ textDecoration: 'none', fontSize: 'var(--text-xs)', padding: '4px 10px' }}>
          Go to Settings
        </Link>
      </div>
    );
  }

  return (
    <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 12 }}>
      <div className="kpi-card">
        <div className="kpi-label">PORTFOLIO</div>
        <div className="kpi-value">{formatMoney(portfolio.total_value)}</div>
        {portfolio.daily_pnl != null && (
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', marginTop: 2, color: portfolio.daily_pnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
            {portfolio.daily_pnl >= 0 ? '+' : ''}{formatMoney(portfolio.daily_pnl)} today
          </div>
        )}
      </div>
      <div className="kpi-card">
        <div className="kpi-label">P&L</div>
        <div className="kpi-value" style={{ color: (portfolio.total_return || 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
          {pctSigned(portfolio.total_return || 0)}
        </div>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', marginTop: 2, color: 'var(--text-muted)' }}>since inception</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">POSITIONS</div>
        <div className="kpi-value">{portfolio.position_count || 0}</div>
        {portfolio.position_breakdown && (
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', marginTop: 2, color: 'var(--text-muted)' }}>
            {portfolio.position_breakdown}
          </div>
        )}
      </div>
      <div className="kpi-card">
        <div className="kpi-label">THESIS HEALTH</div>
        <div className="kpi-value" style={{ color: (portfolio.thesis_health || 0) >= 70 ? 'var(--positive)' : 'var(--warning)' }}>
          {portfolio.thesis_health || '--'}
        </div>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', marginTop: 2, color: 'var(--text-muted)' }}>weighted avg</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Attention + Learning columns                                       */
/* ------------------------------------------------------------------ */
function AttentionAndLearning({ icDecisions, recentEvents, proposals }: { icDecisions: any[]; recentEvents: any[]; proposals: any[] }) {
  const icPassed = icDecisions.filter((r: any) => r.verdict === 'PASS').slice(0, 3);

  const behavioralProposals = proposals.filter((p: any) => p.source === 'behavioral' || !p.source);
  const patternProposals = proposals.filter((p: any) => p.source === 'pattern');
  const allProposals = [...behavioralProposals, ...patternProposals];

  return (
    <div className="two-col">
      {/* Your Attention */}
      <div className="card">
        <div className="card-title">Your Attention</div>
        {icPassed.length > 0 && (
          <>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginBottom: 6 }}>
              IC PASSED
            </div>
            {icPassed.map((decision: any) => (
              <div key={decision.ticker} style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-xs)' }}>
                <Link to={`/ticker/${decision.ticker}`} className="ticker">{decision.ticker}</Link>
                <span style={{ color: 'var(--positive)', fontFamily: 'var(--font-data)' }}>
                  PASS {decision.scores?.conviction || '?'}/5
                </span>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                  base {Math.round(decision.scores?.base_return || 0)}%
                </span>
              </div>
            ))}
          </>
        )}
        {icPassed.length === 0 && recentEvents.length === 0 && (
          <div className="muted">No recent attention items. Run the screener or pipeline.</div>
        )}
        {recentEvents.length > 0 && (
          <>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginTop: 10, marginBottom: 6 }}>
              RECENT
            </div>
            {recentEvents.slice(0, 4).map((event: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-xs)' }}>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', width: 48, flexShrink: 0 }}>
                  {event.created_at?.slice(5, 10) || event.run_at?.slice(5, 10) || ''}
                </span>
                <span>
                  {event.event_type || event.agent}{' '}
                  {event.ticker && <Link to={`/ticker/${event.ticker}`} className="ticker">{event.ticker}</Link>}
                  {event.description && ` ${event.description}`}
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Proposals Queue */}
      <div className="card">
        <div className="card-title">Proposals Queue</div>
        {allProposals.length === 0 && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Every IC decision teaches the system. Proposals surface here when behavioral patterns or long-horizon signals reach confidence thresholds.
          </div>
        )}
        {allProposals.slice(0, 4).map((proposal: any) => {
          const isBehavioral = proposal.source === 'behavioral' || !proposal.source;
          return (
            <div key={proposal.id} style={{ padding: '10px 12px', background: 'var(--bg-tertiary)', borderLeft: `3px solid ${isBehavioral ? 'var(--accent)' : 'var(--positive)'}`, borderRadius: 'var(--radius-sm)', marginBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                  fontSize: 9,
                  fontFamily: 'var(--font-data)',
                  letterSpacing: '0.08em',
                  padding: '1px 5px',
                  borderRadius: 3,
                  background: isBehavioral ? 'rgba(245,166,35,0.15)' : 'rgba(80,200,120,0.15)',
                  color: isBehavioral ? 'var(--accent)' : 'var(--positive)',
                }}>
                  {isBehavioral ? 'BEHAVIORAL' : 'PATTERN'}
                </span>
                {proposal.confidence && (
                  <span style={{ fontSize: 9, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
                    {proposal.confidence}% confidence
                  </span>
                )}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>{proposal.title || proposal.description}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Utility: format relative date                                      */
/* ------------------------------------------------------------------ */
function formatRelativeDate(dateStr: string | undefined): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? 's' : ''} ago`;
  return date.toLocaleDateString();
}

/* ================================================================== */
/*  MAIN EXPORT: Mirror Page                                           */
/* ================================================================== */
export function Mirror() {
  const { data: strategyData, isLoading } = useQuery({ queryKey: ['strategy'], queryFn: api.getStrategy });
  const strategy = strategyData?.strategy;
  const { data: _versionsData } = useQuery({
    queryKey: ['strategy-versions', strategy?.id],
    queryFn: () => api.getStrategyVersions(strategy.id),
    enabled: !!strategy?.id,
  });

  const { data: constitutionData } = useQuery({
    queryKey: ['constitution'],
    queryFn: api.getConstitution,
    enabled: !!strategyData?.has_strategy,
  });

  const { data: changelogData } = useQuery({
    queryKey: ['constitution-changelog'],
    queryFn: api.getConstitutionChangelog,
    enabled: !!strategyData?.has_strategy,
  });

  const { data: mirrorData } = useQuery({
    queryKey: ['behavioral-mirror'],
    queryFn: api.getMirror,
    enabled: !!strategyData?.has_strategy,
  });

  const { data: eventsData } = useQuery({
    queryKey: ['recent-events'],
    queryFn: () => api.getRecentEvents(20),
    enabled: !!strategyData?.has_strategy,
  });

  const { data: dashboardData } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.dashboard,
    enabled: !!strategyData?.has_strategy,
    refetchInterval: 30000,
  });

  const { data: learningProposals } = useQuery({ queryKey: ['learning-proposals'], queryFn: api.getLearningProposals, staleTime: 60000, enabled: !!strategyData?.has_strategy });
  const { data: learningOutcomes } = useQuery({ queryKey: ['learning-outcomes'], queryFn: () => api.getLearningOutcomes(), staleTime: 60000, enabled: !!strategyData?.has_strategy });
  const { data: learningDrift } = useQuery({ queryKey: ['learning-drift'], queryFn: api.getLearningDrift, staleTime: 60000, enabled: !!strategyData?.has_strategy });

  // Loading state
  if (isLoading) {
    return (
      <div className="stack" style={{ padding: '16px 20px' }}>
        <div style={{ display: 'flex', gap: 0, marginBottom: 12, border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden', width: 'fit-content' }}>
          <span style={{ padding: '7px 20px', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-ui)', fontWeight: 600, background: 'var(--accent-subtle)', color: 'var(--accent)', border: 'none' }}>Mirror</span>
          <span style={{ padding: '7px 20px', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-ui)', fontWeight: 500, background: 'var(--bg-secondary)', color: 'var(--text-secondary)', border: 'none' }}>Configure</span>
        </div>
        <div className="card" style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="muted">Loading...</div>
        </div>
      </div>
    );
  }

  // Mode A: No strategy yet
  if (!strategyData?.has_strategy) {
    return <OnboardingConversation />;
  }

  // Merge constitution data with strategy for richer signals
  void (constitutionData?.constitution || strategy);
  const recentRuns = dashboardData?.recent_runs || [];
  const icDecisions = recentRuns.filter((run: any) => run.agent === 'ic_review');
  const latestPortfolio = dashboardData?.latest_portfolio || {};
  const recentEvents = eventsData?.events || [];
  const proposals = learningProposals?.proposals || [];
  const changelog = changelogData?.changelog || changelogData?.versions || [];

  // Pipeline run info
  const pipelineRuns = recentRuns.filter((r: any) => r.agent === 'pipeline' || r.agent === 'screener' || r.agent === 'thesis' || r.agent === 'ic_review' || r.agent === 'portfolio');
  const lastPipelineRun = pipelineRuns[0];

  return (
    <div style={{ padding: '16px 20px' }}>
      <div style={{ marginBottom: 16 }}>
        <div className="section-label">DASHBOARD</div>
        <h1 className="page-title">Operations</h1>
        <p className="page-subtitle">Pipeline status, portfolio health, and what needs your attention</p>
      </div>

      <div className="stack">
        {/* System Health Strip */}
        <div style={{ display: 'flex', gap: 20, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)', marginBottom: 12, padding: '6px 0' }}>
          {learningProposals?.count > 0 && (
            <span style={{ color: 'var(--accent)' }}>{learningProposals.count} proposal{learningProposals.count > 1 ? 's' : ''} pending</span>
          )}
          {(learningOutcomes as any)?.outcomes?.length > 0 && (() => {
            const alphas = (learningOutcomes as any).outcomes.filter((o: any) => o.alpha_pct != null).map((o: any) => o.alpha_pct);
            const avg = alphas.length ? (alphas.reduce((a: number, b: number) => a + b, 0) / alphas.length) : 0;
            return <span style={{ color: avg >= 0 ? 'var(--positive)' : 'var(--negative)' }}>Alpha: {avg >= 0 ? '+' : ''}{avg.toFixed(1)}%</span>;
          })()}
          {learningDrift?.has_enough_data && (learningDrift?.signal_drift?.length > 0 || learningDrift?.anti_signal_violations?.length > 0) && (
            <span style={{ color: 'var(--accent)' }}>{(learningDrift.signal_drift?.length || 0) + (learningDrift.anti_signal_violations?.length || 0)} signals drifting</span>
          )}
        </div>

        {/* Portfolio KPIs */}
        <PortfolioKpis portfolio={latestPortfolio} />

        {/* Pipeline Status */}
        <div className="card">
          <div className="card-title">PIPELINE STATUS</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 2 }}>Last full run</div>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
                {lastPipelineRun ? new Date(lastPipelineRun.run_at ?? lastPipelineRun.started_at).toLocaleDateString() : 'Never'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 2 }}>Next scheduled</div>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>Sun 8:00 AM</div>
            </div>
            <div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 2 }}>Status</div>
              <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', color: 'var(--positive)' }}>Idle</div>
            </div>
          </div>
        </div>

        {/* Recent Agent Runs */}
        <div className="card">
          <div className="card-title">RECENT AGENT RUNS</div>
          {recentRuns.length > 0 ? (
            <div style={{ display: 'grid', gap: 6 }}>
              {recentRuns.slice(0, 8).map((run: any, i: number) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', borderBottom: i < Math.min(recentRuns.length, 8) - 1 ? '1px solid var(--border)' : undefined, fontSize: 'var(--text-xs)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-data)', color: 'var(--accent)', minWidth: 110, flexShrink: 0 }}>{run.agent}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{run.ticker || run.message || ''}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: run.status === 'completed' ? 'var(--positive)' : run.status === 'failed' ? 'var(--negative)' : 'var(--text-muted)' }}>
                      {run.status || 'completed'}
                    </span>
                    <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                      {(run.run_at ?? run.started_at) ? new Date(run.run_at ?? run.started_at).toLocaleDateString() : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
              No pipeline runs yet. Run the pipeline to see activity here.
            </div>
          )}
        </div>

        {/* Upcoming Schedules */}
        <div className="card">
          <div className="card-title">SCHEDULED RUNS</div>
          <table style={{ width: '100%', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Agent</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Frequency</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Next Run</th>
                <th style={{ padding: '4px 0', fontWeight: 500 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {[
                { agent: 'Screener', freq: 'Weekly', next: 'Sun 8:00 AM', status: 'active' },
                { agent: 'Portfolio', freq: 'Daily', next: 'Tomorrow 7:00 AM', status: 'active' },
                { agent: 'Outcome Checker', freq: 'Daily', next: 'Tomorrow 6:00 AM', status: 'active' },
                { agent: 'Library Sync', freq: 'Weekly', next: 'Mon 6:00 AM', status: 'active' },
                { agent: 'Full Pipeline', freq: 'Weekly', next: '\u2014', status: 'paused' },
              ].map((s, i, arr) => (
                <tr key={i} style={{ borderBottom: i < arr.length - 1 ? '1px solid var(--border)' : 'none' }}>
                  <td style={{ padding: '5px 0', fontWeight: 500 }}>{s.agent}</td>
                  <td style={{ padding: '5px 0' }}>{s.freq}</td>
                  <td style={{ padding: '5px 0', color: s.status === 'active' ? 'var(--accent)' : 'var(--text-muted)' }}>{s.next}</td>
                  <td style={{ padding: '5px 0', color: s.status === 'active' ? 'var(--positive)' : 'var(--warning)' }}>
                    {s.status === 'active' ? 'Active' : 'Paused'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 8, textAlign: 'right' }}>
            <Link to="/settings" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', textDecoration: 'none', fontFamily: 'var(--font-data)' }}>
              Manage schedules →
            </Link>
          </div>
        </div>

        {/* Your Attention + Proposals */}
        <AttentionAndLearning icDecisions={icDecisions} recentEvents={recentEvents} proposals={proposals} />

        {/* Said vs Did — behavioral scorecard */}
        <SaidVsDid mirrorData={mirrorData} icDecisions={icDecisions} drift={learningDrift} />

        {/* Approval Profile */}
        <ApprovalProfile icDecisions={icDecisions} />

        {/* Constitution Evolution */}
        <ConstitutionEvolution changelog={changelog} />
      </div>
    </div>
  );
}

export default Mirror;
