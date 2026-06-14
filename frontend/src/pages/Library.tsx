/**
 * Library — everything retained: dossiers (search a ticker), conversations
 * as durable threads, and what the assistant remembers about you (readable,
 * forgettable). Selection persists in the URL (?t=AAPL).
 */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  forgetChatMemory,
  getChatHistory,
  getChatMemory,
  getChatThreads,
  librarySuggest,
} from '../api/client';
import { CompanyDossier } from './CompanyPage';

function SearchPanel({
  selected,
  onSelect,
  collapsed,
  onToggle,
}: {
  selected: string | null;
  onSelect: (ticker: string) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const [q, setQ] = useState('');
  const query = q.trim().toUpperCase();

  const { data, isFetching } = useQuery({
    queryKey: ['library-suggest', query],
    queryFn: () => librarySuggest(query),
    enabled: query.length > 0,
    staleTime: 30_000,
  });

  const matches = query.length > 0 ? (data?.matches ?? []) : [];

  const choose = (ticker: string) => {
    onSelect(ticker.toUpperCase());
    setQ('');
  };

  const onEnter = () => {
    if (!query) return;
    const exact = matches.find((m) => m.ticker.toUpperCase() === query);
    if (exact) choose(exact.ticker);
    else if (matches.length === 1) choose(matches[0].ticker);
    else choose(query); // unknown tickers resolve to the no-result state
  };

  if (collapsed) {
    return (
      <div className="library-search-panel collapsed">
        <button className="btn btn-ghost" onClick={onToggle} title="Expand search panel" aria-label="Expand search panel">
          🔍
        </button>
      </div>
    );
  }

  return (
    <div className="library-search-panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span className="section-label" style={{ marginBottom: 0, flex: 1 }}>
          Ticker Search
        </span>
        <button className="btn btn-ghost" onClick={onToggle} title="Collapse search panel" aria-label="Collapse search panel" style={{ padding: '2px 8px' }}>
          «
        </button>
      </div>
      <input
        className="field"
        style={{ fontFamily: 'var(--font-data)', letterSpacing: '0.05em', textTransform: 'uppercase' }}
        placeholder="e.g. AAPL"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onEnter();
        }}
        aria-label="Search ticker"
      />
      <div style={{ marginTop: 8 }}>
        {query.length > 0 && matches.length === 0 && !isFetching && (
          <div className="empty-note" role="status" style={{ padding: '8px', lineHeight: 1.5 }}>
            <b>No retained FundOps history for “{query}”.</b>
            <br />
            Only tickers the platform has researched, screened, or held resolve here. Run a
            screener or thesis to start building history for it.
          </div>
        )}
        {matches.map((m) => (
          <button key={m.ticker} className="suggest-item" onClick={() => choose(m.ticker)}>
            <span className="ticker">{m.ticker}</span>
            <span className="muted" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {m.name ?? ''}
            </span>
          </button>
        ))}
      </div>
      {selected && (
        <div className="inline-metadata" style={{ marginTop: 14 }}>
          <span>
            viewing <span className="ticker">{selected}</span>
          </span>
        </div>
      )}
      <div className="muted" style={{ fontSize: 'var(--text-xs)', marginTop: 14, lineHeight: 1.6 }}>
        Only tickers with retained FundOps history resolve.
      </div>
    </div>
  );
}

