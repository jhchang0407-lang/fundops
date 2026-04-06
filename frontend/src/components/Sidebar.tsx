import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../api/client';
import { useRunningJobs } from './JobTracker';

type NavItem = { to: string; label: string; icon: string; end?: boolean };

const navGroups: (NavItem[] | 'sep')[] = [
  [
    { to: '/', label: 'Chat', icon: 'AI', end: true },
    { to: '/dashboard', label: 'Dashboard', icon: 'DB' },
  ],
  'sep',
  [
    { to: '/screener', label: 'Screener', icon: 'SC' },
    { to: '/research', label: 'Research', icon: 'RS' },
    { to: '/portfolio', label: 'Portfolio', icon: 'PF' },
    { to: '/library', label: 'Library', icon: 'LB' },
    { to: '/allocator', label: 'Allocator', icon: 'AL' },
  ],
  'sep',
  [
    { to: '/settings', label: 'Settings', icon: 'ST' },
  ],
];

export function Sidebar() {
  const runningJobs = useRunningJobs();
  const pipelineRunning = runningJobs.some(j => j.agent === 'pipeline');
  const [starting, setStarting] = useState(false);

  const handleRunPipeline = async () => {
    if (pipelineRunning || starting) return;
    setStarting(true);
    try {
      await api.runPipeline();
    } catch (e) {
      console.error('Pipeline failed:', e);
    } finally {
      setTimeout(() => setStarting(false), 3000);
    }
  };

  return (
    <nav style={{
      width: 208,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)), var(--bg-secondary)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      height: '100vh',
      position: 'sticky',
      top: 0,
    }}>
      <div style={{
        padding: '18px 14px',
        fontFamily: 'var(--font-data)',
        fontSize: 'var(--text-lg)',
        fontWeight: 600,
        color: 'var(--accent)',
        letterSpacing: '0.08em',
        borderBottom: '1px solid var(--border)',
      }}>
        <div>FUNDOPS</div>
        <div style={{ marginTop: 6, color: 'var(--text-muted)', fontSize: '10px' }}>
          PERSONAL INVESTMENT OS
        </div>
      </div>
      <div style={{ flex: 1, padding: '8px 0', overflowY: 'auto' }}>
        {navGroups.map((group, gi) =>
          group === 'sep' ? (
            <div key={`sep-${gi}`} style={{ height: 1, background: 'var(--border)', margin: '8px 14px' }} />
          ) : (
            group.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  margin: '0 10px 4px',
                  padding: '9px 10px',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  fontSize: 'var(--text-sm)',
                  textDecoration: 'none',
                  border: `1px solid ${isActive ? 'var(--accent-strong)' : 'transparent'}`,
                  borderRadius: '8px',
                  background: isActive ? 'rgba(245,166,35,0.08)' : 'transparent',
                })}
              >
                <span style={{
                  width: 26,
                  height: 26,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 6,
                  background: 'rgba(255,255,255,0.04)',
                  color: 'inherit',
                  fontFamily: 'var(--font-data)',
                  fontSize: '10px',
                }}>
                  {item.icon}
                </span>
                {item.label}
              </NavLink>
            ))
          )
        )}
      </div>
      <div style={{ padding: 12, borderTop: '1px solid var(--border)' }}>
        <button
          className="btn btn-accent"
          onClick={handleRunPipeline}
          disabled={pipelineRunning || starting}
          style={{
            width: '100%',
            padding: '10px 12px',
            opacity: (pipelineRunning || starting) ? 0.8 : 1,
          }}
        >
          {pipelineRunning ? '● Running...' : starting ? 'Starting...' : 'Run Pipeline'}
        </button>
        {runningJobs.length > 0 && (
          <div style={{
            marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-muted)',
            textAlign: 'center',
          }}>
            {runningJobs.length} job{runningJobs.length !== 1 ? 's' : ''} active
          </div>
        )}
      </div>
    </nav>
  );
}
