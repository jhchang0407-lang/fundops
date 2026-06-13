import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getDashboard,
  getMonitoringDue,
  getRun,
  refreshDashboard,
  refreshMonitoring,
  respondDashboard,
  runPipeline,
} from '../api/client';
import type { ActivityRow, DashboardItem, ResponseSetEntry } from '../api/client';
import { PageHeader } from '../components/PageHeader';

/* ────────────────────────── helpers ────────────────────────── */

function humanize(code: string): string {
  const s = code.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function normalizeResponses(rs?: ResponseSetEntry[]): { code: string; label: string }[] {
  if (!rs) return [];
  return rs
    .map((r) => {
      if (typeof r === 'string') return { code: r, label: humanize(r) };
      const code = r.code ?? r.response ?? '';
      if (!code) return null;
      return { code, label: r.label ?? humanize(code) };
    })
    .filter((r): r is { code: string; label: string } => r !== null);
}

function extractTickers(refs: unknown): string[] {
  const out = new Set<string>();
  const visit = (v: unknown, depth: number) => {
    if (depth > 3 || v == null) return;
    if (typeof v === 'string') {
      if (/^[A-Z]{1,6}(\.[A-Z])?$/.test(v)) out.add(v);
      return;
    }
    if (Array.isArray(v)) {
      v.forEach((x) => visit(x, depth + 1));
      return;
    }
    if (typeof v === 'object') {
      const o = v as Record<string, unknown>;
      if (typeof o.ticker === 'string') out.add(o.ticker);
      if (Array.isArray(o.tickers)) o.tickers.forEach((x) => visit(x, depth + 1));
    }
  };
  visit(refs, 0);
  return [...out].slice(0, 10);
}

function extractConfidence(item: DashboardItem): string | null {
  const refs = item.evidence_refs;
  if (refs && typeof refs === 'object' && !Array.isArray(refs)) {
    const c = (refs as Record<string, unknown>).confidence_label;
    if (typeof c === 'string') return c.replace(/_/g, ' ');
  }
  return null;
}

function fmtWhen(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function isStrategySource(item: DashboardItem): boolean {
  const src = (item.source_type ?? '').toLowerCase();
  return src.includes('proposal') || src.includes('strategy');
}

/* ────────────────────────── item renderers ────────────────────────── */

function ResponseButtons({
  item,
  onRespond,
  busy,
}: {
  item: DashboardItem;
  onRespond: (item: DashboardItem, code: string) => void;
  busy: boolean;
}) {
  const responses = normalizeResponses(item.response_set);
  if (responses.length === 0) return null;
  return (
    <>
      {responses.map((r) => (
        <button
          key={r.code}
          className="resp-btn"
          disabled={busy}
          onClick={() => onRespond(item, r.code)}
        >
          {r.label}
        </button>
      ))}
    </>
  );
}

function DecisionCard({
  item,
  onRespond,
  busyId,
}: {
  item: DashboardItem;
  onRespond: (item: DashboardItem, code: string) => void;
  busyId: string | null;
}) {
  const tickers = extractTickers(item.evidence_refs);
  const confidence = extractConfidence(item);
  const strategy = isStrategySource(item);

  return (
    <div className="dash-item">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
            {item.ticker && (
              <Link to={`/company/${item.ticker}`} className="ticker" style={{ marginRight: 8 }}>
                {item.ticker}
              </Link>
            )}
            {item.title}
          </div>
          {item.body && (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-secondary)',
                marginTop: 4,
                lineHeight: 1.6,
              }}
            >
              {item.body}
            </div>
          )}
          {tickers.length > 0 && (
            <div className="evidence-tickers">
              {tickers.map((t) => (
                <Link key={t} to={`/company/${t}`} className="citation-chip" style={{ textDecoration: 'none' }}>
                  {t}
                </Link>
              ))}
            </div>
          )}
          {item.rank_source && <div className="rank-source">{item.rank_source}</div>}
        </div>
        {confidence && <span className="confidence-chip">{confidence}</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
        {strategy && (
          <Link to="/" className="resp-btn" style={{ textDecoration: 'none' }}>
            Review in Chat
          </Link>
        )}
        <ResponseButtons item={item} onRespond={onRespond} busy={busyId === item.id} />
      </div>
    </div>
  );
}

function ReviewRow({
  item,
  onRespond,
  busyId,
}: {
  item: DashboardItem;
  onRespond: (item: DashboardItem, code: string) => void;
  busyId: string | null;
}) {
  return (
    <div
      style={{
        padding: '8px 0',
        borderBottom: '1px solid rgba(42,43,54,0.7)',
      }}
    >
      <div style={{ fontSize: 'var(--text-sm)' }}>
        {item.ticker && (
          <Link to={`/company/${item.ticker}`} className="ticker" style={{ marginRight: 8 }}>
            {item.ticker}
          </Link>
        )}
        {item.title}
      </div>
      {item.body && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.5 }}>
          {item.body}
        </div>
      )}
      {item.rank_source && <div className="rank-source">{item.rank_source}</div>}
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        <ResponseButtons item={item} onRespond={onRespond} busy={busyId === item.id} />
      </div>
    </div>
  );
}

