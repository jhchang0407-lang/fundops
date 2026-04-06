import { useState, useRef, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/PageHeader';
import { KpiCard, KpiRow } from '../components/KpiCard';

// ── Types ──────────────────────────────────────────────────────────────

interface ScenarioMetric {
  label: string;
  value: string;
  color?: 'positive' | 'negative' | 'warning' | 'accent' | 'muted';
}

interface Scenario {
  label: string;
  metrics: ScenarioMetric[];
}

interface AiMessage {
  role: 'user' | 'ai';
  text: string;
}

interface ActionItem {
  ticker: string;
  company: string;
  action: 'TRIM' | 'EXIT' | 'ADD ON WEAKNESS' | 'ADD' | 'HOLD' | 'REUNDERWRITE';
  weight_current: number;
  weight_target: number;
  reason: string;
  health_score: number;
  health_trend?: 'up' | 'down' | 'flat';
  pnl_pct: number;
  type: string;
  trigger_price?: number;
  thesis_drift?: string;
  expected_return?: number;
  key_risks?: string[];
  scenarios: [Scenario, Scenario];
  ai_messages?: AiMessage[];
  ai_open?: boolean;
}

interface NewPosition {
  ticker: string;
  position_type: string;
  recommended_weight: number;
  entry_strategy: string;
  priority: string;
  reason: string;
  sector?: string;
  expected_return?: number;
  bear_return?: number | null;
}

interface SizingAlert {
  severity: 'danger' | 'warning';
  title: string;
  description: string;
}

interface HoldPosition {
  ticker: string;
  weight: number;
  health: number;
  target_weight: number;
  status: string;
}

interface AllocatorData {
  last_run?: string;
  actions_required: ActionItem[];
  monitoring: ActionItem[];
  no_action: HoldPosition[];
  new_positions: NewPosition[];
  alerts: SizingAlert[];
  kpis: {
    actions_pending: number;
    urgent_count: number;
    monitor_count: number;
    concentration: number;
    concentration_ticker?: string;
    concentration_limit?: number;
    cash_available: number;
    cash_pct: number;
    avg_expected_return: number;
    new_opportunities?: number;
  };
}

// ── Helpers ────────────────────────────────────────────────────────────

function colorVar(c?: string) {
  if (!c) return undefined;
  const map: Record<string, string> = {
    positive: 'var(--positive)',
    negative: 'var(--negative)',
    warning: 'var(--warning)',
    accent: 'var(--accent)',
    muted: 'var(--text-muted)',
  };
  return map[c];
}

function healthColor(score: number) {
  if (score >= 70) return 'var(--positive)';
  if (score >= 40) return 'var(--warning)';
  return 'var(--negative)';
}

function badgeClass(action: string) {
  switch (action) {
    case 'TRIM': return 'alloc-badge alloc-badge-trim';
    case 'EXIT': return 'alloc-badge alloc-badge-exit';
    case 'ADD ON WEAKNESS':
    case 'ADD': return 'alloc-badge alloc-badge-add';
    case 'HOLD': return 'alloc-badge alloc-badge-hold';
    default: return 'alloc-badge alloc-badge-monitor';
  }
}

function doneLabel(action: string) {
  switch (action) {
    case 'TRIM': return 'Mark as Done (trimmed)';
    case 'EXIT': return 'Mark as Done (exited)';
    case 'ADD ON WEAKNESS':
    case 'ADD': return 'Mark as Done (added)';
    default: return 'Mark as Done';
  }
}

// ── Sub-components ─────────────────────────────────────────────────────

function SizingAlert({ alert }: { alert: SizingAlert }) {
  const isDanger = alert.severity === 'danger';
  return (
    <div
      className="alloc-sizing-alert"
      style={{ borderLeftColor: isDanger ? 'var(--negative)' : 'var(--warning)' }}
    >
      <span className="alloc-sizing-icon" style={{ color: isDanger ? 'var(--negative)' : 'var(--warning)' }}>
        {isDanger ? '\u26A0' : '\u25CF'}
      </span>
      <div style={{ flex: 1 }}>
        <div className="alloc-sizing-title">{alert.title}</div>
        <div className="alloc-sizing-desc">{alert.description}</div>
      </div>
    </div>
  );
}

function SectionHeader({
  title,
  count,
  color,
  collapsible,
  collapsed,
  onToggle,
}: {
  title: string;
  count: number;
  color?: string;
  collapsible?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  return (
    <div
      className="alloc-section-header"
      style={{ cursor: collapsible ? 'pointer' : undefined }}
      onClick={collapsible ? onToggle : undefined}
    >
      <span
        className="alloc-section-title"
        style={color ? { color } : undefined}
      >
        {title}
      </span>
      <span
        className="alloc-section-count"
        style={
          color
            ? { background: `color-mix(in srgb, ${color} 15%, transparent)`, color }
            : undefined
        }
      >
        {count}
      </span>
      {collapsible && (
        <span
          className="alloc-collapse-arrow"
          style={{ transform: collapsed ? undefined : 'rotate(90deg)' }}
        >
          &#9654;
        </span>
      )}
    </div>
  );
}

function ScenarioComparison({ scenarios }: { scenarios: [Scenario, Scenario] | Scenario[] }) {
  if (!scenarios || !Array.isArray(scenarios) || scenarios.length === 0) return null;
  return (
    <div className="alloc-scenario-row">
      {scenarios.map((s, i) => (
        <div key={i} className="alloc-scenario-card">
          <div className="alloc-scenario-label">{s.label}</div>
          <div className="alloc-scenario-metrics">
            {(s.metrics || []).map((m, j) => (
              <div key={j} className="alloc-scenario-metric">
                <span className="alloc-scenario-metric-label">{m.label}</span>
                <span
                  className="alloc-scenario-metric-value"
                  style={m.color ? { color: colorVar(m.color) } : undefined}
                >
                  {m.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ThesisStatusBar({
  health_score,
  health_trend,
  pnl_pct,
  type,
  trigger_price,
}: {
  health_score: number;
  health_trend?: string;
  pnl_pct: number;
  type: string;
  trigger_price?: number;
}) {
  const hColor = healthColor(health_score);
  const pnlColor = pnl_pct >= 0 ? 'var(--positive)' : 'var(--negative)';
  return (
    <div className="alloc-thesis-status">
      <span className="alloc-health-dot" style={{ background: hColor }} />
      <span style={{ color: 'var(--text-muted)' }}>Thesis health</span>
      <span style={{ fontFamily: 'var(--font-data)', color: hColor }}>{health_score}/100</span>
      {health_trend === 'down' && (
        <span style={{ color: 'var(--negative)', fontSize: 10 }}>{'\u2193'}</span>
      )}
      <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>P&L</span>
      <span style={{ fontFamily: 'var(--font-data)', color: pnlColor }}>
        {pnl_pct >= 0 ? '+' : ''}{pnl_pct}%
      </span>
      {trigger_price != null ? (
        <>
          <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>Trigger</span>
          <span style={{ fontFamily: 'var(--font-data)' }}>${trigger_price} (-10%)</span>
        </>
      ) : (
        <>
          <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>Type</span>
          <span style={{ fontFamily: 'var(--font-data)' }}>{type}</span>
        </>
      )}
    </div>
  );
}

function AiDiscussPanel({
  ticker,
  action,
  messages: initialMessages,
  defaultOpen,
}: {
  ticker: string;
  action: ActionItem;
  messages?: AiMessage[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  const [messages, setMessages] = useState<AiMessage[]>(initialMessages || []);
  const [input, setInput] = useState('');
  const messagesRef = useRef<HTMLDivElement>(null);

  const discuss = useMutation({
    mutationFn: (msg: string) => api.discussPosition(
      ticker,
      msg,
      messages
        .filter(m => m.role !== 'system' as any)
        .map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text })),
      {
        action: action.action,
        weight: action.weight_current,
        weight_target: action.weight_target,
        pnl_pct: action.pnl_pct,
        reason: action.reason,
        type: action.type,
        health_score: action.health_score,
      }
    ),
    onSuccess: (data) => {
      setMessages(prev => [...prev, { role: 'ai', text: data.message }]);
      setTimeout(() => {
        messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' });
      }, 50);
    },
    onError: (err: Error) => {
      setMessages(prev => [...prev, { role: 'ai', text: `Error: ${err.message}` }]);
    },
  });

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || discuss.isPending) return;
    setMessages(prev => [...prev, { role: 'user', text: trimmed }]);
    setInput('');
    discuss.mutate(trimmed);
  }, [input, discuss]);

  if (!open) {
    return (
      <div className="alloc-action-buttons" style={{ marginTop: 0, marginBottom: 0 }}>
        <button className="alloc-btn-discuss" onClick={() => setOpen(true)}>
          Discuss with AI
        </button>
      </div>
    );
  }

  return (
    <div className="alloc-ai-discuss">
      <div className="alloc-ai-discuss-header">
        <span className="alloc-ai-discuss-title">{'\u25C8'} DISCUSS WITH AI</span>
        <span className="alloc-ai-discuss-ctx">
          Full context: position, thesis, health, scenarios, portfolio policy
        </span>
      </div>
      {messages.length > 0 && (
        <div className="alloc-ai-messages" ref={messagesRef}>
          {messages.map((m, i) => (
            <div key={i} className="alloc-ai-msg">
              <div className={`alloc-ai-msg-label ${m.role === 'ai' ? 'alloc-ai-msg-label-ai' : 'alloc-ai-msg-label-user'}`}>
                {m.role === 'ai' ? 'FUNDOPS' : 'YOU'}
              </div>
              {m.role === 'user' ? (
                <div className="alloc-ai-msg-text-user">{m.text}</div>
              ) : (
                <div
                  className="alloc-ai-msg-text"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(m.text) }}
                />
              )}
            </div>
          ))}
        </div>
      )}
      {discuss.isPending && (
        <div className="alloc-ai-msg" style={{ padding: '8px 12px' }}>
          <div className="alloc-ai-msg-label alloc-ai-msg-label-ai">FUNDOPS</div>
          <div className="alloc-ai-msg-text" style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Thinking...
          </div>
        </div>
      )}
      <div className="alloc-ai-input-row">
        <input
          className="alloc-ai-input"
          placeholder={`Ask about timing, tax implications, alternative sizing, what-if scenarios...`}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleSend(); }}
          disabled={discuss.isPending}
        />
        <button
          className="btn btn-accent"
          style={{ padding: '6px 12px', fontSize: 'var(--text-xs)' }}
          onClick={handleSend}
          disabled={discuss.isPending}
        >
          {discuss.isPending ? '...' : 'Ask'}
        </button>
      </div>
    </div>
  );
}

function ActionCard({
  item,
  variant,
  onDone,
}: {
  item: ActionItem;
  variant: 'urgent' | 'monitor';
  onDone?: (ticker: string, action: string) => void;
}) {
  const borderClass = variant === 'urgent' ? 'alloc-action-card-urgent' : 'alloc-action-card-monitor';

  return (
    <div className={`alloc-action-card ${borderClass}`} style={{ borderLeft: (item as any).sell_discipline_triggered ? '3px solid var(--accent)' : undefined }}>
      {/* Header */}
      <div className="alloc-action-header">
        <div className="alloc-action-ticker-row">
          <Link
            to={`/ticker/${item.ticker}`}
            style={{
              fontFamily: 'var(--font-data)',
              fontSize: 'var(--text-lg)',
              fontWeight: 600,
              color: 'var(--accent)',
              letterSpacing: '0.05em',
              textDecoration: 'none',
            }}
          >
            {item.ticker}
          </Link>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            {item.company}
          </span>
          <span className={badgeClass(item.action)}>{item.action}</span>
          {(item as any).sell_discipline_triggered && (
            <span className="sell-discipline-badge">SELL DISCIPLINE</span>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          Weight:{' '}
          <span style={{ color: item.weight_current > (item.weight_target || 0) ? 'var(--negative)' : undefined }}>
            {item.weight_current}%
          </span>
          {' \u2192 Target: '}
          <span>{item.weight_target}%</span>
        </div>
      </div>

      {/* Why */}
      <div className="alloc-action-why">{item.reason}</div>
      {(item as any).detail && (item as any).detail !== item.reason && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginTop: 4 }}>
          {(item as any).detail}
        </div>
      )}
      {(item as any).sell_rule && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', fontFamily: 'var(--font-data)', marginTop: 4 }}>
          Rule: {(item as any).sell_rule}
        </div>
      )}
      {item.thesis_drift && item.thesis_drift !== 'none' && (
        <div style={{
          fontSize: 'var(--text-xs)', marginTop: 4, padding: '3px 8px',
          background: item.thesis_drift === 'significant' ? 'rgba(255,59,48,0.1)' : 'rgba(245,166,35,0.1)',
          color: item.thesis_drift === 'significant' ? 'var(--negative)' : 'var(--warning)',
          borderRadius: 4, display: 'inline-block',
        }}>
          Thesis drift: {item.thesis_drift}
        </div>
      )}
      {item.key_risks && item.key_risks.length > 0 && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
          Risks: {item.key_risks.join(' · ')}
        </div>
      )}

      {/* Thesis status bar */}
      <ThesisStatusBar
        health_score={item.health_score}
        health_trend={item.health_trend}
        pnl_pct={item.pnl_pct}
        type={item.type}
        trigger_price={item.trigger_price}
      />

      {/* Scenario comparison */}
      <ScenarioComparison scenarios={item.scenarios} />

      {/* AI discuss panel — for RCAT show open with conversation, others collapsed */}
      <AiDiscussPanel
        ticker={item.ticker}
        action={item}
        messages={item.ai_messages}
        defaultOpen={item.ai_open}
      />

      {/* Action buttons */}
      <div className="alloc-action-buttons">
        <button className="btn btn-ghost" style={{ fontSize: 'var(--text-xs)' }}>Dismiss</button>
        {item.action === 'ADD ON WEAKNESS' && (
          <button className="btn btn-ghost" style={{ fontSize: 'var(--text-xs)' }}>
            Set alert at ${item.trigger_price}
          </button>
        )}
        <button
          className="btn btn-danger"
          style={{ fontSize: 'var(--text-xs)' }}
          onClick={() => onDone?.(item.ticker, item.action)}
        >
          {doneLabel(item.action)}
        </button>
      </div>
    </div>
  );
}

