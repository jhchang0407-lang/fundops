import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function Memo() {
  const { ticker } = useParams();
  const [mode, setMode] = useState<'research' | 'investment'>('research');
  const { data } = useQuery({
    queryKey: ['memo', ticker],
    queryFn: () => api.getMemo(ticker || ''),
    enabled: !!ticker,
  });

  const memos = data?.memos || [];
  const currentMemo = memos.find((m: any) => m.run_type === mode);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 600 }}>{ticker || 'Memo'}</h1>
        <div style={{ display: 'flex', gap: 4 }}>
          <button className="btn" style={{ fontSize: 10 }}>PDF</button>
          <button className="btn" style={{ fontSize: 10 }}>MD</button>
        </div>
      </div>

      {/* Mode toggle */}
      <div style={{ display: 'flex', background: 'var(--bg-tertiary)', borderRadius: 4, padding: 2, marginBottom: 10 }}>
        <button onClick={() => setMode('research')} style={{
          flex: 1, padding: '4px 12px', borderRadius: 3, border: 'none',
          background: mode === 'research' ? 'var(--bg-elevated)' : 'none',
          color: mode === 'research' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontFamily: 'var(--font-ui)', fontSize: 'var(--text-sm)', cursor: 'pointer',
        }}>Research Report</button>
        <button onClick={() => setMode('investment')} style={{
          flex: 1, padding: '4px 12px', borderRadius: 3, border: 'none',
          background: mode === 'investment' ? 'var(--bg-elevated)' : 'none',
          color: mode === 'investment' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontFamily: 'var(--font-ui)', fontSize: 'var(--text-sm)', cursor: 'pointer',
        }}>Investment Memo</button>
      </div>

      {!ticker && <div className="card"><p style={{ color: 'var(--text-muted)' }}>Select a ticker from the Library to view its memo.</p></div>}

      {currentMemo ? (
        <div className="card">
          <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-ui)', fontSize: 'var(--text-sm)', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {currentMemo.full_output?.content || currentMemo.summary || 'No content available'}
          </div>
        </div>
      ) : ticker ? (
        <div className="card"><p style={{ color: 'var(--text-muted)' }}>No {mode} memo found for {ticker}. Generate one from the Ticker Detail page.</p></div>
      ) : null}
    </div>
  );
}
