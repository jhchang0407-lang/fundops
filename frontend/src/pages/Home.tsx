/**
 * Home — the command surface. The system reads the data before you arrive
 * (briefing, Now panel); the conversation is the primary work area.
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getBriefing, getMonitoringDue } from '../api/client';
import type { BriefingResponse } from '../api/client';
import { ChatThread } from '../components/chat/ChatThread';
import { prefillConversation } from '../components/CommandPalette';
import { parseDate } from '../utils/formatFinancials';

const SLASH_SUGGESTIONS: { label: string; fill: string }[] = [
  { label: '/pipeline', fill: '/pipeline run' },
  { label: '/screen', fill: 'screen for roic > 15% and momentum > 10% right now' },
  { label: '/portfolio risk', fill: "what's my portfolio risk?" },
  { label: '/archive', fill: 'why did we pass on ' },
  { label: '/strategy', fill: "Let's review and refine our investment strategy." },
];

function fmtShortDate(iso: string): string {
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function Briefing({ data }: { data: BriefingResponse }) {
  const bits: React.ReactNode[] = [];
  data.filings.slice(0, 2).forEach((f, i) =>
    bits.push(
      <span key={`f${i}`}>
        {f.ticker} — {f.label.toLowerCase()} ({f.filed_at}){' '}
        <Link to={`/company/${f.ticker}`} className="wiring-chip" style={{ textDecoration: 'none' }}>
          filing
        </Link>
        {'. '}
      </span>,
    ),
  );
  if (data.health.broken.length > 0)
    bits.push(
      <span key="hb">
        Thesis health is broken on {data.health.broken.join(', ')}{' '}
        <Link to="/inbox" className="wiring-chip" style={{ textDecoration: 'none' }}>
          health check
        </Link>
        {'. '}
      </span>,
    );
  if (data.learning_ready > 0)
    bits.push(
      <span key="lr">
        {data.learning_ready} learning pattern{data.learning_ready > 1 ? 's' : ''} reached
        recommendation strength{' '}
        <Link to="/inbox" className="wiring-chip" style={{ textDecoration: 'none' }}>
          review
        </Link>
        {'. '}
      </span>,
    );
  if (data.pending_proposal)
    bits.push(
      <span key="pp">
        A Constitution draft awaits your decision{' '}
        <Link to="/inbox" className="wiring-chip" style={{ textDecoration: 'none' }}>
          proposal
        </Link>
        {'. '}
      </span>,
    );
  const macroLine = data.macro
    .filter((m) => m.value !== null)
    .map((m) => `${m.label} ${m.display}`)
    .join(' · ');
  if (macroLine) bits.push(<span key="mac">Macro: {macroLine} <span className="wiring-chip">FRED · cached</span>.</span>);

  return (
    <div
      className="card"
      style={{ borderLeft: '2px solid var(--teal)', borderRadius: '4px 12px 12px 4px', marginBottom: 12 }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 4 }}>
        <b style={{ fontSize: 'var(--text-sm)' }}>Briefing</b>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          {fmtShortDate(data.date)} · composed from your retained records · every claim linked
        </span>
      </div>
      <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.8 }}>
        {bits.length > 0 ? bits : (
          <span className="dim" style={{ color: 'var(--text-secondary)' }}>
            Quiet so far — no new filings for holdings, no health changes, nothing waiting on you.
          </span>
        )}
      </div>
    </div>
  );
}

function NowPanel({ data, due }: { data?: BriefingResponse; due?: number }) {
  return (
    <aside className="now-panel">
      <div className="card" style={{ padding: '10px 12px' }}>
        <div className="card-title">Needs you</div>
        {data?.pending_proposal ? (
          <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.5, marginBottom: 6 }}>
            Constitution draft pending
            <br />
            <Link to="/inbox" style={{ color: 'var(--teal-ink)', fontSize: 'var(--text-xs)' }}>
              Review →
            </Link>
          </div>
        ) : null}
        {(data?.learning_ready ?? 0) > 0 && (
          <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
            {data!.learning_ready} learning recommendation
            {data!.learning_ready > 1 ? 's' : ''} ready
            <br />
            <Link to="/inbox" style={{ color: 'var(--purple-ink)', fontSize: 'var(--text-xs)' }}>
              Review →
            </Link>
          </div>
        )}
        {!data?.pending_proposal && (data?.learning_ready ?? 0) === 0 && (
          <div className="empty-note" style={{ padding: 0 }}>
            Nothing waiting on you.
            {(data?.learning?.evaluations ?? 0) > 0 && (
              <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
                Learning is tracking {data!.learning!.evaluations} outcome
                {data!.learning!.evaluations > 1 ? 's' : ''}
                {(data?.learning?.patterns ?? 0) > 0
                  ? ` · ${data!.learning!.patterns} pattern${data!.learning!.patterns > 1 ? 's' : ''}`
                  : ''}
                ; no recommendation has reached strength yet.
              </span>
            )}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: '10px 12px' }}>
        <div className="card-title">Running</div>
        {(data?.running.length ?? 0) > 0 ? (
          data!.running.map((r) => (
            <Link
              key={r.id}
              to="/runs"
              style={{ display: 'block', fontSize: 'var(--text-sm)', textDecoration: 'none', color: 'var(--text-primary)' }}
            >
              {r.kind.replace(/_/g, ' ')}
              <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                open the run →
              </span>
            </Link>
          ))
        ) : (
          <div className="empty-note" style={{ padding: 0 }}>No live runs.</div>
        )}
      </div>

      <div className="card" style={{ padding: '10px 12px' }}>
        <div className="card-title">Watching</div>
        <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.9 }}>
          {data?.health.broken.map((t) => (
            <div key={t}>
              <span className="health-dot" style={{ background: 'var(--red)' }} /> {t} broke
            </div>
          ))}
          {data?.health.watching.map((t) => (
            <div key={t}>
              <span className="health-dot" style={{ background: 'var(--amber)' }} /> {t} watching
            </div>
          ))}
          <div style={{ color: 'var(--text-secondary)' }}>
            <span className="health-dot" style={{ background: 'var(--teal)' }} /> {data?.health.intact ?? 0} intact
            {due != null && due > 0 ? ` · ${due} checks due` : ''}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: '10px 12px' }}>
        <div className="card-title">Today</div>
        <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.8, color: 'var(--text-secondary)' }}>
          {(data?.events ?? []).slice(0, 3).map((e, i) => (
            <div key={i}>
              <Link to={`/company/${e.ticker}`} style={{ fontFamily: 'var(--font-data)' }}>{e.ticker}</Link>{' '}
              {e.label} · {parseDate(e.date).toLocaleDateString([], { month: 'short', day: 'numeric' })}
            </div>
          ))}
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
            {(data?.macro ?? [])
              .filter((m) => m.value !== null)
              .map((m) => `${m.series} ${m.display}`)
              .join(' · ') || 'macro arrives with the daily sync'}
          </div>
        </div>
      </div>
    </aside>
  );
}

export default function Home() {
  const { data } = useQuery({ queryKey: ['briefing'], queryFn: getBriefing, retry: 1 });
  const { data: due } = useQuery({ queryKey: ['monitoring-due'], queryFn: getMonitoringDue, retry: 1 });

  return (
    <div className="home-wrap">
      <div className="home-main">
        {data && <Briefing data={data} />}
        <div className="home-thread-shell">
          <ChatThread variant="page" />
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {SLASH_SUGGESTIONS.map((s) => (
            <button key={s.label} className="wiring-chip" style={{ cursor: 'pointer' }}
                    onClick={() => prefillConversation(s.fill)}>
              {s.label}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          One conversation, every mode — strategy changes come back as drafts, data answers carry
          citations, archive answers cite retained records.
        </div>
      </div>
      <NowPanel data={data} due={due?.due} />
    </div>
  );
}
