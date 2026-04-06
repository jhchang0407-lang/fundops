import { useState, useEffect, type ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type SettingsTab = 'data' | 'ai' | 'schedule' | 'system';

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'data', label: 'Data Sources' },
  { id: 'ai', label: 'AI Model' },
  { id: 'schedule', label: 'Schedule' },
  { id: 'system', label: 'System' },
];

// ---------------------------------------------------------------------------
// Shared styles & helpers
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '5px 8px', background: 'var(--bg-tertiary)',
  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)',
  fontFamily: 'var(--font-ui)', fontSize: 'var(--text-sm)', outline: 'none',
};

const inputMonoStyle: React.CSSProperties = {
  ...inputStyle, fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)',
};

const btnAccent: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 4, fontFamily: 'var(--font-ui)',
  fontSize: 10, fontWeight: 600, cursor: 'pointer', border: 'none',
  background: 'var(--accent)', color: '#0a0a0f',
};

const btnGhost: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 4, fontFamily: 'var(--font-ui)',
  fontSize: 10, fontWeight: 600, cursor: 'pointer',
  background: 'none', border: '1px solid var(--border)', color: 'var(--text-secondary)',
};

const btnDanger: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 4, fontFamily: 'var(--font-ui)',
  fontSize: 10, fontWeight: 600, cursor: 'pointer',
  background: 'rgba(234,67,53,0.12)', color: 'var(--negative)',
  border: '1px solid rgba(234,67,53,0.3)',
};

const labelStyle: React.CSSProperties = {
  fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase',
};

// ---------------------------------------------------------------------------
// ConnectorCard
// ---------------------------------------------------------------------------

type ConnectorStatus = 'connected' | 'not_configured' | 'error' | 'free' | 'configured';

