/**
 * Thesis — second workflow stage. Generates a completed thesis for ALL of the
 * Screener handoff intake; rows then partition into Thesis Selection (ranked
 * by return potential) and Remaining Theses. Capped theses carry a compact
 * "weak return profile" tag but stay promotable.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getThesis, runThesis, selectThesis } from '../api/client';
import type { SelectionAction, ThesisCurrent, ThesisRow } from '../api/client';
import {
  ExpandedRow,
  MoveButton,
  PendingValue,
  RunFailedBanner,
  RunningBanner,
  StageBlock,
  StateCue,
  TickerLink,
} from '../components/workflow/StageTable';
import { ReturnProfilePanel } from '../components/workflow/ReturnProfile';
import { extraStr, normalizeReturnComponents } from '../components/workflow/helpers';
import { fmtPct, fmtPrice } from '../utils/formatFinancials';

const COLS = 7;

const IN_FLIGHT = new Set(['pending', 'queued', 'running', 'retrying']);

function Head() {
  return (
    <tr>
      <th style={{ width: 90 }}>Ticker</th>
      <th>Company</th>
      <th className="num" style={{ width: 90 }}>
        Price
      </th>
      <th className="num" style={{ width: 100 }}>
        Fair Value
      </th>
      <th className="num" style={{ width: 110 }}>
        Exp. Return
      </th>
      <th style={{ width: 190 }} />
      <th style={{ width: 44 }} />
    </tr>
  );
}

function ThesisDetail({ row }: { row: ThesisRow }) {
  const opportunity = extraStr(row, 'opportunity') ?? extraStr(row, 'why_opportunity_exists');
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 8 }}>
      <div className="expanded-card">
        <div className="expanded-card-title">Completed Thesis</div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.75 }}>
          {row.summary || 'No thesis summary recorded.'}
        </div>
        {opportunity && (
          <div style={{ marginTop: 10 }}>
            <div className="expanded-card-title">Why the opportunity exists</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.75 }}>{opportunity}</div>
          </div>
        )}
        {row.artifact_id && (
          <div style={{ marginTop: 12 }}>
            <Link
              to={`/artifact/${row.artifact_id}`}
              className="btn btn-ghost"
              style={{ fontSize: 'var(--text-xs)', textDecoration: 'none', display: 'inline-block', padding: '5px 10px' }}
            >
              Open artifact →
            </Link>
            <span className="artifact-locked-caption" style={{ marginLeft: 8 }}>
              full reading in the Workflow Artifact Reader
            </span>
          </div>
        )}
      </div>
      <ReturnProfilePanel
        price={row.price}
        fairValue={row.fair_value}
        expectedReturnPct={row.expected_return_pct}
        valuationMethod={extraStr(row, 'valuation_method')}
        components={normalizeReturnComponents(row.return_components)}
        coherenceWarning={extraStr(row, 'coherence_warning')}
        keyRisk={extraStr(row, 'key_risk')}
        capped={row.capped}
      />
    </div>
  );
}

export function Thesis() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['thesis'],
    queryFn: getThesis,
    refetchInterval: (query) => {
      const d = query.state.data as ThesisCurrent | undefined;
      if (!d) return false;
      const active = d.status === 'running' || d.rows.some((r) => IN_FLIGHT.has(r.state));
      return active ? 2000 : false;
    },
  });

  const run = useMutation({
    mutationFn: runThesis,
    onSettled: () => qc.invalidateQueries({ queryKey: ['thesis'] }),
  });

  const select = useMutation({
    mutationFn: ({ ticker, action }: { ticker: string; action: SelectionAction }) => selectThesis(ticker, action),
    onSuccess: (updated) => qc.setQueryData(['thesis'], updated),
  });

  const rows = data?.rows ?? [];
  const byTicker = new Map(rows.map((r) => [r.ticker, r]));
  const inBlocks = new Set([...(data?.selection ?? []), ...(data?.remaining ?? [])]);
  const selectionRows = (data?.selection ?? []).map((t) => byTicker.get(t)).filter((r): r is ThesisRow => !!r);
  const remainingRows = [
    ...(data?.remaining ?? []).map((t) => byTicker.get(t)).filter((r): r is ThesisRow => !!r),
    ...rows.filter((r) => !inBlocks.has(r.ticker)), // intake not yet partitioned (in-flight run)
  ];

  const status = data?.status ?? 'idle';
  const running = status === 'running' || run.isPending;

  const renderRows = (list: ThesisRow[], block: 'selected' | 'remaining') =>
    list.flatMap((row) => {
      const isOpen = expanded === row.ticker && row.state === 'completed';
      const pending = IN_FLIGHT.has(row.state);
      const nodes = [
        <tr
          key={row.ticker}
          className="stage-row"
          onClick={() => row.state === 'completed' && setExpanded(isOpen ? null : row.ticker)}
        >
          <td>
            <TickerLink ticker={row.ticker} />
          </td>
          <td>{row.company_name || '—'}</td>
          <td className="num">{pending ? <PendingValue /> : fmtPrice(row.price)}</td>
          <td className="num">{pending ? <PendingValue /> : fmtPrice(row.fair_value)}</td>
          <td
            className="num"
            style={{
              fontWeight: 600,
              color:
                row.expected_return_pct == null
                  ? undefined
                  : row.expected_return_pct >= 0
                    ? 'var(--positive)'
                    : 'var(--negative)',
            }}
          >
            {pending ? <PendingValue /> : fmtPct(row.expected_return_pct)}
          </td>
          <td>
            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
              <StateCue state={row.state} />
              {row.capped && row.state === 'completed' && (
                <span
                  className="tag-amber"
                  title="Selection ranking capped — weak or unsupported return profile. Still promotable."
                >
                  weak return profile
                </span>
              )}
            </span>
          </td>
          <td style={{ textAlign: 'right' }}>
            <MoveButton
              kind={block === 'selected' ? 'dismiss' : 'promote'}
              enabled={row.state === 'completed' && !select.isPending}
              busy={select.isPending}
              label={
                block === 'selected'
                  ? `Move ${row.ticker} to remaining theses`
                  : `Add ${row.ticker} to the end of the thesis selection`
              }
              onClick={() => select.mutate({ ticker: row.ticker, action: block === 'selected' ? 'dismiss' : 'promote' })}
            />
          </td>
        </tr>,
      ];
      if (isOpen) {
        nodes.push(
          <ExpandedRow key={`${row.ticker}-detail`} colSpan={COLS}>
            <ThesisDetail row={row} />
          </ExpandedRow>,
        );
      }
      return nodes;
    });

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/runs" className="page-kicker" style={{ textDecoration: 'none' }}>← Runs · Workflow · Stage 2</Link>
          <h1 className="page-title">Thesis</h1>
          <div className="page-subtitle">
            {rows.length > 0
              ? `Intake ${rows.length} from Screener handoff${data?.selection_count ? ` · selection target ${data.selection_count}` : ''}`
              : 'Generates a completed thesis for every candidate in the Screener handoff.'}
          </div>
        </div>
        <button className="btn btn-accent" onClick={() => run.mutate()} disabled={running || rows.length === 0}>
          {running ? 'Generating theses…' : 'Run Thesis'}
        </button>
      </div>

      {status === 'running' && (
        <RunningBanner label="Generating completed theses for the intake — rows fill in as items finish…" />
      )}
      {status === 'failed' && <RunFailedBanner />}
      {run.isError && <RunFailedBanner error={(run.error as Error).message} />}

      {isLoading ? (
        <div className="stage-empty">Loading thesis state…</div>
      ) : rows.length === 0 ? (
        <div className="stage-empty">
          No thesis intake yet this session. Hand off Top Picks from the Screener (or run the full pipeline) to populate it.
        </div>
      ) : (
        <>
          <StageBlock
            variant="selected"
            title="Thesis Selection"
            count={selectionRows.length}
            head={<Head />}
            emptyText="No theses selected yet — selection fills in when the run completes."
          >
            {renderRows(selectionRows, 'selected')}
          </StageBlock>
          <StageBlock
            variant="remaining"
            title="Remaining Theses"
            count={remainingRows.length}
            head={<Head />}
            emptyText="Every completed thesis is currently in the selection."
          >
            {renderRows(remainingRows, 'remaining')}
          </StageBlock>
        </>
      )}
    </div>
  );
}

export default Thesis;
