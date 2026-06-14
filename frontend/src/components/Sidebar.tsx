import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getBriefing, getHealth, getStrategy } from '../api/client';

type NavItem = { to: string; label: string; end?: boolean; badge?: number };

function linkClass({ isActive }: { isActive: boolean }) {
  return `side-link${isActive ? ' active' : ''}`;
}

const PROVIDER_LABELS: Record<string, string> = {
  agent_cli: 'claude · headless',
  openai: 'OpenAI API',
  stub: 'offline stub',
};

export function Sidebar({ onOpenWiring, onOpenPalette }: {
  onOpenWiring: () => void;
  onOpenPalette: () => void;
}) {
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth, staleTime: 60_000 });
  const { data: strategy } = useQuery({ queryKey: ['strategy'], queryFn: getStrategy });
  const { data: briefing } = useQuery({ queryKey: ['briefing'], queryFn: getBriefing, retry: 1 });

  const inboxBadge =
    (briefing?.learning_ready ?? 0) +
    (briefing?.pending_proposal ? 1 : 0) +
    (briefing?.health.broken.length ?? 0);
  const runsBadge = briefing?.running.length ?? 0;

  const nav: NavItem[] = [
    { to: '/', label: 'Home', end: true },
    { to: '/inbox', label: 'Inbox', badge: inboxBadge },
    { to: '/runs', label: 'Runs', badge: runsBadge },
    { to: '/markets', label: 'Markets' },
    { to: '/portfolio', label: 'Portfolio' },
    { to: '/library', label: 'Library' },
  ];

  const v = strategy?.active_version;
  const providerKey = health?.ai_provider ?? (health?.ai_configured ? 'openai' : 'stub');
  const providerLabel = PROVIDER_LABELS[providerKey] ?? providerKey;
  const dotColor =
    health === undefined ? 'var(--text-muted)' : health.ai_configured ? 'var(--teal)' : 'var(--amber)';

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <span style={{ color: 'var(--teal)' }}>✦</span> FundOps
        <div className="sidebar-brand-sub">Investment operations</div>
      </div>

      <div className="sidebar-nav">
        {nav.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
            {item.label}
            {item.badge != null && item.badge > 0 && (
              <span className="side-badge">{item.badge}</span>
            )}
          </NavLink>
        ))}
      </div>

      <div className="sidebar-foot">
        <button className="side-chip" onClick={onOpenWiring} title="How the Constitution wires each capability — read-only">
          <div className="side-chip-label">Constitution</div>
          <div className="side-chip-value">
            {v ? `v${v.version_number}` : 'not set'}
            {v?.style_blend
              ? ` · ${Object.keys(v.style_blend).slice(0, 2).join('/')}`
              : ''}
          </div>
          {strategy?.universe?.name && (
            <div className="side-chip-sub">
              {strategy.universe.name}
              {strategy.universe.tickers_count != null ? ` · ${strategy.universe.tickers_count} names` : ''}
            </div>
          )}
          {strategy?.pending_proposal && (
            <div className="side-chip-sub" style={{ color: 'var(--purple-ink)' }}>draft pending</div>
          )}
        </button>

        <NavLink to="/settings" className="side-chip" style={{ textDecoration: 'none' }}>
          <div style={{ fontSize: 'var(--text-xs)' }}>
            <span className="health-dot" style={{ background: dotColor }} /> {providerLabel}
          </div>
          <div className="side-chip-sub">Settings · usage · data</div>
        </NavLink>

        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className="wiring-chip"
            style={{ flex: 1, cursor: 'pointer', justifyContent: 'center' }}
            aria-label="Toggle light or dark theme"
            title="Toggle light/dark theme"
            onClick={() => {
              const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
              document.documentElement.dataset.theme = next;
              localStorage.setItem('fundops.theme', next);
            }}
          >
            theme
          </button>
          <button
            className="wiring-chip"
            style={{ flex: 1, cursor: 'pointer', justifyContent: 'center' }}
            aria-label="Open command palette (Command-K)"
            title="Open command palette (⌘K)"
            onClick={onOpenPalette}
          >
            ⌘K
          </button>
        </div>
      </div>
    </nav>
  );
}

export default Sidebar;