function AttentionCard({
  item,
  onRespond,
  busyId,
}: {
  item: DashboardItem;
  onRespond: (item: DashboardItem, code: string) => void;
  busyId: string | null;
}) {
  const sev = (item.severity ?? '').toLowerCase();
  const sevClass =
    sev === 'high' || sev === 'critical'
      ? 'dash-attn-high'
      : sev === 'medium'
        ? 'dash-attn-medium'
        : 'dash-attn-low';

  return (
    <div className={`dash-item dash-item-attn ${sevClass}`}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
        {item.ticker && (
          <Link to={`/company/${item.ticker}`} className="ticker" style={{ marginRight: 8 }}>
            {item.ticker}
          </Link>
        )}
        {item.title}
      </div>
      {item.body && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.6 }}>
          {item.body}
        </div>
      )}
      {item.rank_source && <div className="rank-source">{item.rank_source}</div>}
      <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
        <ResponseButtons item={item} onRespond={onRespond} busy={busyId === item.id} />
      </div>
    </div>
  );
}

function Activity({ rows }: { rows: ActivityRow[] }) {
  if (rows.length === 0) return <div className="empty-note">No recent activity.</div>;
  return (
    <div>
      {rows.map((r, i) => (
        <div key={i} className="activity-row">
          <span className="activity-kind">{r.kind.replace(/_/g, ' ')}</span>
          <span style={{ minWidth: 0, color: 'var(--text-secondary)' }}>
            {r.ticker && (
              <Link to={`/company/${r.ticker}`} className="ticker" style={{ marginRight: 6 }}>
                {r.ticker}
              </Link>
            )}
            {r.title}
          </span>
          <span className="activity-time">{fmtWhen(r.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

/* ────────────────────────── page ────────────────────────── */

export default function Dashboard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [monitoringNote, setMonitoringNote] = useState<string | null>(null);
  const [pipelineRunId, setPipelineRunId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });
  const { data: due } = useQuery({ queryKey: ['monitoring-due'], queryFn: getMonitoringDue });

  const pipelineRun = useQuery({
    queryKey: ['run', pipelineRunId],
    queryFn: () => getRun(pipelineRunId!),
    enabled: !!pipelineRunId,
    refetchInterval: (query) => {
      if (query.state.status === 'error') return false; // surfaced below, not polled forever
      return query.state.data?.run?.status === 'running' || query.state.data === undefined ? 2500 : false;
    },
  });
  const runStatus = pipelineRun.isError ? 'failed' : pipelineRun.data?.run?.status;

  useEffect(() => {
    if (pipelineRunId && (runStatus === 'completed' || runStatus === 'failed')) {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['monitoring-due'] });
    }
  }, [runStatus, pipelineRunId, qc]);

  const respond = useMutation({
    mutationFn: ({ item, code }: { item: DashboardItem; code: string }) =>
      respondDashboard(item.id, code),
    onMutate: ({ item }) => setBusyItemId(item.id),
    onSuccess: (_res, { item, code }) => {
      // "Open" means open the thing — recording the response alone would be
      // an invisible no-op from the user's point of view.
      if (code === 'open') {
        if (item.ticker) navigate(`/company/${item.ticker}`);
        else {
          const refs = Array.isArray(item.evidence_refs) ? item.evidence_refs as Array<Record<string, unknown>> : [];
          const art = refs.find((r) => typeof r.id === 'string' && String(r.id).startsWith('art_'));
          if (art) navigate(`/artifact/${art.id}`);
        }
      }
    },
    onError: (err: Error, { item }) =>
      setMonitoringNote(`Response on “${item.title}” failed: ${err.message} — is the server reachable?`),
    onSettled: () => {
      setBusyItemId(null);
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const checkMonitoring = useMutation({
    mutationFn: refreshMonitoring,
    onSuccess: (res) => {
      const n = res.refreshed?.length ?? 0;
      const full = res.refreshed?.filter((r) => !r.metadata_only).length ?? 0;
      setMonitoringNote(
        n === 0
          ? 'No tickers were due a thesis-health check.'
          : `Checked ${n} ticker${n === 1 ? '' : 's'} — ${full} had new filings and were recomputed; the rest were metadata-only checks.`,
      );
      qc.invalidateQueries({ queryKey: ['monitoring-due'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: Error) => setMonitoringNote(`Check failed: ${err.message}`),
  });

  const refresh = useMutation({
    mutationFn: refreshDashboard,
    onSettled: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });

  const pipeline = useMutation({
    mutationFn: runPipeline,
    onSuccess: (res) => setPipelineRunId(res.run_id),
  });

  const onRespond = (item: DashboardItem, code: string) => respond.mutate({ item, code });

  const needsDecision = data?.needs_decision ?? [];
  const pressure = data?.portfolio_review?.pressure ?? [];
  const opportunities = data?.portfolio_review?.opportunities ?? [];
  const needsAttention = data?.needs_attention ?? [];
  const activity = data?.recent_activity ?? [];

  const steps = pipelineRun.data?.steps ?? [];
  const doneSteps = steps.filter((s) => s.status === 'completed').length;

  return (
    <div>
      <PageHeader
        sectionLabel="Inbox"
        title="Inbox"
        subtitle="Decisions and attention, pre-analyzed by your workflows — nothing here trades for you."
        actions={
          <>
            <button
              className="btn"
              disabled={checkMonitoring.isPending}
              onClick={() => checkMonitoring.mutate()}
              title="Metadata-gated: full recompute only where new filings exist"
            >
              {checkMonitoring.isPending
                ? 'Checking…'
                : `Check for thesis updates${due != null ? ` · ${due.due} due` : ''}`}
            </button>
            <button
              className="btn"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
            >
              {refresh.isPending ? 'Refreshing…' : 'Refresh'}
            </button>
            <button
              className="btn btn-accent"
              disabled={pipeline.isPending || runStatus === 'running'}
              onClick={() => pipeline.mutate()}
            >
              {runStatus === 'running' ? 'Pipeline running…' : 'Run full pipeline'}
            </button>
          </>
        }
      />

      {monitoringNote && (
        <div className="banner" style={{ marginBottom: 10, color: 'var(--text-secondary)' }}>
          {monitoringNote}
        </div>
      )}

      {pipelineRunId && (
        <div
          className={`banner ${runStatus === 'completed' ? 'banner-positive' : runStatus === 'failed' ? '' : 'banner-warning'}`}
          style={{
            marginBottom: 10,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            ...(runStatus === 'failed'
              ? { borderColor: 'rgba(234,67,53,0.3)', background: 'rgba(234,67,53,0.06)' }
              : {}),
          }}
        >
          {runStatus === 'running' || runStatus == null ? (
            <>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  animation: 'pulse 1.2s ease-in-out infinite',
                  flexShrink: 0,
                }}
              />
              <span>
                Pipeline running
                {steps.length > 0 ? ` — ${doneSteps}/${steps.length} steps complete` : '…'}
              </span>
            </>
          ) : runStatus === 'completed' ? (
            <span>Pipeline completed. Stage pages have fresh output.</span>
          ) : (
            <span>
              Pipeline failed{pipelineRun.data?.run?.error ? `: ${pipelineRun.data.run.error}` : '.'}{' '}
              Operational failure — no investment judgment was recorded.
            </span>
          )}
          <button
            onClick={() => setPipelineRunId(null)}
            style={{
              marginLeft: 'auto',
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            ×
          </button>
        </div>
      )}

      {isLoading && <div className="empty-note">Loading inbox…</div>}

      {/* ── Decisions ── */}
      <div className="dash-section">
        <div className="section-label">
          Decisions{needsDecision.length > 0 ? ` · ${needsDecision.length}` : ''}
        </div>
        {needsDecision.length === 0 ? (
          <div className="empty-note">No unresolved decisions.</div>
        ) : (
          needsDecision.map((item) => (
            <DecisionCard key={item.id} item={item} onRespond={onRespond} busyId={busyItemId} />
          ))
        )}
      </div>

      {/* ── Portfolio review ── */}
      <div className="dash-section">
        <div className="section-label">Portfolio review</div>
        <div className="two-col">
          <div className="card">
            <div className="card-title">Positions under pressure</div>
            {pressure.length === 0 ? (
              <div className="empty-note">No held positions need review.</div>
            ) : (
              pressure.map((item) => (
                <ReviewRow key={item.id} item={item} onRespond={onRespond} busyId={busyItemId} />
              ))
            )}
          </div>
          <div className="card">
            <div className="card-title">Constitution-fit opportunities</div>
            {opportunities.length === 0 ? (
              <div className="empty-note">No constitution-fit opportunities surfaced.</div>
            ) : (
              opportunities.map((item) => (
                <ReviewRow key={item.id} item={item} onRespond={onRespond} busyId={busyItemId} />
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Attention ── */}
      <div className="dash-section">
        <div className="section-label">
          Attention{needsAttention.length > 0 ? ` · ${needsAttention.length}` : ''}
        </div>
        {needsAttention.length === 0 ? (
          <div className="empty-note">Nothing needs attention.</div>
        ) : (
          needsAttention.map((item) => (
            <AttentionCard key={item.id} item={item} onRespond={onRespond} busyId={busyItemId} />
          ))
        )}
      </div>

      {/* ── Recent activity ── */}
      <div className="dash-section">
        <div className="section-label">Recent activity</div>
        <Activity rows={activity} />
      </div>
    </div>
  );
}
