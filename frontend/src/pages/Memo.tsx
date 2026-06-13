/**
 * Memo — fourth workflow stage. One structured Investment Memo per intake
 * item (the deep-research stage). Completed memos open in the Workflow
 * Artifact Reader; the memo decision is evidence, never an instruction.
 */
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getMemo, runMemo } from '../api/client';
import type { MemoIntakeItem } from '../api/client';
import { RunFailedBanner, RunningBanner, StateCue, TickerLink } from '../components/workflow/StageTable';

const IN_FLIGHT = new Set(['pending', 'queued', 'running', 'retrying']);

const DECISION_STYLE: Record<string, { label: string; bg: string; color: string }> = {
  attractive: { label: 'attractive', bg: 'rgba(52,168,83,0.15)', color: 'var(--positive)' },
  watchlist: { label: 'watchlist', bg: 'rgba(66,133,244,0.12)', color: 'var(--info)' },
  avoid: { label: 'avoid', bg: 'rgba(234,67,53,0.15)', color: 'var(--negative)' },
  needs_more_evidence: { label: 'needs more evidence', bg: 'rgba(251,188,4,0.12)', color: 'var(--warning)' },
};

function DecisionBadge({ decision }: { decision?: string | null }) {
  if (!decision) return <span className="muted">—</span>;
  const s = DECISION_STYLE[decision] ?? { label: decision.replace(/_/g, ' '), bg: 'var(--bg-tertiary)', color: 'var(--text-secondary)' };
  return (
    <span className="badge" style={{ background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

export function Memo() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['memo'],
    queryFn: getMemo,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return false;
      const active = d.status === 'running' || d.intake.some((i) => IN_FLIGHT.has(i.state));
      return active ? 2000 : false;
    },
  });

  const generate = useMutation({
    mutationFn: (ticker?: string) => runMemo(ticker),
    onSettled: () => qc.invalidateQueries({ queryKey: ['memo'] }),
  });

  const intake = data?.intake ?? [];
  const status = data?.status ?? 'idle';
  const anyInFlight = status === 'running' || intake.some((i) => IN_FLIGHT.has(i.state));
  const generatable = intake.filter((i) => i.state !== 'completed' && !IN_FLIGHT.has(i.state));
  const doneCount = intake.filter((i) => i.state === 'completed').length;
  const writing = intake.find((i) => i.state === 'running' || i.state === 'retrying');
  const progressLabel =
    `Generating investment memos — ${doneCount} of ${intake.length} done` +
    (writing ? ` · writing ${writing.ticker} (evidence → research → 7-section body)…` : '…');

  const rowAction = (item: MemoIntakeItem) => {
    if (item.state === 'completed' && item.artifact_id) {
      return (
        <Link to={`/artifact/${item.artifact_id}`} className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 'var(--text-xs)', textDecoration: 'none' }}>
          Open memo →
        </Link>
      );
    }
    if (IN_FLIGHT.has(item.state)) return null;
    return (
      <button
        className="btn"
        style={{ padding: '4px 10px', fontSize: 'var(--text-xs)' }}
        disabled={generate.isPending || anyInFlight}
        onClick={() => generate.mutate(item.ticker)}
      >
        {item.state === 'failed' ? 'Retry memo' : 'Generate memo'}
      </button>
    );
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/runs" className="page-kicker" style={{ textDecoration: 'none' }}>← Runs · Workflow · Stage 4</Link>
          <h1 className="page-title">Memo</h1>
          <div className="page-subtitle">
            Memo is the deep-research stage — one structured memo per opportunity.
          </div>
        </div>
        <button
          className="btn btn-accent"
          disabled={generate.isPending || anyInFlight || generatable.length === 0}
          onClick={() => generate.mutate(undefined)}
        >
          {anyInFlight ? 'Generating…' : `Generate all (${generatable.length})`}
        </button>
      </div>

      {status === 'running' && <RunningBanner label={progressLabel} />}
      {status === 'failed' && <RunFailedBanner />}
      {generate.isError && <RunFailedBanner error={(generate.error as Error).message} />}

      {isLoading ? (
        <div className="stage-empty">Loading memo intake…</div>
      ) : intake.length === 0 ? (
        <div className="stage-empty">
          Memo intake is empty this session. Hand off the IC selection (or run the full pipeline) to populate it.
        </div>
      ) : (
        <section className="stage-block">
          <div className="stage-block-header">
            <span className="stage-block-title">Memo Intake</span>
            <span className="stage-block-count">{intake.length}</span>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 90 }}>Ticker</th>
                  <th style={{ width: 160 }}>State</th>
                  <th>Memo Decision</th>
                  <th style={{ width: 150, textAlign: 'right' }} />
                </tr>
              </thead>
              <tbody>
                {intake.map((item) => (
                  <tr key={item.ticker}>
                    <td>
                      <TickerLink ticker={item.ticker} />
                    </td>
                    <td>
                      {item.state === 'completed' ? (
                        <span className="badge badge-muted">completed</span>
                      ) : (
                        <StateCue state={item.state} />
                      )}
                    </td>
                    <td>
                      <DecisionBadge decision={item.decision} />
                    </td>
                    <td style={{ textAlign: 'right' }}>{rowAction(item)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="inline-metadata" style={{ marginTop: 8 }}>
            <span>Memo is the deep-research stage — one structured memo per opportunity. Generate deliberately.</span>
          </div>
        </section>
      )}
    </div>
  );
}

export default Memo;
