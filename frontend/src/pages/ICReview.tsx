/**
 * IC Review — third workflow stage (the gate). Every PASS enters IC Selection
 * (no cap); FAILs sit in Remaining IC Reviews. The +/− controls here are user
 * overrides of the deterministic gate, confirmed inline and recorded as such.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getIC, overrideIC, runIC } from '../api/client';
import type { ICRow } from '../api/client';
import {
  ExpandedRow,
  MoveButton,
  RunFailedBanner,
  RunningBanner,
  StageBlock,
  StateCue,
  TickerLink,
} from '../components/workflow/StageTable';
import { ICScorecard } from '../components/workflow/ICScorecard';
import { extraNum, extraStr } from '../components/workflow/helpers';
import { fmtPrice } from '../utils/formatFinancials';

const COLS = 6;

const IN_FLIGHT = new Set(['pending', 'queued', 'running', 'retrying']);

function Head() {
  return (
    <tr>
      <th style={{ width: 90 }}>Ticker</th>
      <th>Company</th>
      <th className="num" style={{ width: 100 }}>
        Price
      </th>
      <th style={{ width: 110 }}>Verdict</th>
      <th style={{ width: 200 }} />
      <th style={{ width: 44 }} />
    </tr>
  );
}

function VerdictBadge({ row }: { row: ICRow }) {
  if (row.verdict === 'pass') return <span className="verdict-pass">PASS</span>;
  if (row.verdict === 'fail') return <span className="verdict-fail">FAIL</span>;
  if (row.state && IN_FLIGHT.has(row.state)) {
    return (
      <span className="pulse-text" style={{ fontSize: 'var(--text-xs)' }}>
        <span className="pulse-dot" />
        pending
      </span>
    );
  }
  return <span className="verdict-pending">—</span>;
}

export function ICReview() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<{ ticker: string; action: 'promote' | 'remove' } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['ic'],
    queryFn: getIC,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return false;
      const rows = [...d.selection, ...d.remaining];
      const active = d.status === 'running' || rows.some((r) => (r.state ? IN_FLIGHT.has(r.state) : false));
      return active ? 2000 : false;
    },
  });

  const run = useMutation({
    mutationFn: runIC,
    onSettled: () => qc.invalidateQueries({ queryKey: ['ic'] }),
  });

  const override = useMutation({
    mutationFn: ({ ticker, action }: { ticker: string; action: 'promote' | 'remove' }) => overrideIC(ticker, action),
    onSuccess: (updated) => {
      qc.setQueryData(['ic'], updated);
      setConfirming(null);
    },
  });

  const status = data?.status ?? 'idle';
  const running = status === 'running' || run.isPending;
  const total = (data?.selection.length ?? 0) + (data?.remaining.length ?? 0);

  const renderRows = (rows: ICRow[], block: 'selected' | 'remaining') =>
    rows.flatMap((row) => {
      const isOpen = expanded === row.ticker && row.verdict != null;
      const isConfirming = confirming?.ticker === row.ticker;
      const hasVerdict = row.verdict != null && !(row.state && IN_FLIGHT.has(row.state));
      const action: 'promote' | 'remove' = block === 'selected' ? 'remove' : 'promote';
      const priorVerdict = extraStr(row, 'prior_verdict');
      const nodes = [
        <tr
          key={row.ticker}
          className="stage-row"
          onClick={() => row.verdict != null && setExpanded(isOpen ? null : row.ticker)}
        >
          <td>
            <TickerLink ticker={row.ticker} />
          </td>
          <td>{row.company_name || '—'}</td>
          <td className="num">{fmtPrice(row.price)}</td>
          <td>
            <VerdictBadge row={row} />
          </td>
          <td>
            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
              {row.state && row.state !== 'completed' && !IN_FLIGHT.has(row.state) && <StateCue state={row.state} />}
              {row.is_override && (
                <span className="tag-override" title="Verdict set by user override — the deterministic gate's original result is retained as provenance.">
                  user override{priorVerdict ? ` · gate said ${priorVerdict.toUpperCase()}` : ''}
                </span>
              )}
            </span>
          </td>
          <td style={{ textAlign: 'right' }}>
            <MoveButton
              kind={block === 'selected' ? 'dismiss' : 'promote'}
              enabled={hasVerdict && !override.isPending}
              busy={override.isPending}
              label={block === 'selected' ? `Override ${row.ticker} to FAIL` : `Override ${row.ticker} to PASS`}
              onClick={() => setConfirming(isConfirming ? null : { ticker: row.ticker, action })}
            />
          </td>
        </tr>,
      ];
      if (isConfirming) {
        nodes.push(
          <ExpandedRow key={`${row.ticker}-confirm`} colSpan={COLS}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 'var(--text-sm)' }}>
                Override <span className="ticker">{row.ticker}</span> to{' '}
                <strong>{confirming.action === 'promote' ? 'PASS' : 'FAIL'}</strong>?
              </span>
              <span className="muted" style={{ fontSize: 'var(--text-xs)' }}>
                Recorded as a user override — the gate verdict ({row.verdict?.toUpperCase() ?? '—'}) is kept as provenance.
              </span>
              <span style={{ display: 'inline-flex', gap: 6, marginLeft: 'auto' }}>
                <button
                  className="btn btn-accent"
                  style={{ padding: '4px 12px', fontSize: 'var(--text-xs)' }}
                  disabled={override.isPending}
                  onClick={() => override.mutate(confirming)}
                >
                  {override.isPending ? 'Recording…' : 'Confirm override'}
                </button>
                <button
                  className="btn btn-ghost"
                  style={{ padding: '4px 12px', fontSize: 'var(--text-xs)' }}
                  onClick={() => setConfirming(null)}
                >
                  Cancel
                </button>
              </span>
            </div>
          </ExpandedRow>,
        );
      }
      if (isOpen) {
        nodes.push(
          <ExpandedRow key={`${row.ticker}-detail`} colSpan={COLS}>
            <ICScorecard
              rationale={row.rationale}
              hurdles={row.hurdle_findings}
              conviction={row.conviction}
              constitutionFit={row.constitution_fit}
              dataQuality={row.data_quality}
              gateScore={row.gate_score}
              cutoff={extraNum(row, 'cutoff')}
            />
          </ExpandedRow>,
        );
      }
      return nodes;
    });

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/runs" className="page-kicker" style={{ textDecoration: 'none' }}>← Runs · Workflow · Stage 3</Link>
          <h1 className="page-title">IC Review</h1>
          <div className="page-subtitle">
            Deterministic gate over the thesis selection — hard hurdles first, then gate score vs cutoff.
          </div>
        </div>
        <button className="btn btn-accent" onClick={() => run.mutate()} disabled={running}>
          {running ? 'Reviewing…' : 'Run IC Review'}
        </button>
      </div>

      {status === 'running' && <RunningBanner label="IC review in progress — verdicts land per ticker as the gate evaluates…" />}
      {status === 'failed' && <RunFailedBanner />}
      {run.isError && <RunFailedBanner error={(run.error as Error).message} />}

      {isLoading ? (
        <div className="stage-empty">Loading IC state…</div>
      ) : total === 0 ? (
        <div className="stage-empty">
          No IC intake yet this session. Hand off the thesis selection (or run the full pipeline) to populate it.
        </div>
      ) : (
        <>
          <StageBlock
            variant="selected"
            title="IC Selection"
            count={data?.selection.length ?? 0}
            head={<Head />}
            emptyText="No passes yet — every PASS verdict enters the IC selection automatically."
          >
            {renderRows(data?.selection ?? [], 'selected')}
          </StageBlock>
          <StageBlock
            variant="remaining"
            title="Remaining IC Reviews"
            count={data?.remaining.length ?? 0}
            head={<Head />}
            emptyText="Nothing outside the selection."
          >
            {renderRows(data?.remaining ?? [], 'remaining')}
          </StageBlock>
        </>
      )}
    </div>
  );
}

export default ICReview;