function ConnectorCard({ title, status, children }: {
  title: string; status: ConnectorStatus; children: ReactNode;
}) {
  const colors: Record<ConnectorStatus, string> = {
    connected: 'var(--positive)', not_configured: 'var(--text-muted)',
    error: 'var(--negative)', free: 'var(--positive)', configured: 'var(--accent)',
  };
  const labels: Record<ConnectorStatus, string> = {
    connected: '\u25CF Connected', not_configured: '\u25CB Not configured',
    error: '\u25CF Error', free: '\u25CF Connected (free)', configured: '\u25CF Key saved',
  };
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <strong style={{ fontSize: 'var(--text-sm)' }}>{title}</strong>
        <span style={{ color: colors[status], fontSize: 'var(--text-xs)' }}>{labels[status]}</span>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RadioOption (reusable)
// ---------------------------------------------------------------------------

function RadioOption({ selected, label, description, capability, onClick }: {
  selected: boolean; label: string; description?: string;
  capability?: string; onClick: () => void;
}) {
  const capColor = capability === 'search + extract'
    ? { bg: 'rgba(52,168,83,0.12)', fg: 'var(--positive)' }
    : capability === 'search only'
    ? { bg: 'rgba(245,166,35,0.12)', fg: 'var(--accent)' }
    : null;

  return (
    <label onClick={onClick} style={{
      display: 'flex', alignItems: 'flex-start', gap: 6, padding: '4px 6px',
      background: selected ? 'var(--bg-tertiary)' : 'transparent',
      border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
      borderRadius: 4, cursor: 'pointer', fontSize: 'var(--text-xs)',
    }}>
      <div style={{
        width: 12, height: 12, borderRadius: '50%', marginTop: 1, flexShrink: 0,
        border: `2px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {selected && <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontWeight: 500 }}>{label}</span>
          {capability && capColor && (
            <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: capColor.bg, color: capColor.fg }}>
              {capability}
            </span>
          )}
        </div>
        {description && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{description}</div>}
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Settings (main export)
// ---------------------------------------------------------------------------

export function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('data');
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.getConfig });
  const connectors = config?.connectors || {};

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, marginBottom: 10 }}>Settings</h1>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 0,
        borderBottom: '1px solid var(--border)', marginBottom: 12,
      }}>
        {TABS.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
            padding: '6px 10px', fontSize: 'var(--text-sm)',
            color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-secondary)',
            borderTop: 'none', borderLeft: 'none', borderRight: 'none',
            borderBottom: `2px solid ${activeTab === tab.id ? 'var(--accent)' : 'transparent'}`,
            background: 'none',
            cursor: 'pointer', fontFamily: 'var(--font-ui)', whiteSpace: 'nowrap',
          }}>
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'data' && <DataSourcesTab connectors={connectors} />}
      {activeTab === 'ai' && <AIModelTab connectors={connectors} />}
      {activeTab === 'schedule' && <ScheduleTab />}
      {activeTab === 'system' && <SystemTab />}
    </div>
  );
}


// ===========================================================================
// TAB 1: Data Sources
// ===========================================================================

const WEB_SEARCH_PROVIDERS = [
  { id: 'openai', label: 'OpenAI Web Search', description: 'Search + read pages. Uses your OpenAI key. Built into GPT models.', needsKey: false, capabilities: 'search + extract' },
  { id: 'none', label: 'None (disabled)', description: 'No web search. Agents work with SEC + financial data only.', needsKey: false, capabilities: 'none' },
] as const;

function DataSourcesTab({ connectors }: { connectors: any }) {
  const queryClient = useQueryClient();
  const hasFmpKey = !!(connectors.market_data?.api_key);
  const [fmpKey, setFmpKey] = useState('');
  const [fmpEditMode, setFmpEditMode] = useState(!hasFmpKey);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string; tier?: string; tier_features?: string[]; missing_features?: string[]; preview?: string }>>({});
  const [saving, setSaving] = useState(false);
  const [wsTestResult, setWsTestResult] = useState<{ ok: boolean; msg: string; preview?: string } | null>(null);
  const [wsTestLoading, setWsTestLoading] = useState(false);

  // SEC EDGAR user agent state
  const secConfig = connectors.filings || {};
  const existingAgent = secConfig.user_agent || '';
  const [secName, setSecName] = useState('');
  const [secEmail, setSecEmail] = useState('');
  const [secSaving, setSecSaving] = useState(false);
  const [secSaved, setSecSaved] = useState(!!existingAgent);

  const saveSecAgent = async () => {
    if (!secName.trim() || !secEmail.trim()) return;
    setSecSaving(true);
    const userAgent = `${secName.trim()} ${secEmail.trim()}`;
    await api.saveConfig('connectors.filings', { user_agent: userAgent });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setSecSaving(false);
    setSecSaved(true);
  };

  // Web search state
  const webSearch = connectors.web_search || {};
  const [wsProvider, setWsProvider] = useState(webSearch.provider || 'openai');
  const [wsApiKey, setWsApiKey] = useState('');
  const [wsSaving, setWsSaving] = useState(false);
  const [wsSaved, setWsSaved] = useState(false);

  const currentWs = WEB_SEARCH_PROVIDERS.find(p => p.id === wsProvider) || WEB_SEARCH_PROVIDERS[0];

  const wsStatus: ConnectorStatus = wsTestResult?.ok ? 'connected'
    : wsProvider === 'none' ? 'not_configured'
    : wsProvider === 'openai' ? (connectors.ai_model?.api_key ? 'configured' : 'not_configured')
    : webSearch.api_key ? 'configured' : 'not_configured';

  const testConn = async (source: string) => {
    try {
      const r = await api.testConnection(source);
      setTestResult(prev => ({ ...prev, [source]: { ok: r.connected, msg: r.connected ? 'Connected' : r.error || 'Failed' } }));
    } catch (e) {
      setTestResult(prev => ({ ...prev, [source]: { ok: false, msg: String(e) } }));
    }
  };

  const saveFmp = async () => {
    if (!fmpKey) return;
    setSaving(true);
    await api.saveConfig('connectors.market_data', { api_key: fmpKey });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setSaving(false);
    setFmpEditMode(false);
    setFmpKey('');
    testConn('fmp');
  };

  const clearFmp = async () => {
    await api.saveConfig('connectors.market_data', { api_key: '' });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setFmpKey('');
    setFmpEditMode(true);
    setTestResult(prev => { const n = { ...prev }; delete n.fmp; return n; });
  };

  const saveWebSearch = async () => {
    setWsSaving(true);
    await api.saveConfig('connectors.web_search', {
      provider: wsProvider,
      ...(wsApiKey && !wsApiKey.startsWith('****') ? { api_key: wsApiKey } : {}),
    });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setWsSaving(false);
    setWsSaved(true);
    setTimeout(() => setWsSaved(false), 3000);
  };

  const testWebSearch = async () => {
    setWsTestLoading(true);
    setWsTestResult(null);
    try {
      const r = await api.testConnection('web_search');
      setWsTestResult({
        ok: r.connected,
        msg: r.connected ? 'Search working' : r.error || 'Failed',
        preview: r.preview,
      });
    } catch (e) {
      setWsTestResult({ ok: false, msg: String(e) });
    } finally {
      setWsTestLoading(false);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
      {/* Yahoo Finance */}
      <ConnectorCard title="Yahoo Finance" status="free">
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          Free default for quotes, PE, margins, sector data. No API key required.
        </div>
        <button style={{ ...btnGhost, marginTop: 8 }} onClick={() => testConn('yfinance')}>
          Test Connection
        </button>
        {testResult.yfinance && (
          <span style={{ fontSize: 10, marginLeft: 6, color: testResult.yfinance.ok ? 'var(--positive)' : 'var(--negative)' }}>
            {testResult.yfinance.msg}
          </span>
        )}
      </ConnectorCard>

      {/* SEC EDGAR */}
      <ConnectorCard title="SEC EDGAR" status={secSaved ? 'free' : 'not_configured'}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 6 }}>
          Free. 10-K/10-Q filings, financial statements, company profiles. SEC requires your name and email in requests.
        </div>
        {secSaved && existingAgent ? (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 6 }}>
            Registered as: <span style={{ color: 'var(--text-secondary)' }}>{existingAgent}</span>
          </div>
        ) : null}
        <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
          <input value={secName} onChange={e => setSecName(e.target.value)}
            placeholder="Your name" style={{ ...inputStyle, flex: 1 }} />
          <input value={secEmail} onChange={e => setSecEmail(e.target.value)}
            placeholder="your@email.com" style={{ ...inputStyle, flex: 1 }} />
        </div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button style={btnAccent} onClick={saveSecAgent} disabled={secSaving || !secName.trim() || !secEmail.trim()}>
            {secSaving ? 'Saving...' : 'Save'}
          </button>
          <button style={btnGhost} onClick={() => testConn('sec')}>
            Test Connection
          </button>
          {testResult.sec && (
            <span style={{ fontSize: 10, color: testResult.sec.ok ? 'var(--positive)' : 'var(--negative)' }}>
              {testResult.sec.msg}
            </span>
          )}
        </div>
      </ConnectorCard>

      {/* FMP */}
      <ConnectorCard title="FMP (optional)" status={testResult.fmp?.ok ? 'connected' : connectors.market_data?.api_key ? 'configured' : 'not_configured'}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 6 }}>
          Adds analyst estimates, earnings surprises, price targets, momentum/relative strength data, and bulk screening. Yahoo + SEC cover the basics without it.
        </div>
        <label style={labelStyle}>API Key</label>
        {!fmpEditMode ? (
          <div style={{ display: 'flex', gap: 4, marginTop: 4, alignItems: 'center' }}>
            <div style={{ ...inputMonoStyle, flex: 1, color: 'var(--text-muted)', letterSpacing: 2, userSelect: 'none' }}>
              ••••••••••••••••
            </div>
            <button style={btnGhost} onClick={() => setFmpEditMode(true)}>Change</button>
            <button style={btnDanger} onClick={clearFmp}>Clear</button>
            <button style={btnGhost} onClick={() => testConn('fmp')}>Test</button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
            <input value={fmpKey} onChange={e => setFmpKey(e.target.value)}
              placeholder="Your FMP API key..." type="password"
              style={{ ...inputMonoStyle, flex: 1 }} />
            <button style={btnAccent} onClick={saveFmp} disabled={saving || !fmpKey}>
              {saving ? '...' : 'Save'}
            </button>
            {hasFmpKey && <button style={btnGhost} onClick={() => { setFmpEditMode(false); setFmpKey(''); }}>Cancel</button>}
          </div>
        )}
        {testResult.fmp && (
          <div style={{ fontSize: 10, marginTop: 6 }}>
            <span style={{ color: testResult.fmp.ok ? 'var(--positive)' : 'var(--negative)' }}>
              {testResult.fmp.ok ? '● Connected' : '● Failed'}
            </span>
            {testResult.fmp.tier && (
              <span style={{
                marginLeft: 8, padding: '1px 6px', borderRadius: 9999, fontSize: 9, fontFamily: 'var(--font-data)',
                background: testResult.fmp.tier === 'paid' ? 'rgba(52,168,83,0.15)' : 'rgba(245,166,35,0.15)',
                color: testResult.fmp.tier === 'paid' ? 'var(--positive)' : 'var(--accent)',
              }}>
                {testResult.fmp.tier === 'paid' ? 'PAID' : 'FREE TIER'}
              </span>
            )}
            {testResult.fmp.tier_features && testResult.fmp.tier_features.length > 0 && (
              <div style={{ marginTop: 4, color: 'var(--text-muted)' }}>
                ✓ {testResult.fmp.tier_features.join(' · ')}
              </div>
            )}
            {testResult.fmp.missing_features && testResult.fmp.missing_features.length > 0 && (
              <div style={{ marginTop: 2, color: 'var(--text-muted)' }}>
                ✗ Not available: {testResult.fmp.missing_features.join(' · ')}
              </div>
            )}
            {!testResult.fmp.ok && testResult.fmp.msg && (
              <div style={{ color: 'var(--negative)', marginTop: 2 }}>{testResult.fmp.msg}</div>
            )}
          </div>
        )}
      </ConnectorCard>

      {/* Web Search & Extract */}
      <ConnectorCard title="Web Search & Extract" status={wsStatus}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
          Powers market research, news context, and the AI strategy wizard. Search finds URLs. Extract reads page content.
        </div>

        <label style={labelStyle}>Search Provider</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4, marginBottom: 8 }}>
          {WEB_SEARCH_PROVIDERS.map(p => (
            <RadioOption
              key={p.id}
              selected={wsProvider === p.id}
              label={p.label}
              description={p.description}
              capability={p.capabilities !== 'none' ? p.capabilities : undefined}
              onClick={() => setWsProvider(p.id)}
            />
          ))}
        </div>

        {currentWs.needsKey && 'keyLabel' in currentWs && (
          <>
            <label style={labelStyle}>{(currentWs as any).keyLabel}</label>
            <input value={wsApiKey} onChange={e => setWsApiKey(e.target.value)}
              placeholder={webSearch.api_key ? '(key saved, enter new to change)' : (currentWs as any).keyPlaceholder || ''}
              type="password"
              style={{ ...inputMonoStyle, marginTop: 4 }} />
          </>
        )}

        {wsProvider === 'openai' && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--positive)' }}>&#10003;</span> OpenAI Web Search handles both search and page reading. No separate extract tool needed.
          </div>
        )}

        <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button style={btnAccent} onClick={saveWebSearch} disabled={wsSaving}>
            {wsSaving ? 'Saving...' : 'Save'}
          </button>
          {wsProvider !== 'none' && (
            <button style={btnGhost} onClick={testWebSearch} disabled={wsTestLoading}>
              {wsTestLoading ? 'Testing...' : 'Test Search'}
            </button>
          )}
          {wsSaved && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--positive)', alignSelf: 'center' }}>Saved</span>}
        </div>
        {wsTestResult && (
          <div style={{ marginTop: 8, fontSize: 10, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            <span style={{ color: wsTestResult.ok ? 'var(--positive)' : 'var(--negative)' }}>
              {wsTestResult.ok ? '● ' : '● '}{wsTestResult.msg}
            </span>
            {wsTestResult.preview && (
              <div style={{ marginTop: 4, color: 'var(--text-muted)', lineHeight: 1.5, fontStyle: 'italic' }}>
                "{wsTestResult.preview}…"
              </div>
            )}
          </div>
        )}
      </ConnectorCard>
    </div>
  );
}


// ===========================================================================
// TAB 2: AI Model
// ===========================================================================

const PROVIDERS = [
  {
    id: 'openai', label: 'OpenAI', description: 'GPT-5, o3, o4-mini. Best web search integration.', keyPlaceholder: 'sk-...',
    models: [
      // GPT-5 series (current flagship)
      'gpt-5.4',
      'gpt-5.4-mini',
      'gpt-5.4-nano',
      'gpt-5',
      'gpt-5-mini',
      // o-series reasoning models
      'o3',
      'o3-pro',
      'o3-mini',
      'o4-mini',
      // GPT-4.1 series (fast + cheap, 1M context)
      'gpt-4.1',
      'gpt-4.1-mini',
      'gpt-4.1-nano',
      // GPT-4o series (multimodal)
      'gpt-4o',
      'gpt-4o-mini',
    ],
  },
  {
    id: 'custom', label: 'Custom endpoint', description: 'Any OpenAI-compatible API endpoint. Must support structured outputs.', models: [] as string[], keyPlaceholder: 'Your API key...', baseUrl: '',
  },
];

// Cost breakdown type
interface CostEntry { label: string; amount: string }

function AIModelTab({ connectors }: { connectors: any }) {
  const queryClient = useQueryClient();
  const aiConfig = connectors.ai_model || {};
  const hasApiKey = !!(aiConfig.api_key);

  const [provider, setProvider] = useState(aiConfig.provider || 'openai');
  const [model, setModel] = useState(aiConfig.model || 'gpt-5.4');
  const [apiKey, setApiKey] = useState('');
  const [apiKeyEditMode, setApiKeyEditMode] = useState(!hasApiKey);
  const [baseUrl, setBaseUrl] = useState(aiConfig.base_url || '');
  const [customModel, setCustomModel] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Cost tracking — fetch real data from /api/costs
  const { data: costData } = useQuery({ queryKey: ['costs'], queryFn: api.getCosts, refetchInterval: 10000 });
  const [monthlyBudget, setMonthlyBudget] = useState(aiConfig.monthly_budget ?? 100);
  const [warningThreshold, setWarningThreshold] = useState(aiConfig.warning_threshold ?? 80);
  const currentSpend = costData?.total_cost ?? 0;
  const costBreakdown: CostEntry[] = costData?.cost_breakdown || [];

  const currentProvider = PROVIDERS.find(p => p.id === provider) || PROVIDERS[0];
  const spendPct = monthlyBudget > 0 ? Math.min((currentSpend / monthlyBudget) * 100, 100) : 0;
  const warnAmount = (monthlyBudget * warningThreshold / 100);

  const handleProviderChange = (id: string) => {
    setProvider(id);
    const p = PROVIDERS.find(pp => pp.id === id)!;
    if (p.models.length > 0) setModel(p.models[0]);
    if ('baseUrl' in p && p.baseUrl !== undefined) setBaseUrl(p.baseUrl);
    setTestResult(null);
    setApiKey('');
    setApiKeyEditMode(!hasApiKey);
  };

  const handleSave = async () => {
    setSaving(true);
    const effectiveModel = model === '_custom' ? customModel : model;
    await api.saveConfig('connectors.ai_model', {
      provider, model: effectiveModel,
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(baseUrl ? { base_url: baseUrl } : {}),
      monthly_budget: monthlyBudget,
      warning_threshold: warningThreshold,
    });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setSaving(false);
    setSaved(true);
    if (apiKey) { setApiKey(''); setApiKeyEditMode(false); }
    setTimeout(() => setSaved(false), 3000);
  };

  const clearApiKey = async () => {
    await api.saveConfig('connectors.ai_model', { api_key: '' });
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setApiKey('');
    setApiKeyEditMode(true);
    setTestResult(null);
  };

  const handleTest = async () => {
    setTestResult(null);
    try {
      const r = await api.testConnection('ai');
      setTestResult({ ok: r.connected, msg: r.connected ? 'Connected. Model responded.' : r.error || 'Failed to connect.' });
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    }
  };

  return (
    <div>
      {/* Provider + Model/Key: 2-column */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {/* Provider selection */}
        <div className="card">
          <div className="card-title">Provider</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {PROVIDERS.map(p => (
              <RadioOption
                key={p.id}
                selected={provider === p.id}
                label={p.label}
                description={p.description}
                onClick={() => handleProviderChange(p.id)}
              />
            ))}
          </div>
        </div>

        {/* Model + Key */}
        <div>
          <div className="card">
            <div className="card-title">Model</div>
            {currentProvider.models.length > 0 ? (
              <select value={model} onChange={e => setModel(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {currentProvider.models.map(m => <option key={m} value={m}>{m}</option>)}
                <option value="_custom">Custom model name...</option>
              </select>
            ) : (
              <input value={model} onChange={e => setModel(e.target.value)}
                placeholder="Model name (e.g., mistralai/Mixtral-8x7B)"
                style={inputStyle} />
            )}
            {model === '_custom' && (
              <input value={customModel} onChange={e => setCustomModel(e.target.value)}
                placeholder="Type model name..."
                style={{ ...inputStyle, marginTop: 6 }} />
            )}
          </div>

          <div className="card" style={{ marginTop: 8 }}>
            <div className="card-title">
              {provider === 'ollama' ? 'Connection' : 'API Key'}
            </div>
            {provider !== 'ollama' && (
              !apiKeyEditMode ? (
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 4 }}>
                  <div style={{ ...inputMonoStyle, flex: 1, color: 'var(--text-muted)', letterSpacing: 2, userSelect: 'none' }}>
                    ••••••••••••••••
                  </div>
                  <button style={btnGhost} onClick={() => setApiKeyEditMode(true)}>Change</button>
                  <button style={btnDanger} onClick={clearApiKey}>Clear</button>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 4 }}>
                  <input value={apiKey} onChange={e => setApiKey(e.target.value)}
                    placeholder={currentProvider.keyPlaceholder}
                    type="password"
                    style={{ ...inputMonoStyle, flex: 1 }} />
                  {hasApiKey && <button style={btnGhost} onClick={() => { setApiKeyEditMode(false); setApiKey(''); }}>Cancel</button>}
                </div>
              )
            )}
            {provider === 'ollama' && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 6 }}>
                No API key needed. Make sure Ollama is running locally.
              </div>
            )}
            {(provider === 'ollama' || provider === 'custom' || provider === 'openrouter') && (
              <>
                <label style={{ ...labelStyle, marginTop: 8, display: 'block' }}>Base URL</label>
                <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  style={{ ...inputMonoStyle, marginTop: 4 }} />
              </>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center' }}>
            <button style={{ ...btnAccent, padding: '6px 16px', fontSize: 'var(--text-sm)' }} onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button style={{ ...btnGhost, fontSize: 'var(--text-xs)' }} onClick={handleTest}>
              Test Connection
            </button>
            {saved && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--positive)' }}>Saved</span>}
            {testResult && (
              <span style={{ fontSize: 'var(--text-xs)', color: testResult.ok ? 'var(--positive)' : 'var(--negative)' }}>
                {testResult.ok ? '\u2713 Connected' : testResult.msg}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Cost Tracking — full width */}
      <div className="card" style={{ marginTop: 8 }}>
        <div className="card-title">Cost Tracking</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 600 }}>
            ${currentSpend.toFixed(2)}
          </span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            of ${monthlyBudget} monthly budget
          </span>
        </div>

        {/* Progress bar */}
        <div style={{ height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden', margin: '6px 0 4px' }}>
          <div style={{ height: 6, borderRadius: 3, background: 'var(--accent)', width: `${spendPct}%` }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
          <span>$0</span>
          <span style={{ color: 'var(--warning)' }}>${warnAmount.toFixed(0)} warn</span>
          <span>${monthlyBudget} cap</span>
        </div>

        {/* By agent breakdown */}
        <div style={{ marginTop: 12 }}>
          <div className="card-title">By Agent</div>
          {costBreakdown.map((entry, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-sm)',
            }}>
              <span style={{ color: 'var(--text-secondary)' }}>{entry.label}</span>
              <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-primary)', fontSize: 'var(--text-xs)' }}>{entry.amount}</span>
            </div>
          ))}
        </div>

        {/* Budget inputs */}
        <div style={{ marginTop: 10, display: 'flex', gap: 12 }}>
          <div>
            <label style={labelStyle}>Monthly budget</label>
            <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
              <input type="number" value={monthlyBudget} onChange={e => setMonthlyBudget(Number(e.target.value))}
                style={{ ...inputMonoStyle, width: 70, textAlign: 'right' }} />
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', alignSelf: 'center' }}>USD</span>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Warning at</label>
            <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
              <input type="number" value={warningThreshold} onChange={e => setWarningThreshold(Number(e.target.value))}
                style={{ ...inputMonoStyle, width: 50, textAlign: 'right' }} />
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', alignSelf: 'center' }}>%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


// ===========================================================================
// TAB 3: System
// ===========================================================================

type AutonomyMode = 'manual' | 'suggest' | 'autopilot';

const AUTONOMY_MODES: { id: AutonomyMode; label: string; description: string }[] = [
  { id: 'manual', label: 'Manual', description: 'All changes require manual intervention. Full control.' },
  { id: 'suggest', label: 'Suggest', description: 'System proposes changes, you approve. Feedback proposals appear on Home page. Autopilot unlocks at 80%+ acceptance rate.' },
  { id: 'autopilot', label: 'Autopilot', description: 'System applies low-risk changes automatically. High-impact changes still require approval.' },
];

interface ScheduleEntry {
  agent: string;
  description: string;
  frequency: string;
  time: string;
  status: 'active' | 'paused' | 'manual';
  lastRun?: string;
  nextRun?: string;
  cost?: string;
}

const DEFAULT_SCHEDULES: ScheduleEntry[] = [
  { agent: 'Screener', description: 'Score universe against your strategy', frequency: 'Weekly', time: 'Sun 8:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Portfolio Monitor', description: 'Update prices, P&L, thesis health', frequency: 'Daily', time: '7:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Outcome Checker', description: 'Check prediction accuracy vs actuals', frequency: 'Daily', time: '6:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Library Sync', description: 'Collect and index new research artifacts', frequency: 'Weekly', time: 'Mon 6:00 AM', status: 'active', cost: 'Free' },
  { agent: 'Full Pipeline', description: 'Scout → Thesis → IC → Pulse → Allocator', frequency: 'Weekly', time: 'Sun 9:00 AM', status: 'paused', cost: '~$0.50' },
  { agent: 'Thesis Batch', description: 'Run thesis on all promoted screener picks', frequency: 'Manual', time: '\u2014', status: 'manual', cost: '~$0.10/ticker' },
  { agent: 'Memo Generation', description: 'Generate investment memo for IC-passed stocks', frequency: 'Manual', time: '\u2014', status: 'manual', cost: '~$0.38/memo' },
  { agent: 'Allocator', description: 'Position sizing, concentration alerts, and action items', frequency: 'Manual', time: '\u2014', status: 'manual', cost: 'Free' },
];

// ---------------------------------------------------------------------------
// Schedule Tab
// ---------------------------------------------------------------------------

function ScheduleTab() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.getConfig });
  const system = config?.system || {};
  // Merge saved schedules with defaults — any agent missing from saved list is restored as manual
  const savedSchedules: ScheduleEntry[] = system.schedules || DEFAULT_SCHEDULES;
  const savedAgents = new Set(savedSchedules.map((s: ScheduleEntry) => s.agent));
  const schedules: ScheduleEntry[] = [
    ...savedSchedules,
    ...DEFAULT_SCHEDULES.filter(d => !savedAgents.has(d.agent)).map(d => ({ ...d, frequency: 'Manual', time: '\u2014', status: 'manual' as const })),
  ];

  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editFreq, setEditFreq] = useState('');
  const [editTime, setEditTime] = useState('');

  const startEdit = (idx: number) => {
    setEditingIdx(idx);
    setEditFreq(schedules[idx].frequency);
    setEditTime(schedules[idx].time);
  };

  const cancelEdit = () => { setEditingIdx(null); };

  const saveMutation = useMutation({
    mutationFn: (updated: ScheduleEntry[]) => api.saveConfig('system', { schedules: updated }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setEditingIdx(null);
    },
  });

  const saveEdit = (idx: number) => {
    const updated = [...schedules];
    updated[idx] = { ...updated[idx], frequency: editFreq, time: editTime, status: editFreq === 'Manual' ? 'manual' : 'active' };
    saveMutation.mutate(updated);
  };

  const resetSchedule = (idx: number) => {
    const updated = [...schedules];
    updated[idx] = { ...updated[idx], frequency: 'Manual', time: '\u2014', status: 'manual' };
    saveMutation.mutate(updated);
  };

  const toggleStatus = (idx: number) => {
    const updated = [...schedules];
    const s = updated[idx];
    if (s.status === 'manual') return;
    updated[idx] = { ...s, status: s.status === 'active' ? 'paused' : 'active' };
    saveMutation.mutate(updated);
  };

  const freqOptions = ['Every 6 hours', 'Daily', 'Weekly', 'Bi-weekly', 'Monthly', 'Manual'];

  return (
    <div className="stack">
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 4 }}>
        Control when each agent runs automatically. Manual agents only run when you trigger them.
      </div>

      {schedules.map((s, i) => (
        <div key={i} className="card" style={{
          borderLeftColor: s.status === 'active' ? 'var(--positive)' : s.status === 'paused' ? 'var(--warning)' : 'var(--border)',
          borderLeftWidth: 2,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                <span style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{s.agent}</span>
                <span style={{
                  fontSize: 9, fontFamily: 'var(--font-data)', padding: '1px 6px', borderRadius: 3,
                  background: s.status === 'active' ? 'rgba(52,168,83,0.15)' : s.status === 'paused' ? 'rgba(251,188,4,0.15)' : 'rgba(255,255,255,0.05)',
                  color: s.status === 'active' ? 'var(--positive)' : s.status === 'paused' ? 'var(--warning)' : 'var(--text-muted)',
                }}>
                  {s.status === 'active' ? 'ACTIVE' : s.status === 'paused' ? 'PAUSED' : 'MANUAL'}
                </span>
                {s.cost === 'Free' && <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>Free</span>}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 6 }}>{s.description}</div>

              {editingIdx === i ? (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                  <select value={editFreq} onChange={e => setEditFreq(e.target.value)} style={{ ...inputStyle, width: 140, fontSize: 'var(--text-xs)' }}>
                    {freqOptions.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  {editFreq !== 'Manual' && (
                    <input
                      type="text"
                      value={editTime}
                      onChange={e => setEditTime(e.target.value)}
                      placeholder="e.g. 8:00 AM or Mon 9:00 AM"
                      style={{ ...inputMonoStyle, width: 160 }}
                    />
                  )}
                  <button style={btnAccent} onClick={() => saveEdit(i)}>Save</button>
                  <button style={btnGhost} onClick={cancelEdit}>Cancel</button>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 16, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-secondary)' }}>
                  <span>Frequency: <span style={{ color: 'var(--text-primary)' }}>{s.frequency}</span></span>
                  {s.time !== '\u2014' && <span>Time: <span style={{ color: 'var(--text-primary)' }}>{s.time}</span></span>}
                  {s.lastRun && <span>Last: <span style={{ color: 'var(--text-primary)' }}>{s.lastRun}</span></span>}
                  {s.nextRun && <span>Next: <span style={{ color: 'var(--accent)' }}>{s.nextRun}</span></span>}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 4, flexShrink: 0, marginLeft: 12 }}>
              {s.status !== 'manual' && (
                <button style={btnGhost} onClick={() => toggleStatus(i)}>
                  {s.status === 'active' ? 'Pause' : 'Resume'}
                </button>
              )}
              <button style={btnGhost} onClick={() => editingIdx === i ? cancelEdit() : startEdit(i)}>
                {editingIdx === i ? 'Cancel' : 'Edit'}
              </button>
              <button style={{ ...btnDanger, padding: '4px 8px' }} onClick={() => resetSchedule(i)} title="Reset to manual">
                ×
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Quick presets */}
      <div className="card">
        <div className="card-title">QUICK PRESETS</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button style={btnGhost} title="Screener weekly, Portfolio daily, everything else manual"
            onClick={() => saveMutation.mutate(schedules.map(s => ({
              ...s,
              frequency: s.agent === 'Screener' ? 'Weekly' : s.agent === 'Portfolio Monitor' ? 'Daily' : 'Manual',
              time: s.agent === 'Screener' ? 'Sun 8:00 AM' : s.agent === 'Portfolio Monitor' ? '7:00 AM' : '\u2014',
              status: (s.agent === 'Screener' || s.agent === 'Portfolio Monitor') ? 'active' : 'manual',
            })))}
          >
            Minimal (free)
          </button>
          <button style={{ ...btnGhost, borderColor: 'rgba(245,166,35,0.3)', color: 'var(--accent)' }} title="Full pipeline weekly, Portfolio daily, Library weekly"
            onClick={() => saveMutation.mutate(schedules.map(s => ({
              ...s,
              frequency: s.agent === 'Portfolio Monitor' ? 'Daily' : 'Weekly',
              time: s.agent === 'Screener' ? 'Sun 8:00 AM' : s.agent === 'Portfolio Monitor' ? '7:00 AM' : s.agent === 'Full Pipeline' ? 'Sun 9:00 AM' : s.agent === 'Library Sync' ? 'Mon 6:00 AM' : s.time,
              status: s.agent === 'Thesis Batch' || s.agent === 'Memo Generation' ? 'manual' : 'active',
            })))}
          >
            Recommended
          </button>
          <button style={btnGhost} title="Full pipeline daily, everything automated"
            onClick={() => saveMutation.mutate(schedules.map(s => ({
              ...s,
              frequency: s.agent === 'Thesis Batch' || s.agent === 'Memo Generation' ? 'Manual' : 'Daily',
              time: s.agent === 'Thesis Batch' || s.agent === 'Memo Generation' ? '\u2014' : '7:00 AM',
              status: s.agent === 'Thesis Batch' || s.agent === 'Memo Generation' ? 'manual' : 'active',
            })))}
          >
            Active trader
          </button>
        </div>
        <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          {saveMutation.isPending ? 'Applying preset...' : saveMutation.isSuccess ? 'Preset applied.' : 'Presets configure all schedules at once. You can customize individual agents after applying.'}
        </div>
      </div>
    </div>
  );
}

function SystemTab() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.getConfig });
  const system = config?.system || {};

  const [autonomy, setAutonomy] = useState<AutonomyMode>(system.autonomy_mode || 'suggest');
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetStatus, setResetStatus] = useState<'idle' | 'resetting' | 'done' | 'error'>('idle');
  const [clearConfirm, setClearConfirm] = useState(false);
  const [clearStatus, setClearStatus] = useState<'idle' | 'clearing' | 'done' | 'error'>('idle');

  // Sync autonomy mode when config loads from backend
  useEffect(() => {
    if (system.autonomy_mode) setAutonomy(system.autonomy_mode as AutonomyMode);
  }, [system.autonomy_mode]);

  const dbPath = system.db_path || '~/.fundops/fundops.db';
  const dbSize = system.db_size || '4.2 MB';
  const dbTables = system.db_tables || 'constitution, judgment_events, library_entries, strategy_versions, +9 more';

  const saveAutonomy = useMutation({
    mutationFn: (mode: AutonomyMode) => api.saveConfig('system', { autonomy_mode: mode }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config'] }),
  });

  const handleAutonomy = (mode: AutonomyMode) => {
    setAutonomy(mode);
    saveAutonomy.mutate(mode);
  };

  const exportData = async (format: 'json' | 'sqlite') => {
    // Trigger download via API
    const url = `/api/config/export?format=${format}`;
    window.open(url, '_blank');
  };

  const handleReset = async () => {
    if (!resetConfirm) {
      setResetConfirm(true);
      return;
    }
    setResetStatus('resetting');
    try {
      await api.resetConstitution();
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['strategy'] });
      // Clear the chat session so onboarding restarts
      sessionStorage.removeItem('configure-session-id');
      setResetStatus('done');
      setResetConfirm(false);
      setTimeout(() => setResetStatus('idle'), 3000);
    } catch {
      setResetStatus('error');
      setResetConfirm(false);
    }
  };

  const currentMode = AUTONOMY_MODES.find(m => m.id === autonomy) || AUTONOMY_MODES[1];

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {/* Database */}
      <div className="card">
        <div className="card-title">Database</div>
        <ConfigRow label="Type" value="SQLite" />
        <ConfigRow label="Path" value={dbPath} />
        <ConfigRow label="Size" value={dbSize} />
        <ConfigRow label="Tables" value={dbTables} smallValue />
      </div>

      {/* Data Export */}
      <div className="card">
        <div className="card-title">Data Export</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 8 }}>
          Export all your data. Constitution, judgment events, library entries, conversation history, portfolio snapshots. Your data stays yours.
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button style={btnGhost} onClick={() => exportData('json')}>Export JSON</button>
          <button style={btnGhost} onClick={() => exportData('sqlite')}>Export SQLite</button>
        </div>
      </div>

      {/* Autonomy Mode */}
      <div className="card">
        <div className="card-title">Autonomy Mode</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 8 }}>
          Controls how much the system acts on its own. Applies to feedback loop proposals and behavioral calibration updates.
        </div>
        <div style={{
          display: 'flex', gap: 0,
          border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
          overflow: 'hidden', width: 'fit-content', marginBottom: 8,
        }}>
          {AUTONOMY_MODES.map(m => (
            <button key={m.id} onClick={() => handleAutonomy(m.id)} style={{
              padding: '6px 14px', fontSize: 'var(--text-xs)',
              background: autonomy === m.id ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
              border: 'none', color: autonomy === m.id ? 'var(--accent)' : 'var(--text-secondary)',
              cursor: 'pointer', fontFamily: 'var(--font-ui)',
            }}>
              {m.label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          <strong style={{ color: 'var(--text-secondary)' }}>{currentMode.label}</strong> (current): {currentMode.description}
        </div>
      </div>

      {/* Pipeline Data */}
      <div className="card">
        <div className="card-title">Pipeline Data</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>Clear pipeline data</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Clears all screener, thesis, IC review, and memo results. Portfolio positions and strategy are preserved. Also auto-clears on server restart.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {clearStatus === 'done' && <span style={{ fontSize: 10, color: 'var(--positive)' }}>Cleared</span>}
            {clearStatus === 'error' && <span style={{ fontSize: 10, color: 'var(--negative)' }}>Failed</span>}
            <button style={btnGhost} onClick={async () => {
              if (!clearConfirm) { setClearConfirm(true); return; }
              setClearStatus('clearing');
              try {
                await api.clearPipelineData();
                queryClient.invalidateQueries();
                setClearStatus('done');
                setClearConfirm(false);
                setTimeout(() => setClearStatus('idle'), 3000);
              } catch { setClearStatus('error'); setClearConfirm(false); }
            }} disabled={clearStatus === 'clearing'}>
              {clearStatus === 'clearing' ? 'Clearing...' : clearConfirm ? 'Confirm Clear' : 'Clear Pipeline'}
            </button>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="card" style={{ borderColor: 'rgba(234,67,53,0.3)' }}>
        <div className="card-title" style={{ color: 'var(--negative)' }}>Danger Zone</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>Reset constitution</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Deletes your constitution and starts fresh. All judgment events and library data are preserved.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {resetStatus === 'done' && <span style={{ fontSize: 10, color: 'var(--positive)' }}>Reset complete</span>}
            {resetStatus === 'error' && <span style={{ fontSize: 10, color: 'var(--negative)' }}>Reset failed</span>}
            <button style={btnDanger} onClick={handleReset} disabled={resetStatus === 'resetting'}>
              {resetStatus === 'resetting' ? 'Resetting...' : resetConfirm ? 'Confirm Reset' : 'Reset'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// ConfigRow helper for System tab
// ---------------------------------------------------------------------------

function ConfigRow({ label, value, smallValue }: { label: string; value: string; smallValue?: boolean }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-sm)',
    }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-primary)', fontSize: smallValue ? 10 : 'var(--text-xs)' }}>
        {value}
      </span>
    </div>
  );
}
