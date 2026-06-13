/**
 * Screener — first workflow stage. Universe → requirements → ranked review
 * set; Top Picks (selected block) are the handoff to Thesis.
 */
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getScreener, runScreener, selectScreener } from '../api/client';
import type { CandidateRow, PassEvidence, ScreenerCurrent, SelectionAction } from '../api/client';
import {
  ExpandedRow,
  MoveButton,
  RunFailedBanner,
  RunningBanner,
  StageBlock,
  TickerLink,
} from '../components/workflow/StageTable';
import { fmtMetric, fmtPrice, humanizeLabel } from '../utils/formatFinancials';

const COLS = 5;

function Head() {
  return (
    <tr>
      <th style={{ width: 90 }}>Ticker</th>
      <th>Company</th>
      <th style={{ width: 180 }}>Sector</th>
      <th className="num" style={{ width: 100 }}>
        Price
      </th>
      <th style={{ width: 44 }} />
    </tr>
  );
}

/** Same metric slots, same order, for every candidate — em-dash for missing. */
function useFinancialSlots(data: ScreenerCurrent | undefined) {
  return useMemo(() => {
    const slots = new Map<string, string>();
    for (const row of [...(data?.top_picks ?? []), ...(data?.remaining ?? [])]) {
      for (const kf of row.key_financials ?? []) {
        if (!slots.has(kf.metric)) slots.set(kf.metric, kf.label);
      }
    }
    return [...slots.entries()].map(([metric, label]) => ({ metric, label }));
  }, [data]);
}

/** Prefer the humanized backend fields; fall back to the raw machine values. */
function evidenceCells(e: PassEvidence): { name: string; sub: string | null; threshold: string; observed: string } {
  const metric = typeof e.metric === 'string' && e.metric ? e.metric : e.criterion ?? '';
  return {
    name: e.label || humanizeLabel((e.criterion ?? '').split('.').pop() ?? '—'),
    sub: e.rule ?? null,
    threshold: e.threshold_display ?? (e.threshold != null ? String(e.threshold) : '—'),
    observed:
      e.observed_display ??
      (typeof e.observed === 'number' ? fmtMetric(metric, e.observed) : e.observed != null ? String(e.observed) : '—'),
  };
}

