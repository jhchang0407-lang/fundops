import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';
import { parseOutput } from '../api/utils';

export function ICReview() {
  const { data, isLoading } = useQuery({
    queryKey: ['ic-reviews'],
    queryFn: async () => {
      const dashboard = await api.dashboard();
      const tickers = Array.from(
        new Set<string>((dashboard?.recent_runs || []).map((run: any) => String(run.ticker)).filter(Boolean)),
      ).slice(0, 12);
      const reviews = await Promise.all(tickers.map(async (ticker) => {
        const review = await api.getICReview(ticker);
        return { run: review, output: parseOutput(review) };
      }));
      return reviews.filter((review) => review.run?.ticker);
    },
  });
  const reviews = data || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <div className="page-kicker">IC Review</div>
          <h1 className="page-title">Approval Gate</h1>
          <div className="page-subtitle">Where the platform stress-tests ideas before they enter the memo layer.</div>
        </div>
      </div>
      <div className="table-shell">
        <table>
          <thead><tr><th>Ticker</th><th>Verdict</th><th className="num">Base</th><th className="num">Bear</th><th className="num">Conv</th><th>Date</th></tr></thead>
          <tbody>
            {!isLoading && reviews.length === 0 && <tr><td colSpan={6} style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>No IC reviews yet.</td></tr>}
            {reviews.map((review: any, i: number) => (
              <tr key={i}>
                <td>
                  <Link to={`/ticker/${review.run.ticker}`} className="ticker">{review.run.ticker}</Link>
                  {review.output?.key_risk && <div className="muted" style={{ marginTop: 4 }}>{review.output.key_risk}</div>}
                </td>
                <td><span className={`badge ${review.run.verdict === 'PASS' ? 'badge-pass' : 'badge-nopass'}`}>{review.run.verdict || '—'}</span></td>
                <td className="num pos">{review.run.scores?.base_return?.toFixed(0) || '—'}%</td>
                <td className="num">{review.run.scores?.bear_return?.toFixed(0) || '—'}%</td>
                <td className="num">{review.run.scores?.conviction || '—'}/5</td>
                <td className="num" style={{ fontSize: 'var(--text-xs)' }}>{review.run.run_at?.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
