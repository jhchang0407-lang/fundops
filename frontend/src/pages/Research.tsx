/**
 * Research Hub (/research) — industry/sector/theme work, distinct from the
 * per-company funnel. v1 is deterministic: a sector→industry browser over
 * identity data, per-group dashboards aggregated from retained observations,
 * watchlists/themes, and (Phase 4) bounded AI research runs that produce
 * cited note artifacts.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  createWatchlist,
  deleteWatchlist,
  exportUrls,
  getIndustryDashboard,
  getResearchNotes,
  getSectors,
  getThemeDashboard,
  listWatchlists,
  runThematicResearch,
  searchFilingsFulltext,
  startResearchRun,
} from '../api/client';
import type { FulltextHit, IndustryDashboard, Watchlist } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { fmtDate, fmtMetric, humanizeLabel } from '../utils/formatFinancials';

type Selection =
  | { type: 'industry'; sector?: string; industry?: string; label: string }
  | { type: 'theme'; id: string; label: string }
  | null;

/* ────────────────────────── left rail ────────────────────────── */

function SectorBrowser({
  selected,
  onSelect,
}: {
  selected: Selection;
  onSelect: (s: Selection) => void;
}) {
  const { data } = useQuery({ queryKey: ['research-sectors'], queryFn: getSectors });
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const sectors = data?.sectors ?? [];
  if (!sectors.length) {
    return (
      <div className="empty-note">
        Sector data fills as the universe syncs identity information.
      </div>
    );
  }
  return (
    <div>
      {sectors.map((s) => (
        <div key={s.sector}>
          <button
            className="rail-item"
            style={{
              display: 'flex', width: '100%', justifyContent: 'space-between',
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '5px 8px', color: 'var(--text-primary)', fontSize: 'var(--text-sm)',
            }}
            onClick={() => {
              setOpen(open === s.sector ? null : s.sector);
              setFilter('');
              onSelect({ type: 'industry', sector: s.sector, label: s.sector });
            }}
          >
            <span>{open === s.sector ? '▾' : '▸'} {s.sector}</span>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>{s.count}</span>
          </button>
          {open === s.sector && s.industries.length > 8 && (
            <input
              className="field"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={`Filter ${s.industries.length} industries…`}
              aria-label={`Filter industries in ${s.sector}`}
              style={{ margin: '4px 8px 6px 22px', width: 'calc(100% - 30px)', fontSize: 'var(--text-xs)' }}
            />
          )}
          {open === s.sector &&
            s.industries
              .filter((i) => i.industry.toLowerCase().includes(filter.toLowerCase()))
              .map((i) => (
              <button
                key={i.industry}
                style={{
                  display: 'flex', width: '100%', justifyContent: 'space-between',
                  background:
                    selected?.type === 'industry' && selected.industry === i.industry
                      ? 'var(--bg-elevated)' : 'none',
                  border: 'none', cursor: 'pointer', padding: '4px 8px 4px 22px',
                  color: 'var(--text-secondary)', fontSize: 'var(--text-xs)',
                  borderRadius: 'var(--radius-sm)',
                }}
                onClick={() => onSelect({ type: 'industry', industry: i.industry, label: i.industry })}
              >
                <span style={{ textAlign: 'left' }}>{i.industry}</span>
                <span style={{ fontFamily: 'var(--font-data)' }}>{i.count}</span>
              </button>
            ))}
        </div>
      ))}
    </div>
  );
}