function PassEvidenceCard({ evidence }: { evidence: PassEvidence[] }) {
  return (
    <div className="expanded-card">
      <div className="expanded-card-title">Pass Evidence</div>
      <div className="table-shell" style={{ boxShadow: 'none' }}>
        <table className="artifact-data-table">
          <thead>
            <tr>
              <th>Requirement</th>
              <th className="num">Threshold</th>
              <th className="num">Observed</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((e, i) => {
              const c = evidenceCells(e);
              return (
                <tr key={`${e.criterion ?? c.name}-${i}`}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{c.name}</div>
                    {c.sub && <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>{c.sub}</div>}
                  </td>
                  <td className="num">{c.threshold}</td>
                  <td className="num">{c.observed}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CandidateDetail({ row, slots }: { row: CandidateRow; slots: { metric: string; label: string }[] }) {
  const byMetric = new Map((row.key_financials ?? []).map((kf) => [kf.metric, kf]));
  const evidence = row.pass_evidence ?? [];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: 8 }}>
        <div className="expanded-card">
          <div className="expanded-card-title">Ranking Explanation</div>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            {row.ranking_explanation || 'No ranking explanation recorded for this candidate.'}
          </div>
        </div>
        <div className="expanded-card">
          <div className="expanded-card-title">Key Financials</div>
          {slots.length === 0 ? (
            <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>—</div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${Math.min(slots.length, 4)}, 1fr)`,
                gap: 8,
                textAlign: 'center',
                fontFamily: 'var(--font-data)',
                fontSize: 'var(--text-xs)',
              }}
            >
              {slots.map((s) => {
                const kf = byMetric.get(s.metric);
                return (
                  <div key={s.metric}>
                    <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>{s.label}</div>
                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                      {kf?.display ?? fmtMetric(s.metric, kf?.value)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      {evidence.length > 0 && <PassEvidenceCard evidence={evidence} />}
    </div>
  );
}

export function Screener() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['screener'],
    queryFn: getScreener,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  });

  const run = useMutation({
    mutationFn: runScreener,
    onSettled: () => qc.invalidateQueries({ queryKey: ['screener'] }),
  });

  const select = useMutation({
    mutationFn: ({ ticker, action }: { ticker: string; action: SelectionAction }) => selectScreener(ticker, action),
    onSuccess: (updated) => qc.setQueryData(['screener'], updated),
  });

  const slots = useFinancialSlots(data);
  const status = data?.status ?? 'idle';
  const running = status === 'running' || run.isPending;
  const summary = data?.summary;
  const canSelect = status === 'completed' && !select.isPending;

  const renderRows = (rows: CandidateRow[], block: 'selected' | 'remaining') =>
    rows.flatMap((row) => {
      const isOpen = expanded === row.ticker;
      const nodes = [
        <tr key={row.ticker} className="stage-row" onClick={() => setExpanded(isOpen ? null : row.ticker)}>
          <td>
            <TickerLink ticker={row.ticker} />
          </td>
          <td>{row.company_name || '—'}</td>
          <td className="muted">{row.sector || '—'}</td>
          <td className="num">{fmtPrice(row.price)}</td>
          <td style={{ textAlign: 'right' }}>
            <MoveButton
              kind={block === 'selected' ? 'dismiss' : 'promote'}
              enabled={canSelect}
              busy={select.isPending}
              label={
                block === 'selected'
                  ? `Move ${row.ticker} to remaining candidates`
                  : `Add ${row.ticker} to the end of Top Picks`
              }
              onClick={() => select.mutate({ ticker: row.ticker, action: block === 'selected' ? 'dismiss' : 'promote' })}
            />
          </td>
        </tr>,
      ];
      if (isOpen) {
        nodes.push(
          <ExpandedRow key={`${row.ticker}-detail`} colSpan={COLS}>
            <CandidateDetail row={row} slots={slots} />
          </ExpandedRow>,
        );
      }
      return nodes;
    });

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/runs" className="page-kicker" style={{ textDecoration: 'none' }}>← Runs · Workflow · Stage 1</Link>
          <h1 className="page-title">Screener</h1>
          <div className="page-subtitle">
            {summary
              ? `Universe ${summary.universe_size ?? '—'} · ${summary.passed ?? '—'} passed · showing top ${summary.shown ?? '—'}`
              : 'Deterministic screen and ranking over the active universe.'}
          </div>
        </div>
        <button className="btn btn-accent" onClick={() => run.mutate()} disabled={running}>
          {running ? 'Screening…' : 'Run Screener'}
        </button>
      </div>

      {status === 'running' && <RunningBanner label="Screening universe — requirements, ranking, then Top Picks…" />}
      {status === 'failed' && <RunFailedBanner error={data?.run?.error} />}
      {run.isError && <RunFailedBanner error={(run.error as Error).message} />}

      {isLoading ? (
        <div className="stage-empty">Loading screener state…</div>
      ) : status === 'idle' && (data?.top_picks?.length ?? 0) === 0 && (data?.remaining?.length ?? 0) === 0 ? (
        <div className="stage-empty">
          No screener run yet this session. Run Screener to build the ranked candidate set from the active universe.
        </div>
      ) : (
        <>
          <StageBlock
            variant="selected"
            title="Top Picks"
            count={data?.top_picks?.length ?? 0}
            head={<Head />}
            emptyText="No top picks selected — promote candidates from below."
          >
            {renderRows(data?.top_picks ?? [], 'selected')}
          </StageBlock>
          <StageBlock
            variant="remaining"
            title="Remaining Candidates"
            count={data?.remaining?.length ?? 0}
            head={<Head />}
            emptyText="Every passed candidate is currently in Top Picks."
          >
            {renderRows(data?.remaining ?? [], 'remaining')}
          </StageBlock>
        </>
      )}
    </div>
  );
}

export default Screener;