function HoldCard({ pos }: { pos: HoldPosition }) {
  const weightColor = pos.health >= 70 ? 'var(--positive)' : 'var(--text-secondary)';
  return (
    <div className="alloc-action-card alloc-action-card-hold" style={{ padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link to={`/ticker/${pos.ticker}`} className="ticker">{pos.ticker}</Link>
          <span className="alloc-badge alloc-badge-hold">HOLD</span>
        </div>
        <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: weightColor }}>
          {pos.weight}%
        </span>
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
        Health {pos.health} . Target {pos.target_weight}% . {pos.status}
      </div>
    </div>
  );
}

function NewPositionCard({ opp }: { opp: NewPosition }) {
  const priorityColor = opp.priority === 'high' ? 'var(--positive)' : opp.priority === 'medium' ? 'var(--accent)' : 'var(--text-muted)';
  return (
    <div className="alloc-action-card" style={{ borderLeftColor: 'var(--accent)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link to={`/ticker/${opp.ticker}`} className="ticker" style={{ fontSize: 'var(--text-base)' }}>{opp.ticker}</Link>
          <span style={{
            fontSize: 10, padding: '1px 6px', borderRadius: 3,
            background: 'rgba(245, 166, 35, 0.15)', color: 'var(--accent)',
            textTransform: 'uppercase', fontWeight: 600,
          }}>
            {opp.position_type}
          </span>
          <span style={{
            fontSize: 10, padding: '1px 6px', borderRadius: 3,
            background: `color-mix(in srgb, ${priorityColor} 15%, transparent)`, color: priorityColor,
            textTransform: 'uppercase', fontWeight: 600,
          }}>
            {opp.priority} priority
          </span>
        </div>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
          <span style={{ color: 'var(--text-muted)' }}>Target: </span>
          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{opp.recommended_weight}%</span>
        </div>
      </div>

      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
        {opp.reason}
      </div>

      <div className="alloc-scenario-row">
        <div className="alloc-scenario-card">
          <div className="alloc-scenario-label">RETURN PROFILE</div>
          <div className="alloc-scenario-metrics">
            {opp.expected_return != null && (
              <div className="alloc-scenario-metric">
                <span className="alloc-scenario-metric-label">Expected</span>
                <span className="alloc-scenario-metric-value" style={{ color: (opp.expected_return ?? 0) >= 15 ? 'var(--positive)' : 'var(--warning)' }}>
                  {opp.expected_return}%
                </span>
              </div>
            )}
            {opp.bear_return != null && (
              <div className="alloc-scenario-metric">
                <span className="alloc-scenario-metric-label">Bear</span>
                <span className="alloc-scenario-metric-value" style={{ color: (opp.bear_return ?? 0) >= 10 ? 'var(--positive)' : 'var(--negative)' }}>
                  {opp.bear_return}%
                </span>
              </div>
            )}
          </div>
        </div>
        <div className="alloc-scenario-card">
          <div className="alloc-scenario-label">SIZING</div>
          <div className="alloc-scenario-metrics">
            <div className="alloc-scenario-metric">
              <span className="alloc-scenario-metric-label">Type</span>
              <span className="alloc-scenario-metric-value">{opp.position_type}</span>
            </div>
            <div className="alloc-scenario-metric">
              <span className="alloc-scenario-metric-label">Entry</span>
              <span className="alloc-scenario-metric-value">{opp.entry_strategy === 'scale_in' ? 'Scale in' : 'Full position'}</span>
            </div>
            {opp.sector && (
              <div className="alloc-scenario-metric">
                <span className="alloc-scenario-metric-label">Sector</span>
                <span className="alloc-scenario-metric-value">{opp.sector}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CompactHoldCard({ pos }: { pos: HoldPosition }) {
  const weightColor = pos.health >= 70 ? 'var(--positive)' : 'var(--text-secondary)';
  return (
    <div className="alloc-action-card alloc-action-card-hold" style={{ padding: '8px 10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link to={`/ticker/${pos.ticker}`} className="ticker">{pos.ticker}</Link>
        <span style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: weightColor }}>
          {pos.weight}%
        </span>
      </div>
    </div>
  );
}

// ── Policy Modal ───────────────────────────────────────────────────────

function PolicyModal({ open, onClose, data }: { open: boolean; onClose: () => void; data?: AllocatorData | null }) {
  if (!open) return null;

  // Use constitution-derived values from allocator data if available
  const policy = (data as any)?.policy || null;
  const maxPosition = policy?.max_position_pct ?? 15;
  const concentrationLimit = policy?.concentration_limit_pct ?? 20;
  const minPosition = policy?.min_position_pct ?? 2;
  const hasConstitution = !!policy;

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
          zIndex: 1000, backdropFilter: 'blur(2px)',
        }}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        background: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 24, zIndex: 1001,
        width: 480, maxHeight: '80vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 600 }}>
            Allocation Policy
          </div>
          <button onClick={onClose} className="btn btn-ghost" style={{ fontSize: 14, padding: '2px 8px' }}>x</button>
        </div>

        {!hasConstitution && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 12, fontStyle: 'italic' }}>
            Using default values. <Link to="/" style={{ color: 'var(--accent)' }}>Configure in strategy conversation</Link> to customize.
          </div>
        )}

        <div style={{ fontSize: 'var(--text-sm)', display: 'grid', gap: 14 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>POSITION SIZING</div>
            <div style={{ display: 'grid', gap: 4, fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Max single position</span><span>{maxPosition}%</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Concentration limit</span><span>{concentrationLimit}%</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Min position size</span><span>{minPosition}%</span></div>
            </div>
          </div>

          <div style={{ height: 1, background: 'var(--border)' }} />

          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>POSITION TYPES</div>
            <div style={{ display: 'grid', gap: 4, fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
              {policy?.position_types ? (
                policy.position_types.map((pt: any, i: number) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{pt.type || pt.label}</span>
                    <span>{pt.min}–{pt.max}%</span>
                  </div>
                ))
              ) : (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Core positions</span><span>5-10%</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Tactical positions</span><span>2-5%</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Legacy</span><span>Exit on thesis break</span></div>
                </>
              )}
            </div>
          </div>

          <div style={{ height: 1, background: 'var(--border)' }} />

          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>ALERTS &amp; THRESHOLDS</div>
            <div style={{ display: 'grid', gap: 4, fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Concentration breach</span><span style={{ color: 'var(--negative)' }}>{policy?.concentration_breach || '10% (tactical), 15% (core)'}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Drawdown alert</span><span style={{ color: 'var(--negative)' }}>{policy?.drawdown_threshold_pct ? `-${policy.drawdown_threshold_pct}%` : '-15%'}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'var(--text-secondary)' }}>Thesis health breach</span><span style={{ color: 'var(--warning)' }}>&lt; {policy?.health_breach ?? 25}/100</span></div>
            </div>
          </div>

          <div style={{ height: 1, background: 'var(--border)' }} />

          <div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: 4 }}>ACTION TRIGGERS</div>
            <div style={{ display: 'grid', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              {policy?.sell_discipline ? (
                Object.entries(policy.sell_discipline).map(([key, value]: [string, any]) => (
                  <div key={key}>{String(key).toUpperCase()} — {String(value)}</div>
                ))
              ) : (
                <>
                  <div>TRIM — when position exceeds max weight or thesis health declines</div>
                  <div>EXIT — on thesis break (revenue growth assumption violated 2+ quarters)</div>
                  <div>ADD — when high-conviction name trades below target weight + trigger price hit</div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Main Component ─────────────────────────────────────────────────────

export function Allocator() {
  const queryClient = useQueryClient();
  const [policyOpen, setPolicyOpen] = useState(false);
  const { data: rawData } = useQuery({
    queryKey: ['allocator'],
    queryFn: api.allocatorRecs,
  });
  const { data: portfolioData } = useQuery({
    queryKey: ['portfolio'],
    queryFn: api.portfolioStatus,
    staleTime: 60000,
  });
  const portfolioHoldings = (() => {
    const h = portfolioData?.holdings;
    if (Array.isArray(h)) return h;
    if (typeof h === 'string') try { return JSON.parse(h); } catch { return []; }
    return [];
  })();

  const runMutation = useMutation({
    mutationFn: api.runAllocator,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['allocator'] }),
  });

  const doneMutation = useMutation({
    mutationFn: ({ ticker, action }: { ticker: string; action: string }) =>
      api.recordAllocatorAction(ticker, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['allocator'] }),
  });

  const handleDone = (ticker: string, action: string) => {
    doneMutation.mutate({ ticker, action });
  };

  // Use real API data only — never fall back to sample data (would be misleading)
  const raw = rawData as any;
  // Normalize backend field names to frontend expectations
  const normalizeItem = (item: any): any => ({
    ...item,
    weight_current: item.weight_current ?? item.current_weight ?? 0,
    weight_target: item.weight_target ?? item.target_weight ?? 0,
    company: item.company ?? '',
    health_score: item.health_score ?? item.thesis_health ?? 0,
    health_trend: item.health_trend ?? (item.thesis_drift === 'significant' ? 'down' : item.thesis_drift === 'minor' ? 'down' : 'flat'),
    thesis_drift: item.thesis_drift,
    expected_return: item.expected_return ?? 0,
    key_risks: item.key_risks ?? [],
    scenarios: item.scenarios ?? [
      { label: 'Bear Case', metrics: [
        { label: 'Return', value: `${item.pnl_pct ?? 0}%`, color: (item.pnl_pct ?? 0) < 0 ? 'negative' : 'positive' },
      ] },
      { label: 'Base Case', metrics: [
        { label: 'Expected Return', value: `${item.expected_return ?? 0}%`, color: (item.expected_return ?? 0) >= 15 ? 'positive' : 'warning' },
        { label: 'Target', value: `${item.weight_target ?? item.target_weight ?? 0}%` },
      ] },
    ],
    ai_messages: item.ai_messages ?? [],
    ai_open: item.ai_open ?? false,
  });
  const data: AllocatorData | null = (raw && Array.isArray(raw.actions_required)) ? {
    ...raw,
    actions_required: (raw.actions_required || []).map(normalizeItem),
    monitoring: (raw.monitoring || []).map(normalizeItem),
    no_action: (raw.no_action || []).map((p: any) => ({
      ...p,
      weight: p.weight ?? p.current_weight ?? 0,
      health: p.health ?? p.health_score ?? p.thesis_health ?? 0,
      target_weight: p.target_weight ?? 0,
      status: p.status ?? 'ok',
    })),
    new_positions: (raw.new_positions || []),
    alerts: (raw.alerts || []).map((a: any) => ({ severity: a.severity ?? a.type ?? 'warning', title: a.title ?? '', description: a.description ?? a.detail ?? '' })),
    kpis: raw.kpis ?? { actions_pending: 0, urgent_count: 0, monitor_count: 0, concentration: 0, cash_available: 0, cash_pct: 0, avg_expected_return: 0 },
  } : null;

  const hasActions = data ? (data.actions_required.length > 0 || data.monitoring.length > 0) : false;
  const hasPortfolio = data ? (data.no_action.length > 0 || hasActions) : false;

  // Empty state — no allocator run yet, or empty portfolio
  if (!hasPortfolio || !data) {
    return (
      <>
        <PolicyModal open={policyOpen} onClose={() => setPolicyOpen(false)} data={data} />
        <EmptyState
          onViewPolicy={() => setPolicyOpen(true)}
          hasPositions={portfolioHoldings.length > 0}
          onRun={() => runMutation.mutate()}
          running={runMutation.isPending}
        />
      </>
    );
  }

  // Clean state (no actions)
  if (!hasActions) {
    return (
      <>
        <PolicyModal open={policyOpen} onClose={() => setPolicyOpen(false)} data={data} />
        <CleanState
          data={data}
          onRun={() => runMutation.mutate()}
          running={runMutation.isPending}
          onViewPolicy={() => setPolicyOpen(true)}
        />
      </>
    );
  }

  // Default: with actions
  return (
    <>
      <PolicyModal open={policyOpen} onClose={() => setPolicyOpen(false)} data={data} />
      <WithActionsState
        data={data}
        onRun={() => runMutation.mutate()}
        running={runMutation.isPending}
        onViewPolicy={() => setPolicyOpen(true)}
        onDone={handleDone}
      />
    </>
  );
}

// ── State 1: With Actions ──────────────────────────────────────────────

function WithActionsState({
  data,
  onRun,
  running,
  onViewPolicy,
  onDone,
}: {
  data: AllocatorData;
  onRun: () => void;
  running: boolean;
  onViewPolicy: () => void;
  onDone: (ticker: string, action: string) => void;
}) {
  const [noActionCollapsed, setNoActionCollapsed] = useState(true);
  const k = data.kpis;

  const subtitle = [
    data.last_run && `Last run ${data.last_run}`,
    `${data.actions_required.length} actions required`,
    `${data.monitoring.length} monitoring`,
    `${data.no_action.length} no action`,
  ].filter(Boolean).join(' \u00B7 ');

  return (
    <div className="stack">
      <PageHeader
        sectionLabel="ALLOCATOR"
        title="Position Recommendations"
        subtitle={subtitle}
        actions={
          <>
            <button className="btn btn-ghost" onClick={onViewPolicy}>View Policy</button>
            <button
              className="btn btn-accent"
              onClick={onRun}
              disabled={running}
            >
              {running ? 'Running...' : 'Run Allocator'}
            </button>
          </>
        }
      />

      {/* KPIs */}
      <KpiRow columns={4}>
        <KpiCard
          label="ACTIONS PENDING"
          value={k.actions_pending}
          valueColor="var(--negative)"
          detail={<span className="kpi-sub">{k.urgent_count} urgent, {k.monitor_count} monitor</span>}
        />
        <KpiCard
          label="CONCENTRATION"
          value={`${k.concentration}%`}
          valueColor="var(--negative)"
          detail={<span className="kpi-sub">{k.concentration_ticker} exceeds {k.concentration_limit}% limit</span>}
        />
        <KpiCard
          label="CASH AVAILABLE"
          value={`$${Math.round(k.cash_available / 1000)}K`}
          detail={<span className="kpi-sub">{k.cash_pct}% of portfolio</span>}
        />
        <KpiCard
          label="AVG EXPECTED RETURN"
          value={`${k.avg_expected_return}%`}
          valueColor="var(--positive)"
          detail={<span className="kpi-sub">portfolio-weighted</span>}
        />
      </KpiRow>

      {/* Sizing alerts */}
      {data.alerts.map((a, i) => (
        <SizingAlert key={i} alert={a} />
      ))}

      {/* Action required section */}
      <SectionHeader
        title="ACTION REQUIRED"
        count={data.actions_required.length}
        color="var(--negative)"
      />
      {data.actions_required.map((item, i) => (
        <ActionCard key={i} item={item} variant="urgent" onDone={onDone} />
      ))}

      {/* Monitoring section */}
      {data.monitoring.length > 0 && (
        <>
          <SectionHeader
            title="MONITORING"
            count={data.monitoring.length}
            color="var(--warning)"
          />
          {data.monitoring.map((item, i) => (
            <ActionCard key={i} item={item} variant="monitor" onDone={onDone} />
          ))}
        </>
      )}

      {/* New opportunities section */}
      {data.new_positions.length > 0 && (
        <>
          <SectionHeader
            title="NEW OPPORTUNITIES"
            count={data.new_positions.length}
            color="var(--accent)"
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {data.new_positions.map((opp, i) => (
              <NewPositionCard key={i} opp={opp} />
            ))}
          </div>
        </>
      )}

      {/* No action section (collapsed by default) */}
      {data.no_action.length > 0 && (
        <>
          <SectionHeader
            title="NO ACTION"
            count={data.no_action.length}
            collapsible
            collapsed={noActionCollapsed}
            onToggle={() => setNoActionCollapsed(c => !c)}
          />
          {!noActionCollapsed && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {data.no_action.map((pos, i) => (
                <HoldCard key={i} pos={pos} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── State 2: Clean (No Actions) ────────────────────────────────────────

function CleanState({
  data,
  onRun,
  running,
  onViewPolicy,
}: {
  data: AllocatorData;
  onRun: () => void;
  running: boolean;
  onViewPolicy: () => void;
}) {
  const k = data.kpis;

  return (
    <div className="stack">
      <PageHeader
        sectionLabel="ALLOCATOR"
        title="Position Recommendations"
        subtitle={`Last run ${data.last_run || 'never'} \u00B7 No actions required`}
        actions={
          <>
            <button className="btn btn-ghost" onClick={onViewPolicy}>View Policy</button>
            <button className="btn btn-accent" onClick={onRun} disabled={running}>
              {running ? 'Running...' : 'Run Allocator'}
            </button>
          </>
        }
      />

      <KpiRow columns={4}>
        <KpiCard
          label="ACTIONS PENDING"
          value={0}
          valueColor="var(--positive)"
          detail={<span className="kpi-sub">all positions in spec</span>}
        />
        <KpiCard
          label="MAX CONCENTRATION"
          value={`${k.concentration}%`}
          detail={<span className="kpi-sub">{k.concentration_ticker} (limit: {k.concentration_limit}%)</span>}
        />
        <KpiCard
          label="CASH"
          value={`$${Math.round(k.cash_available / 1000)}K`}
          detail={<span className="kpi-sub">{k.cash_pct}% of portfolio</span>}
        />
        <KpiCard
          label="AVG EXPECTED RETURN"
          value={`${k.avg_expected_return}%`}
          valueColor="var(--positive)"
          detail={<span className="kpi-sub">portfolio-weighted</span>}
        />
      </KpiRow>

      {/* Balanced message */}
      <div className="alloc-balanced-card">
        <div style={{ color: 'var(--positive)', fontSize: 20, marginBottom: 8 }}>{'\u2713'}</div>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, marginBottom: 4 }}>
          Portfolio is balanced
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          All positions are within policy limits. No concentration breaches, no thesis alerts, no recommended actions.
        </div>
      </div>

      {/* New opportunities */}
      {data.new_positions.length > 0 && (
        <>
          <SectionHeader
            title="NEW OPPORTUNITIES"
            count={data.new_positions.length}
            color="var(--accent)"
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {data.new_positions.map((opp, i) => (
              <NewPositionCard key={i} opp={opp} />
            ))}
          </div>
        </>
      )}

      {/* All positions grid */}
      <SectionHeader title="ALL POSITIONS" count={data.no_action.length} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
        {data.no_action.map((pos, i) => (
          <CompactHoldCard key={i} pos={pos} />
        ))}
      </div>
    </div>
  );
}

// ── State 3: Empty ─────────────────────────────────────────────────────

function EmptyState({ onViewPolicy, hasPositions, onRun, running }: {
  onViewPolicy: () => void;
  hasPositions?: boolean;
  onRun?: () => void;
  running?: boolean;
}) {
  return (
    <div className="stack">
      <PageHeader
        sectionLabel="ALLOCATOR"
        title="Position Recommendations"
        actions={hasPositions ? (
          <button className="btn btn-accent" onClick={onRun} disabled={running}>
            {running ? 'Running...' : 'Run Allocator'}
          </button>
        ) : undefined}
      />

      <div className="alloc-empty-card">
        <div style={{ fontSize: 'var(--text-lg)', fontWeight: 500, marginBottom: 6 }}>
          {hasPositions ? 'Allocator not run yet' : 'No portfolio to analyze'}
        </div>
        <div style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--text-secondary)',
          marginBottom: 16,
          maxWidth: 400,
          marginLeft: 'auto',
          marginRight: 'auto',
        }}>
          {hasPositions
            ? 'You have positions. Click "Run Allocator" to generate sizing recommendations, concentration alerts, and action items.'
            : 'The allocator needs a portfolio to generate sizing recommendations. Add your positions first, then run the allocator to get action items.'}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          {hasPositions ? (
            <button className="btn btn-accent" onClick={onRun} disabled={running}>
              {running ? 'Running...' : 'Run Allocator'}
            </button>
          ) : (
            <Link to="/portfolio" className="btn btn-accent" style={{ textDecoration: 'none' }}>
              Go to Portfolio
            </Link>
          )}
          <button className="btn btn-ghost" onClick={onViewPolicy}>View Policy</button>
        </div>
      </div>
    </div>
  );
}
