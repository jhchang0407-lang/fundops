import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  clearPipelineData,
  getSettings,
  getSync,
  resetConstitution,
  runDailySync,
  getExportEstimate,
  saveApiKey,
  saveSettings,
  settingsExportUrl,
  startBootstrap,
  testAI,
} from '../api/client';
import type {
  AiUsageRow,
  SettingsResponse,
  SyncBootstrap,
} from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { fmtDate } from '../utils/formatFinancials';

/* ────────────────────────── helpers ────────────────────────── */

function usageRows(data?: SettingsResponse): AiUsageRow[] {
  const u = data?.ai_usage;
  if (!u) return [];
  if (Array.isArray(u)) return u;
  return u.rows ?? [];
}

function fmtInt(n?: number | null): string {
  return n == null ? '—' : n.toLocaleString();
}

function fmtCost(n?: number | null): string {
  return n == null ? '—' : `$${n.toFixed(2)}`;
}

function fmtMb(mb?: number | null): string {
  if (mb == null) return '—';
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

function fmtBytes(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${Math.round(b / 1e6)} MB`;
  return `${Math.round(b / 1e3)} KB`;
}

/** Bootstrap progress → short human line (pct and/or bytes when present). */
function progressText(p: SyncBootstrap['progress'] | undefined): string | null {
  if (p == null) return null;
  if (typeof p === 'number') return `${Math.round(p <= 1 ? p * 100 : p)}%`;
  const parts: string[] = [];
  if (typeof p.pct === 'number') parts.push(`${Math.round(p.pct <= 1 ? p.pct * 100 : p.pct)}%`);
  if (typeof p.bytes === 'number') {
    parts.push(
      typeof p.total_bytes === 'number'
        ? `${fmtBytes(p.bytes)} / ${fmtBytes(p.total_bytes)}`
        : fmtBytes(p.bytes),
    );
  }
  if (typeof p.note === 'string' && p.note) parts.push(p.note);
  return parts.length > 0 ? parts.join(' · ') : null;
}

function HealthChip({
  label, state, ok, detail, onClick,
}: {
  label: string;
  /** Short state word(s) shown after the label — chips must say their state,
   * not just color a dot. */
  state: string;
  ok: boolean | undefined;
  detail?: string;
  onClick?: () => void;
}) {
  const cls =
    ok === undefined
      ? 'health-dot health-dot-muted'
      : ok
        ? 'health-dot health-dot-positive'
        : 'health-dot health-dot-warning';
  return (
    <button
      className="health-chip"
      title={detail}
      onClick={onClick}
      style={{ border: 'none', cursor: onClick ? 'pointer' : 'default', font: 'inherit' }}
    >
      <span className={cls} style={{ marginRight: 0 }} />
      {label}
      <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
        {state}
      </span>
    </button>
  );
}

/* ────────────────────────── market & filings data ────────────────────────── */

function SyncStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi-mini" style={{ textAlign: 'left' }}>
      <div className="kpi-mini-label">{label}</div>
      <div className="kpi-mini-value" style={{ fontSize: 'var(--text-xs)' }}>
        {value}
      </div>
    </div>
  );
}

function MarketDataCard() {
  const qc = useQueryClient();
  const sync = useQuery({
    queryKey: ['sync'],
    queryFn: getSync,
    retry: 1,
    refetchInterval: (query) => {
      const b = query.state.data?.bootstrap;
      return b && !b.done && !b.error && b.stage ? 3000 : false;
    },
  });
  const start = useMutation({
    mutationFn: startBootstrap,
    onSettled: () => qc.invalidateQueries({ queryKey: ['sync'] }),
  });
  const daily = useMutation({
    mutationFn: runDailySync,
    onSettled: () => qc.invalidateQueries({ queryKey: ['sync'] }),
  });

  const status = sync.data;
  const bs = status?.bootstrap;
  const running = start.isPending || (!!bs && !bs.done && !bs.error && !!bs.stage);
  const progress = progressText(bs?.progress);

  return (
    <div className="card">
      <div className="card-title">Market &amp; filings data</div>

      {sync.isError ? (
        <div className="empty-note">
          Sync status unavailable: {(sync.error as Error).message}
        </div>
      ) : bs == null ? (
        <div className="empty-note">Checking data status…</div>
      ) : bs.done ? (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 6,
              marginBottom: 10,
            }}
          >
            <SyncStat
              label="Universe"
              value={`${status?.universe?.name ?? '—'} · ${fmtInt(status?.universe?.count)}`}
            />
            <SyncStat label="Financial facts" value={fmtInt(status?.counts?.facts)} />
            <SyncStat
              label="Price coverage"
              value={`${fmtInt(status?.counts?.prices_tickers)} tickers · ${fmtInt(status?.counts?.prices_rows)} rows`}
            />
            <SyncStat label="Filings" value={fmtInt(status?.counts?.filings)} />
            <SyncStat label="Ownership" value={fmtInt(status?.counts?.ownership)} />
            <SyncStat label="Cache size" value={fmtMb(status?.cache_size_mb)} />
            <SyncStat label="Last daily sync" value={fmtDate(status?.last_daily_tick)} />
            <SyncStat label="Last bulk refresh" value={fmtDate(status?.last_bulk_refresh)} />
          </div>
          <div className="settings-row">
            <span className="settings-key">
              Daily sync
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                Runs on launch and catches up everything since your last session — filings index,
                targeted fact top-ups, price updates, 13D/G holders, and thesis-health recalcs for
                fresh filers. To stay current on days FundOps never opens, schedule{' '}
                <code style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>npm run sync</code>{' '}
                with cron or launchd.
              </div>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {daily.isSuccess && (
                <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--positive)' }}>
                  Sync started
                </span>
              )}
              {daily.isError && (
                <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--negative)' }}>
                  {(daily.error as Error).message}
                </span>
              )}
              <button className="btn" disabled={daily.isPending} onClick={() => daily.mutate()}>
                {daily.isPending ? 'Starting…' : 'Sync now'}
              </button>
            </span>
          </div>
        </>
      ) : running ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}>
          <span className="pulse-dot" />
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
            {bs.stage ? bs.stage.replace(/_/g, ' ') : 'starting download'}
          </span>
          {progress && (
            <span
              style={{
                fontFamily: 'var(--font-data)',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
              }}
            >
              {progress}
            </span>
          )}
        </div>
      ) : (
        <>
          {bs.error && (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-data)',
                color: 'var(--negative)',
                marginBottom: 8,
              }}
            >
              Download failed: {bs.error}
            </div>
          )}
          <div
            style={{
              fontSize: 'var(--text-sm)',
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
              marginBottom: 12,
            }}
          >
            FundOps downloads SEC bulk fundamentals, the filings index, and price history for the
            Russell 2000 universe once — about 2–3 GB on disk — then stays current with ~1–3 MB/day
            index updates. Live APIs are reserved for on-demand research: memo filing reads and
            fresh quotes.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button className="btn btn-accent" disabled={start.isPending} onClick={() => start.mutate()}>
              {bs.error ? 'Retry download' : 'Download market data'}
            </button>
            {start.isError && (
              <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--negative)' }}>
                {(start.error as Error).message}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ────────────────────────── danger confirm modal ────────────────────────── */

function DangerModal({
  title,
  phrase,
  removes,
  preserves,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  phrase: string;
  removes: string[];
  preserves: string[];
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [text, setText] = useState('');
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 460 }}>
        <h3
          style={{
            margin: '0 0 10px',
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-lg)',
            color: 'var(--negative)',
          }}
        >
          {title}
        </h3>
        <div className="draft-section-label" style={{ marginTop: 0 }}>
          This removes
        </div>
        <ul style={{ margin: '0 0 10px', paddingLeft: 18, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          {removes.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
        <div className="draft-section-label" style={{ marginTop: 0 }}>
          This preserves
        </div>
        <ul style={{ margin: '0 0 12px', paddingLeft: 18, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          {preserves.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 6 }}>
          Type{' '}
          <code
            style={{
              fontFamily: 'var(--font-data)',
              color: 'var(--negative)',
              background: 'rgba(234,67,53,0.08)',
              padding: '1px 5px',
              borderRadius: 3,
            }}
          >
            {phrase}
          </code>{' '}
          to confirm.
        </div>
        <input
          className="field"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={phrase}
          style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', marginBottom: 12 }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn"
            disabled={text !== phrase || busy}
            onClick={onConfirm}
            style={{
              background: 'var(--negative)',
              borderColor: 'var(--negative)',
              color: '#fff',
              fontWeight: 600,
            }}
          >
            {busy ? 'Working…' : title}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────── AI provider & models ────────────────────────── */

const AGENT_VALUE = '__agent__';

function fieldStyle(width?: number) {
  return {
    fontFamily: 'var(--font-data)',
    fontSize: 'var(--text-xs)',
    padding: '7px 10px',
    ...(width ? { width } : {}),
  } as const;
}

function AiProviderCard({ data }: { data?: SettingsResponse }) {
  const qc = useQueryClient();
  const config = data?.config;
  const health = data?.health;
  const ai = config?.ai;
  const presets = data?.ai_providers ?? [];
  const keyPresent = data?.ai_key_present ?? {};

  const usingAgent = ai?.provider === 'agent_cli';
  const providerId = (ai?.provider_id as string) ?? 'openai';
  const agentPreset = ai?.agent_cli?.preset === 'codex' ? 'codex' : 'claude';
  const preset = presets.find((p) => p.id === providerId);
  const fastModel = (ai?.model_fast as string) ?? (ai?.fast_model as string) ?? '';
  const deepModel = (ai?.model_deep as string) ?? (ai?.deep_model as string) ?? '';
  const baseUrl = (ai?.base_url as string) ?? '';

  const save = useMutation({
    mutationFn: (updates: Record<string, unknown>) => saveSettings(updates),
    onSettled: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });
  const test = useMutation({ mutationFn: testAI });
  const keyMut = useMutation({
    mutationFn: ({ pid, key }: { pid: string; key: string }) => saveApiKey(pid, key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });

  const [models, setModels] = useState({ fast: '', deep: '' });
  const [url, setUrl] = useState('');
  const [keyInput, setKeyInput] = useState('');
  useEffect(() => {
    setModels({ fast: fastModel, deep: deepModel });
    setUrl(baseUrl);
    setKeyInput('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId, usingAgent, fastModel, deepModel, baseUrl]);

  const pickProvider = (value: string) => {
    if (value === AGENT_VALUE) {
      save.mutate({ ai: { provider: 'agent_cli', agent_cli: { preset: agentPreset } } });
      return;
    }
    const p = presets.find((x) => x.id === value);
    save.mutate({
      ai: {
        provider: 'openai',
        provider_id: value,
        base_url: p?.base_url ?? null,
        model_fast: p?.model_fast ?? '',
        model_deep: p?.model_deep ?? '',
      },
    });
  };

  const modelsDirty = models.fast !== fastModel || models.deep !== deepModel;
  const urlDirty = url !== baseUrl;
  const hasKey = keyPresent[providerId] === true;
  const showKey = !usingAgent && providerId !== 'ollama';
  const keyOptional = providerId === 'custom';

  return (
    <div className="card" id="ai-provider-card">
      <div className="card-title">AI provider &amp; models</div>

      <div className="settings-row">
        <span className="settings-key">
          Provider
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            Who runs FundOps' model work — thesis, IC, memo, strategy. Any OpenAI-compatible API works.
          </div>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <select
            className="field"
            value={usingAgent ? AGENT_VALUE : providerId}
            disabled={save.isPending || config == null}
            onChange={(e) => pickProvider(e.target.value)}
            style={fieldStyle(260)}
          >
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
            <option value={AGENT_VALUE}>My coding agent (Claude Code / Codex)</option>
          </select>
          <button className="btn" disabled={test.isPending} onClick={() => test.mutate()}>
            {test.isPending ? 'Testing…' : 'Test connection'}
          </button>
        </span>
      </div>

      {usingAgent ? (
        <div className="settings-row">
          <span className="settings-key">
            Coding agent
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              Uses your agent's own subscription in headless mode. No API key needed.
            </div>
          </span>
          <select
            className="field"
            value={agentPreset}
            disabled={save.isPending}
            onChange={(e) =>
              save.mutate({ ai: { provider: 'agent_cli', agent_cli: { preset: e.target.value } } })
            }
            style={fieldStyle(220)}
          >
            <option value="claude">Claude Code (claude)</option>
            <option value="codex">Codex (codex)</option>
          </select>
        </div>
      ) : (
        <>
          {showKey && (
            <div className="settings-row">
              <span className="settings-key">
                API key{keyOptional ? ' (optional)' : ''}
                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                  Stored locally in <code style={{ fontFamily: 'var(--font-data)' }}>~/.fundops/credentials.yaml</code> (chmod 600) —
                  never in the workspace or its export. {preset?.env ? `Or set ${preset.env}.` : ''}{' '}
                  {preset?.console_url && (
                    <a href={preset.console_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
                      Get a key →
                    </a>
                  )}
                </div>
              </span>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 360 }}>
                <input
                  className="field"
                  type="password"
                  autoComplete="off"
                  value={keyInput}
                  placeholder={hasKey ? '•••••••• stored — type to replace' : (preset?.key_hint ?? 'paste key')}
                  onChange={(e) => setKeyInput(e.target.value)}
                  style={{ ...fieldStyle(), flex: 1 }}
                />
                <button
                  className="btn"
                  disabled={keyMut.isPending || keyInput.trim() === ''}
                  onClick={() => keyMut.mutate({ pid: providerId, key: keyInput.trim() })}
                >
                  {keyMut.isPending ? 'Saving…' : 'Save'}
                </button>
                {hasKey && (
                  <button
                    className="btn btn-ghost"
                    disabled={keyMut.isPending}
                    title="Remove the stored key"
                    onClick={() => keyMut.mutate({ pid: providerId, key: '' })}
                  >
                    Clear
                  </button>
                )}
              </span>
            </div>
          )}
          {!showKey && !usingAgent && (
            <div className="settings-row">
              <span className="settings-key">API key</span>
              <span className="settings-val" style={{ color: 'var(--text-muted)' }}>
                Not required — runs on your machine
              </span>
            </div>
          )}

          <div className="settings-row">
            <span className="settings-key">Key status</span>
            <span
              className="settings-val"
              style={{ color: health?.ai_configured ? 'var(--positive)' : 'var(--warning)' }}
            >
              {health?.ai_configured ? 'Ready' : showKey ? (hasKey ? 'Ready' : 'No key set') : 'Ready'}
            </span>
          </div>

          <div className="settings-row">
            <span className="settings-key">
              Models
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                Fast = extraction/classification · Deep = thesis, IC, memo, strategy. Use exact model IDs.
              </div>
            </span>
            <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <input
                className="field"
                value={models.fast}
                placeholder="fast model"
                onChange={(e) => setModels((m) => ({ ...m, fast: e.target.value }))}
                style={fieldStyle(180)}
              />
              <input
                className="field"
                value={models.deep}
                placeholder="deep model"
                onChange={(e) => setModels((m) => ({ ...m, deep: e.target.value }))}
                style={fieldStyle(180)}
              />
              <button
                className="btn"
                disabled={save.isPending || !modelsDirty}
                onClick={() => save.mutate({ ai: { model_fast: models.fast.trim(), model_deep: models.deep.trim() } })}
              >
                Save
              </button>
            </span>
          </div>

          <div className="settings-row">
            <span className="settings-key">
              Base URL
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                {providerId === 'custom'
                  ? 'The OpenAI-compatible endpoint to call.'
                  : 'Override only if you proxy this provider; blank uses the default.'}
              </div>
            </span>
            <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 360 }}>
              <input
                className="field"
                value={url}
                placeholder={preset?.base_url ?? 'https://…/v1'}
                onChange={(e) => setUrl(e.target.value)}
                style={{ ...fieldStyle(), flex: 1 }}
              />
              <button
                className="btn"
                disabled={save.isPending || !urlDirty}
                onClick={() => save.mutate({ ai: { base_url: url.trim() || null } })}
              >
                Save
              </button>
            </span>
          </div>
        </>
      )}

      {(test.data || test.error) && (
        <div
          className="settings-row"
          role="status"
          aria-live="polite"
          style={{
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-data)',
            color: test.data?.ok ? 'var(--positive)' : 'var(--negative)',
            justifyContent: 'flex-end',
          }}
        >
          {test.data?.ok
            ? `Connected${test.data.model ? ` — ${test.data.model}` : ''}`
            : `Connection failed${
                test.data?.error
                  ? `: ${test.data.error}`
                  : test.error
                    ? `: ${(test.error as Error).message}`
                    : ''
              }`}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────── automation / schedules ────────────────────────── */

const SCHEDULE_META: Record<string, { label: string; options: string[]; help: string; enforced: boolean }> = {
  data_sync: {
    label: 'Daily catch-up sync',
    options: ['daily', 'manual'],
    help: 'Enforced in-app: while FundOps is open it runs the catch-up tick (filings, prices, recalcs) once a day.',
    enforced: true,
  },
  bulk_refresh: {
    label: 'Full bulk re-extract',
    options: ['weekly', 'monthly', 'manual'],
    help: 'Declared cadence for a full SEC re-extract. Wire it with cron below.',
    enforced: false,
  },
  screener: {
    label: 'Screener',
    options: ['manual', 'daily', 'weekly'],
    help: 'When you intend to re-run the screener. Declared; wire it with cron below.',
    enforced: false,
  },
};

function AutomationCard({ data }: { data?: SettingsResponse }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (updates: Record<string, unknown>) => saveSettings(updates),
    onSettled: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });
  const [copied, setCopied] = useState<false | 'done' | 'error'>(false);

  const raw = data?.config?.schedules;
  const schedules: Record<string, string> = Array.isArray(raw)
    ? Object.fromEntries(raw.map((s) => [String(s.name ?? s.capability ?? ''), String(s.cadence ?? '')]))
    : raw && typeof raw === 'object'
      ? Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, v == null ? '' : String(v)]))
      : {};

  const automation = data?.automation;
  const syncCadence = schedules.data_sync && schedules.data_sync !== 'manual' ? schedules.data_sync : 'daily';
  const cronExpr = automation?.cron?.[syncCadence] ?? automation?.cron?.daily ?? '0 7 * * *';
  const cronLine = automation ? `${cronExpr} cd ${automation.cwd} && ${automation.command}` : '';

  const copy = () => {
    if (!cronLine) return;
    const flash = (state: 'done' | 'error') => {
      setCopied(state);
      setTimeout(() => setCopied(false), state === 'done' ? 1500 : 2500);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(cronLine).then(() => flash('done')).catch(() => flash('error'));
    } else {
      flash('error');
    }
  };

  const names = Object.keys(SCHEDULE_META);

  return (
    <div className="card">
      <div className="card-title">Automation</div>
      {names.map((name) => {
        const meta = SCHEDULE_META[name];
        const value = schedules[name] ?? meta.options[meta.options.length - 1];
        return (
          <div className="settings-row" key={name}>
            <span className="settings-key">
              {meta.label}
              {meta.enforced && (
                <span className="mode-chip" style={{ marginLeft: 6, background: 'var(--teal-bg)', color: 'var(--teal-ink)' }}>
                  in-app
                </span>
              )}
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                {meta.help}
              </div>
            </span>
            <select
              className="field"
              value={value}
              disabled={save.isPending}
              onChange={(e) => save.mutate({ schedules: { [name]: e.target.value } })}
              style={fieldStyle(160)}
            >
              {meta.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
        );
      })}

      <div className="settings-row" style={{ display: 'block' }}>
        <div className="settings-key" style={{ marginBottom: 6 }}>
          Wire OS-level automation
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            To stay current on days you never open FundOps, run the sync from cron. Add this line with{' '}
            <code style={{ fontFamily: 'var(--font-data)' }}>crontab -e</code> (macOS: or a launchd agent).
          </div>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'var(--well)',
            border: '1px solid var(--hairline)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '8px 10px',
          }}
        >
          <code style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', flex: 1, overflowX: 'auto', whiteSpace: 'nowrap' }}>
            {cronLine || '—'}
          </code>
          <button
            className="btn btn-ghost"
            onClick={copy}
            disabled={!cronLine}
            aria-label={copied === 'done' ? 'Copied to clipboard' : 'Copy cron line to clipboard'}
          >
            {copied === 'done' ? 'Copied ✓' : copied === 'error' ? 'Copy failed' : 'Copy'}
          </button>
        </div>
        <div role="status" aria-live="polite" className="sr-only">
          {copied === 'done' ? 'Cron line copied to clipboard'
            : copied === 'error' ? 'Copy failed — select and copy the line manually' : ''}
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────── web search rows ────────────────────────── */

const WEB_PROVIDER_LABELS: Record<string, string> = {
  tavily: 'Tavily', brave: 'Brave Search', ddg: 'keyless DuckDuckGo',
};

function WebSearchRows({
  data, webSearch, busy, onToggle, onProvider,
}: {
  data?: SettingsResponse;
  webSearch: boolean;
  busy: boolean;
  onToggle: () => void;
  onProvider: (id: string) => void;
}) {
  const qc = useQueryClient();
  const ws = data?.web_search;
  const [pid, setPid] = useState('tavily');
  const [key, setKey] = useState('');
  const keyMut = useMutation({
    mutationFn: () => saveApiKey(pid, key.trim()),
    onSuccess: () => { setKey(''); qc.invalidateQueries({ queryKey: ['settings'] }); },
  });
  const active = ws?.active_provider ? (WEB_PROVIDER_LABELS[ws.active_provider] ?? ws.active_provider) : null;
  const selected = ws?.providers?.find((p) => p.id === pid);

  return (
    <>
      <div className="settings-row">
        <span className="settings-key">
          Web search (augments thesis, memo, thematic research)
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            SEC filings stay the only source of figures — web adds recent context, cited [Wn].
            {webSearch && active ? ` Active backend: ${active}.` : ''}
          </div>
        </span>
        <button
          className="btn"
          disabled={busy}
          onClick={onToggle}
          style={webSearch ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
        >
          {webSearch ? 'Enabled' : 'Disabled'}
        </button>
      </div>
      {webSearch && (
        <div className="settings-row">
          <span className="settings-key">
            Search backend
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              Choose a provider, or “Auto”. “Coding-agent harness” lets your CLI agent search
              with no key (agent_cli only).
            </div>
          </span>
          <select
            className="field"
            value={ws?.provider ?? 'auto'}
            disabled={busy}
            onChange={(e) => onProvider(e.target.value)}
            style={fieldStyle(280)}
          >
            {(ws?.choices ?? [{ id: 'auto', label: 'Auto' }]).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
        </div>
      )}
      {webSearch && (
        <div className="settings-row">
          <span className="settings-key">
            Search API key (optional)
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              Without a key, a best-effort keyless backend is used. A free Tavily/Brave key is
              more reliable.{' '}
              {selected?.console_url && (
                <a href={selected.console_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
                  Get a {selected.label} key →
                </a>
              )}
            </div>
          </span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 360 }}>
            <select className="field" value={pid} onChange={(e) => setPid(e.target.value)}
                    style={fieldStyle(130)}>
              {(ws?.providers ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}{p.key_present ? ' ✓' : ''}
                </option>
              ))}
            </select>
            <input
              className="field" type="password" autoComplete="off" value={key}
              placeholder={selected?.key_present ? '•••••••• stored — type to replace' : 'paste key'}
              onChange={(e) => setKey(e.target.value)}
              style={{ ...fieldStyle(), flex: 1 }}
            />
            <button className="btn" disabled={keyMut.isPending || key.trim() === ''}
                    onClick={() => keyMut.mutate()}>
              {keyMut.isPending ? 'Saving…' : 'Save'}
            </button>
          </span>
        </div>
      )}
    </>
  );
}

/* ────────────────────────── page ────────────────────────── */

type DangerAction = 'clear-pipeline' | 'reset-constitution';

export default function Settings() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ['settings'], queryFn: getSettings });
  const config = data?.config;
  const health = data?.health;

  const [secUA, setSecUA] = useState('');
  const [danger, setDanger] = useState<DangerAction | null>(null);
  const [dangerNote, setDangerNote] = useState<string | null>(null);

  const configuredSecUA = String(
    config?.providers?.sec_user_agent ?? config?.sec_user_agent ?? '',
  );

  useEffect(() => {
    if (config) setSecUA(configuredSecUA);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const save = useMutation({
    mutationFn: (updates: Record<string, unknown>) => saveSettings(updates),
    onSettled: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });

  const clearPipeline = useMutation({
    mutationFn: clearPipelineData,
    onSuccess: () => {
      setDanger(null);
      setDangerNote('Pipeline data cleared. Constitution and portfolio were preserved.');
      qc.invalidateQueries();
    },
    onError: (err: Error) => setDangerNote(`Clear pipeline failed: ${err.message}`),
  });

  const resetConst = useMutation({
    mutationFn: resetConstitution,
    onSuccess: () => {
      setDanger(null);
      setDangerNote('Constitution reset. Describe your approach in Chat to draft a new one.');
      qc.invalidateQueries();
    },
    onError: (err: Error) => setDangerNote(`Reset constitution failed: ${err.message}`),
  });

  const download = () => {
    const a = document.createElement('a');
    a.href = settingsExportUrl;
    a.download = 'fundops-export.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const exportData = async () => {
    // Warn before a large download instead of silently streaming hundreds of MB
    // (ISSUE-004). The estimate is a cheap aggregate; if it fails, just download.
    try {
      const est = await getExportEstimate();
      const mb = est.approx_bytes / (1024 * 1024);
      if (mb >= 25) {
        const ok = window.confirm(
          `This workspace export is about ${mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`} ` +
          `(${est.total_rows.toLocaleString()} rows). Resyncable bulk data ` +
          `(${est.excluded_tables.join(', ')}) is already excluded and rebuilds via sync. Continue?`,
        );
        if (!ok) return;
      }
    } catch {
      // estimate unavailable — fall through to the download
    }
    download();
  };

  const webSearch = (config?.providers?.web_search ?? config?.web_search_enabled) === true;
  const rows = usageRows(data);
  const secDirty = config != null && secUA !== configuredSecUA;

  return (
    <div className="settings-grid">
      <PageHeader
        sectionLabel="Operations"
        title="Settings"
        subtitle="Operational configuration only. Investment strategy lives in the Constitution — change it via Chat."
      />

      {/* ── Health strip: each chip says its state and opens the place to act ── */}
      <div className="health-strip">
        <HealthChip
          label="Backend"
          state={health?.ok ? 'connected' : 'unreachable'}
          ok={health?.ok}
          detail="Whether this page can reach the FundOps server"
        />
        <HealthChip
          label="AI provider"
          state={
            health?.ai_provider === 'stub'
              ? 'offline stub'
              : health?.ai_provider === 'agent_cli'
                ? 'claude · headless'
                : String(health?.ai_provider_id ?? health?.ai_provider ?? '—')
          }
          ok={health?.ai_configured}
          detail={
            health?.ai_configured
              ? 'A real model provider is connected — click to review'
              : 'No model connected: runs produce placeholders. Click to set up a provider below'
          }
          onClick={() =>
            document.getElementById('ai-provider-card')?.scrollIntoView({ behavior: 'smooth' })
          }
        />
        <HealthChip
          label="Constitution"
          state={
            health?.has_constitution
              ? `v${health?.constitution_version ?? '?'} active`
              : 'none — draft one in chat'
          }
          ok={health?.has_constitution}
          detail="Your investment strategy as wired, versioned settings. Click to work on it in the conversation"
          onClick={() => navigate('/')}
        />
        <HealthChip
          label="Schema"
          state={`v${health?.workspace_schema_version ?? '—'}`}
          ok={health?.workspace_schema_version != null ? true : undefined}
          detail="Workspace database schema version (informational)"
        />
      </div>

      {/* ── Market & filings data (ADR-0059) ── */}
      <MarketDataCard />

      {/* ── AI provider & models ── */}
      <AiProviderCard data={data} />

      {/* ── Connected services ── */}
      <div className="card">
        <div className="card-title">Connected services</div>

        <div className="settings-row">
          <span className="settings-key">
            SEC user agent
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              EDGAR requires a contact string, e.g. "name email@example.com"
            </div>
          </span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 320 }}>
            <input
              className="field"
              value={secUA}
              onChange={(e) => setSecUA(e.target.value)}
              placeholder="name email@example.com"
              style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', padding: '7px 10px' }}
            />
            <button
              className="btn"
              disabled={!secDirty || save.isPending}
              onClick={() => save.mutate({ providers: { sec_user_agent: secUA } })}
            >
              Save
            </button>
          </span>
        </div>

        <WebSearchRows
          data={data}
          webSearch={webSearch}
          busy={save.isPending || config == null}
          onToggle={() => save.mutate({ providers: { web_search: !webSearch } })}
          onProvider={(id) => save.mutate({ providers: { web_search_provider: id } })}
        />
      </div>

      {/* ── AI usage ── */}
      <div className="card">
        <div className="card-title">AI usage</div>
        {rows.length === 0 ? (
          <div className="empty-note">No AI usage recorded yet.</div>
        ) : (
          <div className="table-shell" style={{ boxShadow: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Model</th>
                  <th style={{ textAlign: 'right' }}>Calls</th>
                  <th style={{ textAlign: 'right' }}>Tokens in</th>
                  <th style={{ textAlign: 'right' }}>Tokens out</th>
                  <th style={{ textAlign: 'right' }}>Est. cost</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.capability ?? '—'}</td>
                    <td className="settings-val" style={{ fontSize: 'var(--text-xs)' }}>
                      {r.model ?? '—'}
                    </td>
                    <td className="num">{fmtInt(r.calls)}</td>
                    <td className="num">{fmtInt(r.tokens_in)}</td>
                    <td className="num">{fmtInt(r.tokens_out)}</td>
                    <td className="num">{fmtCost(r.est_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="usage-caveat">
          Cost estimates are approximate, derived from listed model prices at call time.
        </div>
      </div>

      {/* ── Automation ── */}
      <AutomationCard data={data} />

      {/* ── Own your data ── */}
      <div className="card">
        <div className="card-title">Own your data</div>
        <div className="settings-row">
          <span className="settings-key">
            Export workspace data
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              All retained records — constitution versions, artifacts, evidence, ledger — as JSON.
            </div>
          </span>
          <button className="btn" onClick={exportData}>
            Export JSON
          </button>
        </div>
      </div>

      {/* ── Danger zone ── */}
      <div className="card danger-zone">
        <div className="card-title" style={{ color: 'var(--negative)' }}>
          Danger zone
        </div>
        {dangerNote && (
          <div className="banner" style={{ marginBottom: 10, fontSize: 'var(--text-xs)' }}>
            {dangerNote}
          </div>
        )}
        <div className="settings-row">
          <span className="settings-key">
            Clear pipeline data
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              Removes workflow runs and generated stage output. Keeps Constitution and portfolio.
            </div>
          </span>
          <button
            className="btn"
            style={{ color: 'var(--negative)', borderColor: 'rgba(234,67,53,0.4)' }}
            onClick={() => setDanger('clear-pipeline')}
          >
            Clear pipeline data
          </button>
        </div>
        <div className="settings-row">
          <span className="settings-key">
            Reset constitution
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
              Removes all Constitution versions and derived capability settings.
            </div>
          </span>
          <button
            className="btn"
            style={{ color: 'var(--negative)', borderColor: 'rgba(234,67,53,0.4)' }}
            onClick={() => setDanger('reset-constitution')}
          >
            Reset constitution
          </button>
        </div>
      </div>

      {danger === 'clear-pipeline' && (
        <DangerModal
          title="Clear pipeline data"
          phrase="clear pipeline"
          removes={[
            'Workflow runs and steps (screener, thesis, IC, memo, pipeline)',
            'Stage workbench state and screener results',
            'Generated artifacts from those runs',
          ]}
          preserves={[
            'Constitution versions, proposals, and wired settings',
            'Portfolio ledger (lots, sales) and price marks',
            'Chat history and strategy memory',
          ]}
          busy={clearPipeline.isPending}
          onConfirm={() => clearPipeline.mutate()}
          onClose={() => setDanger(null)}
        />
      )}
      {danger === 'reset-constitution' && (
        <DangerModal
          title="Reset constitution"
          phrase="reset constitution"
          removes={[
            'All Constitution versions and strategy criteria',
            'Pending and historical strategy proposals',
            'Derived capability settings (wiring projections)',
          ]}
          preserves={[
            'Portfolio ledger (lots, sales)',
            'Completed artifacts and evidence records',
            'AI usage history',
          ]}
          busy={resetConst.isPending}
          onConfirm={() => resetConst.mutate()}
          onClose={() => setDanger(null)}
        />
      )}
    </div>
  );
}
