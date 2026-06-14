/**
 * Runs — the pipeline as a durable, visible object. The stage map reads each
 * stage's live workbench state (counts, gates, failures); stages open their
 * full panes. Leave anytime: completed work persists, failures stay visible
 * and never become verdicts.
 */

import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getIC,
  getMemo,
  getRuns,
  getScreener,
  getThesis,
  runPipeline,
} from '../api/client';
import type { RunSummary } from '../api/client';
import { PageHeader } from '../components/PageHeader';

function fmtWhen(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** One honest line of what a run produced, from its recorded stats —
 * "completed" alone hides empty results (e.g. memo with nothing passed IC). */
function runResult(r: RunSummary): string {
  const s = (r.stats ?? {}) as Record<string, unknown>;
  const n = (k: string) => (typeof s[k] === 'number' ? (s[k] as number) : null);
  switch (r.kind) {
    case 'screener':
      return n('passed') != null ? `${n('passed')} passed of ${n('universe_size') ?? '—'}` : '—';
    case 'thesis':
      return n('completed') != null ? `${n('completed')} theses · ${n('selected') ?? 0} selected` : '—';
    case 'ic_review':
      return n('reviewed') != null ? `${n('passes') ?? 0} pass / ${n('fails') ?? 0} fail` : '—';
    case 'memo': {
      if (n('intake') === 0) return 'nothing to write — no IC passes';
      if (n('written') == null) return '—';
      const failed = n('failed') ?? 0;
      const ft = Array.isArray(s.failed_tickers) ? (s.failed_tickers as string[]) : [];
      const base = `${n('written')} of ${n('intake')} written`;
      return failed > 0
        ? `${base} · ${failed} failed${ft.length ? ` (${ft.join(', ')})` : ''}`
        : base;
    }
    case 'pipeline':
      return n('candidates') != null
        ? `${n('candidates')} candidates → ${n('theses') ?? 0} theses → ${n('ic_passes') ?? 0} IC passes → ${n('memos') ?? 0} memos`
        : '—';
    default:
      return '—';
  }
}

function StageCard({
  to, label, status, headline, detail, needsYou,
}: {
  to: string;
  label: string;
  status?: string;
  headline: string;
  detail?: string;
  needsYou?: boolean;
}) {
  const running = status === 'running';
  return (
    <Link
      to={to}
      className="card"
      style={{
        textDecoration: 'none',
        color: 'var(--text-primary)',
        ...(needsYou ? { boxShadow: 'var(--sh1), inset 0 0 0 1.5px var(--amber)' } : {}),
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
        <span
          className="health-dot"
          style={{
            background: running
              ? 'var(--teal)'
              : needsYou
                ? 'var(--amber)'
                : status === 'completed'
                  ? 'var(--teal)'
                  : 'var(--text-muted)',
            ...(running ? { animation: 'pulse 1.2s ease-in-out infinite' } : {}),
          }}
        />
        <span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>{label}</span>
        {needsYou && (
          <span className="mode-chip" style={{ background: 'var(--amber-bg)', color: 'var(--amber-ink)' }}>
            needs you
          </span>
        )}
      </div>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{headline}</div>
      {detail && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>{detail}</div>
      )}
    </Link>
  );
}

export default function Runs() {
  const qc = useQueryClient();
  // Stages are tiny local reads — poll them alongside the runs list so a
  // finishing pipeline updates the map without a manual refresh.
  const { data: runs } = useQuery({ queryKey: ['runs'], queryFn: () => getRuns(20), retry: 1, refetchInterval: 5000 });
  const { data: screener } = useQuery({ queryKey: ['screener-current'], queryFn: getScreener, retry: 1, refetchInterval: 5000 });
  const { data: thesis } = useQuery({ queryKey: ['thesis-current'], queryFn: getThesis, retry: 1, refetchInterval: 5000 });
  const { data: ic } = useQuery({ queryKey: ['ic-current'], queryFn: getIC, retry: 1, refetchInterval: 5000 });
  const { data: memo } = useQuery({ queryKey: ['memo-current'], queryFn: getMemo, retry: 1, refetchInterval: 5000 });

  const pipeline = useMutation({
    mutationFn: runPipeline,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runs'] });
      for (const k of ['screener-current', 'thesis-current', 'ic-current', 'memo-current']) {
        qc.invalidateQueries({ queryKey: [k] });
      }
    },
  });

  const live = (runs ?? []).filter((r) => r.status === 'running');
  const recent = (runs ?? []).slice(0, 8);

  const icPasses = (ic?.selection ?? []).concat(ic?.remaining ?? []).filter((r) => r.verdict === 'pass').length;
  const icJudged = (ic?.selection ?? []).concat(ic?.remaining ?? []).filter((r) => r.verdict != null).length;
  const memosDone = (memo?.intake ?? []).filter((m) => m.artifact_id).length;
  // IC passes promoted after the last memo run sit here unwritten — downstream
  // stages never re-run silently, so surface the pending work explicitly.
  const memoPending = (memo?.intake?.length ?? 0) - memosDone;
  const thesisFailed = (thesis?.rows ?? []).filter((r) => r.state === 'failed').length;

  return (
    <div>
      <PageHeader
        sectionLabel="Runs"
        title="Runs"
        subtitle="Durable and resumable — every step recorded as provenance; operational failure is never an investment judgment."
        actions={
          <button className="btn btn-accent" disabled={pipeline.isPending} onClick={() => pipeline.mutate()}>
            {pipeline.isPending ? 'Starting…' : 'Run full pipeline'}
          </button>
        }
      />

      {live.length > 0 && (
        <div className="banner banner-positive" style={{ marginBottom: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
          <span className="health-dot" style={{ background: 'var(--teal)', animation: 'pulse 1.2s ease-in-out infinite' }} />
          {live.map((r) => `${r.kind.replace(/_/g, ' ')} running`).join(' · ')} — stages update live below.
        </div>
      )}

      <div className="card-title" style={{ marginBottom: 8 }}>Stage map · click a stage to work it</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(225px, 1fr))', gap: 10, marginBottom: 14 }}>
        <StageCard
          to="/screener"
          label="Screener"
          status={String(screener?.status ?? '')}
          headline={
            (screener?.summary?.universe_size ?? 0) > 0
              ? `${screener!.summary!.universe_size} evaluated · ${screener!.summary!.passed ?? 0} passed`
              : 'No current results — run it above'
          }
          detail={`${screener?.top_picks?.length ?? 0} top picks · deterministic, no model`}
        />
        <StageCard
          to="/thesis"
          label="Thesis"
          status={String(thesis?.status ?? '')}
          headline={
            (thesis?.rows?.length ?? 0) > 0
              ? `${thesis!.rows.length} drafted · ${thesis!.selection.length} selected`
              : 'Waits for the screener handoff'
          }
          detail={thesisFailed > 0 ? `${thesisFailed} operational failure${thesisFailed > 1 ? 's' : ''} — visible, retryable` : 'return decomposition per candidate'}
        />
        <StageCard
          to="/ic-review"
          label="IC review"
          status={String(ic?.status ?? '')}
          headline={icJudged > 0 ? `${icJudged} judged · ${icPasses} passed` : 'Waits for thesis selections'}
          detail="hard hurdles deterministic · override either way"
          needsYou={icJudged > 0 && (ic?.selection?.length ?? 0) === 0 && icPasses > 0}
        />
        <StageCard
          to="/memo"
          label="Memo"
          status={String(memo?.status ?? '')}
          headline={
            (memo?.intake?.length ?? 0) > 0
              ? `${memosDone} of ${memo!.intake.length} written`
              : 'Waits for your IC selections'
          }
          detail={
            memoPending > 0 && memo?.status !== 'running'
              ? `${memoPending} IC pass${memoPending > 1 ? 'es' : ''} awaiting a memo run — open to write ${memoPending > 1 ? 'them' : 'it'}`
              : '7 sections + machine-checkable monitoring plan'
          }
          needsYou={memoPending > 0 && memo?.status !== 'running'}
        />
      </div>

      <div className="card">
        <div className="card-title">Recent runs</div>
        {recent.length === 0 ? (
          <div className="empty-note">No runs recorded yet — start one above or from ⌘K anywhere.</div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>Kind</th>
                <th>Status</th>
                <th>Result</th>
                <th>Started</th>
                <th>Finished</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => {
                const failed = typeof (r.stats as Record<string, unknown> | undefined)?.failed === 'number'
                  ? (r.stats as Record<string, number>).failed
                  : 0;
                // A completion that carried operational failures is partial, not
                // clean — flag it distinctly so it doesn't read as all-good (ISSUE-009).
                const partial = r.status === 'completed' && failed > 0;
                return (
                  <tr key={r.id}>
                    <td>{r.kind.replace(/_/g, ' ')}</td>
                    <td>
                      <span
                        className="mode-chip"
                        title={partial ? `${failed} item(s) failed` : undefined}
                        style={
                          partial
                            ? { background: 'var(--amber-bg)', color: 'var(--amber-ink)' }
                            : r.status === 'completed'
                              ? { background: 'var(--teal-bg)', color: 'var(--teal-ink)' }
                              : r.status === 'failed'
                                ? { background: 'var(--red-bg)', color: 'var(--red-ink)' }
                                : { background: 'var(--amber-bg)', color: 'var(--amber-ink)' }
                        }
                      >
                        {partial ? 'partial' : String(r.status)}
                      </span>
                    </td>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{runResult(r)}</td>
                    <td style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>{fmtWhen(r.started_at)}</td>
                    <td style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>{fmtWhen(r.finished_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          Upstream changes never silently rewrite downstream stages — each handoff is explicit and recorded.
        </div>
      </div>
    </div>
  );
}