function fmtAgo(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function ThreadRow({ thread, isLatest }: { thread: import('../api/client').ChatThreadSummary; isLatest: boolean }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ['thread-history', thread.id],
    queryFn: () => getChatHistory(thread.id),
    enabled: open,
  });
  const title = (thread.first_user_message ?? 'Empty conversation').slice(0, 110);
  return (
    <div style={{ borderBottom: '1px solid var(--hairline)', padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
            color: 'var(--text-primary)', fontSize: 'var(--text-sm)', padding: 0, flex: 1, minWidth: 0,
          }}
          title={open ? 'Collapse transcript' : 'Read transcript'}
        >
          {title}
        </button>
        <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', flexShrink: 0 }}>
          {thread.message_count} msgs · {fmtAgo(thread.last_at ?? thread.started_at)}
        </span>
        {isLatest && (
          <Link to="/" className="wiring-chip" style={{ flexShrink: 0 }} title="The live thread continues on Home">
            continue →
          </Link>
        )}
      </div>
      {open && (
        <div className="card" style={{ marginTop: 8, maxHeight: 320, overflowY: 'auto' }}>
          {(data?.messages ?? []).map((m, i) => (
            <div key={i} style={{ padding: '4px 0', fontSize: 'var(--text-xs)' }}>
              <span style={{ color: m.role === 'user' ? 'var(--teal-ink)' : 'var(--text-muted)', fontFamily: 'var(--font-data)', marginRight: 6 }}>
                {m.role === 'user' ? 'you' : 'fundops'}
              </span>
              <span style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>{m.content}</span>
            </div>
          ))}
          {data && data.messages.length === 0 && <div className="empty-note">No messages retained.</div>}
        </div>
      )}
    </div>
  );
}

function ConversationsPanel() {
  const { data } = useQuery({ queryKey: ['chat-threads'], queryFn: () => getChatThreads(30), retry: 1 });
  const threads = data?.threads ?? [];
  return (
    <div className="card">
      <div className="card-title">Conversations</div>
      {threads.length === 0 ? (
        <div className="empty-note">No conversations yet — start one on Home.</div>
      ) : (
        threads.map((t, i) => <ThreadRow key={t.id} thread={t} isLatest={i === 0} />)
      )}
      <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
        Threads are retained as evidence — the latest continues on Home; older ones are read-only.
      </div>
    </div>
  );
}

function MemoryPanel() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ['chat-memory'], queryFn: getChatMemory, retry: 1 });
  const forget = useMutation({
    mutationFn: forgetChatMemory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['chat-memory'] }),
  });
  const records = data?.memory ?? [];
  return (
    <div className="card">
      <div className="card-title">What it remembers about you</div>
      {records.length === 0 ? (
        <div className="empty-note">
          Nothing yet — preferences you state in conversation (“avoid tobacco”, “I care about moats”) are kept here.
        </div>
      ) : (
        records.map((m) => (
          <div key={m.id} style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--hairline)' }}>
            <span className="mode-chip" style={{ background: 'var(--purple-bg)', color: 'var(--purple-ink)', flexShrink: 0 }}>
              {m.kind}
            </span>
            <span style={{ flex: 1, fontSize: 'var(--text-sm)' }}>
              {typeof m.content?.text === 'string' ? m.content.text : JSON.stringify(m.content)}
            </span>
            <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', flexShrink: 0 }}>
              {m.source === 'chat' ? 'from conversation' : m.source ?? ''} · {fmtAgo(m.created_at)}
            </span>
            <button
              className="btn"
              style={{ padding: '2px 9px', fontSize: 'var(--text-xs)', flexShrink: 0 }}
              disabled={forget.isPending}
              onClick={() => forget.mutate(m.id)}
            >
              forget
            </button>
          </div>
        ))
      )}
      <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
        Read back into every strategy conversation. Forgetting removes it from prompts immediately; the record itself stays in the append-only history.
      </div>
    </div>
  );
}

export default function Library() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);
  const selected = (searchParams.get('t') ?? '').trim().toUpperCase() || null;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-kicker">Library</div>
          <h1 className="page-title">Library</h1>
          <div className="page-subtitle">
            Everything retained: dossiers, conversations, and what the assistant remembers about you.
          </div>
        </div>
      </div>
      <div className="library-shell">
        <SearchPanel
          selected={selected}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          onSelect={(t) => setSearchParams({ t })}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          {selected ? (
            <CompanyDossier ticker={selected} />
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              <ConversationsPanel />
              <MemoryPanel />
              <div className="empty-note" style={{ textAlign: 'center' }}>
                Search a ticker on the left to open its dossier — only tickers with retained FundOps history resolve.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