function ThemesRail({
  selected,
  onSelect,
}: {
  selected: Selection;
  onSelect: (s: Selection) => void;
}) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ['watchlists'], queryFn: listWatchlists });
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [tickers, setTickers] = useState('');
  const create = useMutation({
    mutationFn: () =>
      createWatchlist(name.trim(), 'theme',
        tickers.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlists'] });
      setAdding(false);
      setName('');
      setTickers('');
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlists'] }),
  });
  const lists = data?.watchlists ?? [];
  return (
    <div>
      {lists.map((w: Watchlist) => (
        <div key={w.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <button
            style={{
              flex: 1, display: 'flex', justifyContent: 'space-between',
              background: selected?.type === 'theme' && selected.id === w.id ? 'var(--bg-elevated)' : 'none',
              border: 'none', cursor: 'pointer', padding: '4px 8px',
              color: 'var(--text-secondary)', fontSize: 'var(--text-xs)',
              borderRadius: 'var(--radius-sm)',
            }}
            onClick={() => onSelect({ type: 'theme', id: w.id, label: w.name })}
          >
            <span>{w.name}</span>
            <span style={{ fontFamily: 'var(--font-data)' }}>{w.tickers.length}</span>
          </button>
          <button
            title="Delete list"
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            onClick={() => remove.mutate(w.id)}
          >
            ×
          </button>
        </div>
      ))}
      {adding ? (
        <div style={{ padding: '6px 8px', display: 'grid', gap: 6 }}>
          <input className="editor-input" style={{ width: '100%' }} placeholder="Theme name" value={name}
                 onChange={(e) => setName(e.target.value)} />
          <input className="editor-input" style={{ width: '100%' }} placeholder="Tickers (AAPL MSFT …)" value={tickers}
                 onChange={(e) => setTickers(e.target.value)} />
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-accent" disabled={!name.trim() || create.isPending}
                    onClick={() => create.mutate()}>
              Save
            </button>
            <button className="btn btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
          </div>
          {create.isError && (
            <div style={{ fontSize: 10, color: 'var(--negative)' }}>
              {(create.error as Error).message}
            </div>
          )}
        </div>
      ) : (
        <button
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px 8px', color: 'var(--accent)', fontSize: 'var(--text-xs)' }}
          onClick={() => setAdding(true)}
        >
          + New theme / watchlist
        </button>
      )}
    </div>
  );
}

function NotesRail() {
  const { data } = useQuery({ queryKey: ['research-notes'], queryFn: getResearchNotes });
  const notes = data?.notes ?? [];
  if (!notes.length) {
    return <div style={{ padding: '2px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
      Research runs produce cited notes here.
    </div>;
  }
  return (
    <div>
      {notes.slice(0, 8).map((n) => (
        <Link key={n.id} to={`/artifact/${n.id}`}
              style={{ display: 'block', padding: '4px 8px', fontSize: 'var(--text-xs)',
                       color: 'var(--text-secondary)', textDecoration: 'none', lineHeight: 1.4 }}>
          {n.title}
          <span style={{ display: 'block', color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 10 }}>
            {humanizeLabel(n.kind)} · {fmtDate(n.created_at)}
          </span>
        </Link>
      ))}
    </div>
  );
}

/* ────────────────────────── dashboard body ────────────────────────── */

const AGG_LABELS: [string, string][] = [
  ['roic', 'Median ROIC'],
  ['gross_margin', 'Median gross margin'],
  ['revenue_growth', 'Median revenue growth'],
  ['momentum_6m', 'Median 6M momentum'],
];

function GroupDashboard({ selection }: { selection: Selection }) {
  const navigate = useNavigate();
  const [sortBy, setSortBy] = useState('market_cap');
  const [runNotice, setRunNotice] = useState<string | null>(null);
  const enabled = selection != null;
  const { data, isPending, isError, error } = useQuery<IndustryDashboard>({
    queryKey: ['research-dash', selection],
    queryFn: () =>
      selection!.type === 'industry'
        ? getIndustryDashboard({ sector: selection!.sector, industry: selection!.industry })
        : getThemeDashboard(selection!.id),
    enabled,
  });
  const run = useMutation({
    mutationFn: (kind: string) =>
      startResearchRun(
        selection!.type === 'industry'
          ? { kind, sector: selection!.sector, industry: selection!.industry }
          : { kind, watchlist_id: selection!.id },
      ),
    onSuccess: (res) => navigate(`/artifact/${res.artifact_id}`),
    onError: (err: Error) => setRunNotice(err.message),
  });

  if (!selection) {
    return (
      <div className="stage-empty">
        Pick a sector, industry, or theme on the left — dashboards aggregate retained
        local data; nothing is fetched on view.
      </div>
    );
  }
  if (isError) {
    return (
      <div className="stage-empty">
        Could not load this dashboard: {error instanceof Error ? error.message : 'request failed'}
      </div>
    );
  }
  if (isPending || !data) return <div className="stage-empty">Aggregating…</div>;

  const constituents = [...data.constituents].sort((a, b) => {
    const av = a[sortBy] as number | null | undefined;
    const bv = b[sortBy] as number | null | undefined;
    return (bv ?? -Infinity) - (av ?? -Infinity);
  });

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontFamily: 'var(--font-display)' }}>
          {data.group}
        </h2>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          {data.size} companies · {data.with_data} with data · {data.insider_buys_90d} insider buys (90d)
        </span>
        <a className="btn btn-ghost" style={{ marginLeft: 'auto' }}
           href={selection.type === 'industry'
             ? exportUrls.industry({ sector: selection.sector, industry: selection.industry })
             : '#'}
           aria-disabled={selection.type !== 'industry'}>
          CSV
        </a>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        {AGG_LABELS.map(([metric, label]) => {
          const agg = data.aggregates[metric];
          return (
            <div className="kpi-card" key={metric}>
              <div className="kpi-label">{label}</div>
              <div className="kpi-value num" style={{ textAlign: 'left' }}>
                {agg?.median == null ? '—' : fmtMetric(metric, agg.median)}
              </div>
              {agg?.p25 != null && agg?.p75 != null && (
                <div className="kpi-detail">
                  p25 {fmtMetric(metric, agg.p25)} · p75 {fmtMetric(metric, agg.p75)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {(data.pe_distribution.length > 0 || data.margin_trend.length > 1) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginBottom: 12 }}>
          {data.pe_distribution.length > 0 && (
            <div className="card" style={{ padding: '12px 14px' }}>
              <div className="card-title">Valuation distribution · P/E</div>
              <ResponsiveContainer width="100%" height={130}>
                <BarChart data={data.pe_distribution} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="bucket" axisLine={false} tickLine={false}
                         tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
                  <YAxis allowDecimals={false} width={24} axisLine={false} tickLine={false}
                         tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
                  <ChartTooltip
                    cursor={{ fill: 'var(--bg-elevated)' }}
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-data)', fontSize: 11 }} />
                  <Bar dataKey="count" name="Companies" fill="var(--accent-muted)" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {data.margin_trend.length > 1 && (
            <div className="card" style={{ padding: '12px 14px' }}>
              <div className="card-title">Median gross margin by fiscal year</div>
              <ResponsiveContainer width="100%" height={130}>
                <LineChart data={data.margin_trend} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <XAxis dataKey="year" axisLine={false} tickLine={false}
                         tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
                  <YAxis width={36} axisLine={false} tickLine={false}
                         tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                         domain={['auto', 'auto']}
                         tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }} />
                  <ChartTooltip
                    formatter={(v) => `${((v as number) * 100).toFixed(1)}%`}
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-data)', fontSize: 11 }} />
                  <Line type="monotone" dataKey="median" name="Median margin" stroke="var(--accent)"
                        strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      <div className="card" style={{ padding: '12px 14px', marginBottom: 12 }}>
        <div className="card-title">Launch a research run</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 8 }}>
          {([
            ['industry_note', 'Industry note',
             "Fan out across this group's filings: strategy, margins, capex cycles."],
            ['peer_deep_dive', 'Peer deep-dive',
             'Head-to-head: business model, unit economics, momentum, valuation.'],
            ['fulltext', 'Thematic filing search',
             'SEC full text: who mentions drones, tariffs, GLP-1 — anything.'],
            ['risk_landscape', 'Risk landscape',
             "What this group says it's afraid of, and what changed this year."],
          ] as const).map(([kind, title, desc]) => (
            <button
              key={kind}
              disabled={run.isPending && kind !== 'fulltext'}
              onClick={() => {
                if (kind === 'fulltext') {
                  const input = document.getElementById('fulltext-query') as HTMLInputElement | null;
                  input?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  input?.focus();
                } else {
                  run.mutate(kind);
                }
              }}
              style={{
                textAlign: 'left', cursor: 'pointer', padding: '10px 12px',
                background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)', color: 'var(--text-primary)',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 3 }}>{title}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{desc}</div>
            </button>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
          Every claim cited to a filing section · produces a versioned artifact in your library
        </div>
        {run.isPending && (
          <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Gathering metrics and filing excerpts, writing the note…
          </div>
        )}
        {runNotice && (
          <div className="banner banner-warning" style={{ marginTop: 8, fontSize: 'var(--text-xs)' }}>
            {runNotice}
          </div>
        )}
      </div>

      <div className="table-shell">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Company</th>
              {data.constituent_metrics.map((m) => (
                <th
                  key={m}
                  style={{ textAlign: 'right', cursor: 'pointer', whiteSpace: 'nowrap' }}
                  onClick={() => setSortBy(m)}
                  title="Sort by this metric"
                >
                  {humanizeLabel(m)}{sortBy === m ? ' ↓' : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {constituents.slice(0, 50).map((c) => (
              <tr key={String(c.ticker)}>
                <td style={{ fontFamily: 'var(--font-data)' }}>
                  <Link to={`/company/${c.ticker}`}>{String(c.ticker)}</Link>
                </td>
                <td>{String(c.name ?? '')}</td>
                {data.constituent_metrics.map((m) => (
                  <td key={m} style={{ textAlign: 'right', fontFamily: 'var(--font-data)' }}>
                    {fmtMetric(m, c[m] as number | null | undefined)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ────────────────────────── thematic full-text search ────────────────────────── */

function FulltextSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<FulltextHit[] | null>(null);
  const search = useMutation({
    mutationFn: () => searchFilingsFulltext(query.trim()),
    onSuccess: (res) => setHits(res.hits),
  });
  const deep = useMutation({
    mutationFn: () => runThematicResearch(query.trim()),
    onSuccess: (res) => {
      if (res.ok && res.artifact_id) navigate(`/artifact/${res.artifact_id}`);
    },
  });
  const busy = deep.isPending;

  return (
    <div className="card" style={{ padding: '12px 14px', marginBottom: 12 }}>
      <div className="card-title">Thematic deep research</div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
        Name a theme — FundOps discovers the companies via EDGAR full-text, reads each one's
        10-K (Business, Risk Factors, MD&A), and writes a cited market report. SEC filings only.
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          id="fulltext-query"
          className="editor-input"
          style={{ flex: 1 }}
          placeholder='A theme — try "drone market", "GLP-1", "data center power"…'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && query.trim() && !busy) deep.mutate(); }}
        />
        <button className="btn btn-accent" disabled={!query.trim() || busy}
                onClick={() => deep.mutate()}>
          {busy ? 'Researching…' : 'Deep research →'}
        </button>
        <button className="btn btn-ghost" disabled={!query.trim() || search.isPending || busy}
                title="Preview which companies mention this in filings, without the full read"
                onClick={() => search.mutate()}>
          {search.isPending ? 'Searching…' : 'Preview filings'}
        </button>
      </div>

      {busy && (
        <div className="banner banner-positive" style={{ marginTop: 8, fontSize: 'var(--text-xs)', display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="pulse-dot" />
          Discovering companies and reading their 10-Ks — this can take a few minutes on a
          local coding agent; faster with an API provider.
        </div>
      )}
      {deep.isError && (
        <div className="banner banner-warning" style={{ marginTop: 8, fontSize: 'var(--text-xs)' }}>
          {(deep.error as Error).message}
        </div>
      )}
      {deep.data && !deep.data.ok && (
        <div className="empty-note" style={{ marginTop: 8 }}>{deep.data.note}</div>
      )}

      {search.isError && (
        <div className="banner banner-warning" style={{ marginTop: 8, fontSize: 'var(--text-xs)' }}>
          {(search.error as Error).message}
        </div>
      )}
      {hits != null && (
        hits.length === 0 ? (
          <div className="empty-note" style={{ marginTop: 8 }}>
            No filings matched (or EDGAR full-text search is unreachable right now).
          </div>
        ) : (
          <>
            <div style={{ marginTop: 10, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Discovery preview — companies that mention “{query.trim()}” in filings. Run
              deep research above to read their 10-Ks and synthesize a cited report.
            </div>
            <div className="table-shell" style={{ marginTop: 6 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Company</th><th style={{ width: 70 }}>Ticker</th>
                    <th style={{ width: 70 }}>Form</th><th style={{ width: 100 }}>Filed</th>
                    <th style={{ width: 90 }}>Universe</th>
                  </tr>
                </thead>
                <tbody>
                  {hits.slice(0, 12).map((h, i) => (
                    <tr key={i}>
                      <td>{h.company ?? '—'}</td>
                      <td style={{ fontFamily: 'var(--font-data)' }}>
                        {h.ticker && h.known
                          ? <Link to={`/company/${h.ticker}`}>{h.ticker}</Link>
                          : h.ticker ?? '—'}
                      </td>
                      <td style={{ fontFamily: 'var(--font-data)' }}>{h.form ?? '—'}</td>
                      <td style={{ fontFamily: 'var(--font-data)' }}>{h.filed ?? '—'}</td>
                      <td style={{ fontSize: 'var(--text-xs)', color: h.in_universe ? 'var(--positive)' : 'var(--text-muted)' }}>
                        {h.in_universe ? 'in universe' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
    </div>
  );
}

/* ────────────────────────── page ────────────────────────── */

export default function Research() {
  const [selection, setSelection] = useState<Selection>(null);
  return (
    <div>
      <PageHeader
        sectionLabel="Markets"
        title="Markets"
        subtitle="Industry, sector, and thematic work over your retained local data — with bounded, cited AI research runs."
      />
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <aside style={{ width: 230, flexShrink: 0 }}>
          <div className="card" style={{ padding: '10px 8px', marginBottom: 10 }}>
            <div className="card-title" style={{ padding: '0 8px' }}>Browse</div>
            <SectorBrowser selected={selection} onSelect={setSelection} />
          </div>
          <div className="card" style={{ padding: '10px 8px', marginBottom: 10 }}>
            <div className="card-title" style={{ padding: '0 8px' }}>Themes &amp; watchlists</div>
            <ThemesRail selected={selection} onSelect={setSelection} />
          </div>
          <div className="card" style={{ padding: '10px 8px' }}>
            <div className="card-title" style={{ padding: '0 8px' }}>Recent notes</div>
            <NotesRail />
          </div>
        </aside>
        <main style={{ flex: 1, minWidth: 0 }}>
          <FulltextSearch />
          <GroupDashboard selection={selection} />
        </main>
      </div>
    </div>
  );
}
