import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { parseOutput } from '../api/utils';

async function loadResearchRows() {
  const dashboard = await api.dashboard();
  const recentRuns = dashboard?.recent_runs || [];
  const tickers = Array.from(
    new Set<string>(
      recentRuns
        .map((run: any) => String(run.ticker))
        .filter((ticker: string) => !!ticker),
    ),
  ).slice(0, 12);

  const rows = await Promise.all(tickers.map(async (ticker) => {
    const [thesisResp, icResp] = await Promise.allSettled([api.getThesis(ticker), api.getICReview(ticker)]);
    const thesisRun = thesisResp.status === 'fulfilled' ? thesisResp.value : null;
    const icRun = icResp.status === 'fulfilled' ? icResp.value : null;
    const thesis = parseOutput(thesisRun);
    const ic = parseOutput(icRun);
      return {
        ticker,
        thesisRun,
        icRun,
        thesis,
        ic,
    };
  }));

  return rows.filter((row) => row.thesisRun?.ticker || row.icRun?.ticker);
}

function formatPct(value: number | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  return `${Number(value).toFixed(1)}%`;
}

export function Thesis() {
  const { data, isLoading } = useQuery({ queryKey: ['research-board'], queryFn: loadResearchRows });
  const rows = data || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <div className="page-kicker">Research</div>
          <h1 className="page-title">Thesis + IC Pipeline</h1>
          <div className="page-subtitle">Validated ideas, IC verdicts, and what still needs memo-level work.</div>
        </div>
      </div>

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th className="num">Expected</th>
              <th className="num">Discount</th>
              <th>IC Verdict</th>
              <th className="num">Conviction</th>
              <th>Why It Exists</th>
              <th>Next</th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 28, textAlign: 'center', color: 'var(--text-muted)' }}>
                  No research yet. Run the screener and send names into thesis generation.
                </td>
              </tr>
            )}
            {rows.map((row, index) => {
              const thesis = row.thesis;
              const ic = row.ic;
              const verdict = row.icRun?.verdict || ic?.verdict;
              const conviction = row.icRun?.scores?.conviction || ic?.conviction;
              const nextStep = verdict === 'PASS' ? 'Generate memo' : row.icRun?.ticker ? 'Refine or dismiss' : 'Run IC review';
              return (
                <tr key={`${String(row.ticker)}-${index}`}>
                  <td>
                    <div><Link to={`/ticker/${String(row.ticker)}`} className="ticker">{String(row.ticker)}</Link></div>
                    <div className="muted" style={{ marginTop: 4 }}>{thesis.company_name || row.thesisRun?.summary || 'Research in progress'}</div>
                  </td>
                  <td className="num pos">{formatPct(thesis.expected_return || row.thesisRun?.scores?.expected_return)}</td>
                  <td className="num">{formatPct(thesis.discount_pct)}</td>
                  <td>
                    {verdict ? <span className={`badge ${verdict === 'PASS' ? 'badge-pass' : 'badge-nopass'}`}>{verdict}</span> : <span className="badge badge-muted">Pending</span>}
                  </td>
                  <td className="num">{conviction ? `${conviction}/5` : '—'}</td>
                  <td>
                    <div style={{ color: 'var(--text-secondary)' }}>{thesis.variant_view || thesis.web_research?.why_cheap || 'Narrative will appear here once thesis generation finishes.'}</div>
                    {ic?.key_assumptions?.length > 0 && (
                      <div className="inline-metadata" style={{ marginTop: 6 }}>
                        <span>Key assumptions:</span>
                        <span>{ic.key_assumptions.slice(0, 2).join(' · ')}</span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div style={{ color: 'var(--text-primary)' }}>{nextStep}</div>
                    <div className="inline-metadata" style={{ marginTop: 6 }}>
                      <span>{row.icRun?.run_at?.slice(0, 10) || row.thesisRun?.run_at?.slice(0, 10) || '—'}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
