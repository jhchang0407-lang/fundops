/**
 * Company Page (/company/:ticker) — read-only dossier over retained FundOps
 * history. Sections: Workflow Map (default) | Financials | Thesis Health.
 *
 * The body is exported as `CompanyDossier` so the Library page can embed the
 * exact same content next to its search panel.
 */
import { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Area,
  Bar,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ApiError,
  exportUrls,
  getCompany,
  getCompanyEvents,
  getCompanyFinancials,
  getCompanyNews,
  getCompanyPeers,
  getOwnership,
  getPrices,
  getThesisHealth,
  runCompanyResearch,
  startResearchRun,
} from '../api/client';
import type {
  CompanyFinancialsResponse,
  CompanyIdentity,
  CompanyLane,
  FinancialPeriod,
  LaneMilestone,
  MilestoneKeyNumber,
  PricePoint,
  PriceRange,
  SnapshotBasis,
  ThesisHealthResponse,
  ThesisWatchItem,
} from '../api/client';
import { ScoreBar } from '../components/workflow/ICScorecard';
import { ask, metricQuestions } from '../components/AskAnywhere';
import {
  fmtBigUsd,
  fmtDate,
  fmtMetric,
  fmtMultiple,
  fmtPrice,
  fmtRatio,
  humanizeLabel,
  pct,
  parseDate,
} from '../utils/formatFinancials';

/* ════════════════════════ shared helpers ════════════════════════ */

const LANES: { key: string; label: string }[] = [
  { key: 'screener', label: 'Screener' },
  { key: 'thesis', label: 'Thesis' },
  { key: 'ic_review', label: 'IC Review' },
  { key: 'memo', label: 'Memo' },
  { key: 'portfolio', label: 'Portfolio' },
];

/** Milestone detail may arrive as a JSON string or an object — normalize. */
function detailRecord(m: LaneMilestone): Record<string, unknown> | null {
  const d = m.detail as unknown;
  if (!d) return null;
  if (typeof d === 'object') return d as Record<string, unknown>;
  if (typeof d === 'string') {
    try {
      const parsed = JSON.parse(d);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  return null;
}

function isKeyNumber(x: unknown): x is MilestoneKeyNumber {
  return (
    !!x &&
    typeof x === 'object' &&
    typeof (x as MilestoneKeyNumber).label === 'string' &&
    ['string', 'number'].includes(typeof (x as MilestoneKeyNumber).value)
  );
}

/** Enriched `detail.key_numbers` when present; legacy scalar entries otherwise. */
function milestoneKeyNumbers(detail: Record<string, unknown> | null): MilestoneKeyNumber[] {
  if (!detail) return [];
  if (Array.isArray(detail.key_numbers)) return detail.key_numbers.filter(isKeyNumber);
  return Object.entries(detail)
    .filter(
      ([k, v]) => !PROVENANCE_KEYS.has(k) && (typeof v === 'number' || typeof v === 'string'),
    )
    .map(([k, v]) => ({ label: humanizeLabel(k), value: v as string | number }));
}

/** Format a key-number value: strings pass through, numbers via the label heuristic. */
function keyNumberText(kn: MilestoneKeyNumber): string {
  if (kn.value == null) return '—';
  if (typeof kn.value === 'string') return kn.value;
  return fmtMetric(kn.label.toLowerCase().replace(/\s+/g, '_'), kn.value);
}

const IC_SCORE_LABELS: { match: RegExp; label: string }[] = [
  { match: /conviction/i, label: 'Conviction' },
  { match: /constitution|fit/i, label: 'Constitution Fit' },
  { match: /data.?quality/i, label: 'Data Quality' },
];

/** Pull the three IC gate scores out of key numbers (when all are present). */
function icScores(keyNumbers: MilestoneKeyNumber[]): { label: string; value: number }[] | null {
  const out: { label: string; value: number }[] = [];
  for (const slot of IC_SCORE_LABELS) {
    const hit = keyNumbers.find((kn) => slot.match.test(kn.label) && typeof kn.value === 'number');
    if (!hit) return null;
    out.push({ label: slot.label, value: hit.value as number });
  }
  return out;
}

const PROVENANCE_KEYS = new Set([
  'run_id',
  'run',
  'constitution_version',
  'constitution_version_id',
  'artifact_id',
  'evidence_bundle_id',
  'summary',
  'title',
  'date',
  'kind',
  'status',
  'ticker',
  'entity_id',
]);

/* ════════════════════════ Workflow Map ════════════════════════ */

function MilestoneDrawer({
  laneKey,
  laneLabel,
  milestone,
  onClose,
}: {
  laneKey: string;
  laneLabel: string;
  milestone: LaneMilestone;
  onClose: () => void;
}) {
  const detail = detailRecord(milestone);
  const keyNumbers = milestoneKeyNumbers(detail);
  const scores = laneKey === 'ic_review' ? icScores(keyNumbers) : null;
  // Score-bar rows replace their kv entries; everything else stays in the grid.
  const gridNumbers = scores
    ? keyNumbers.filter((kn) => !IC_SCORE_LABELS.some((slot) => slot.match.test(kn.label)))
    : keyNumbers;
  const constitution = detail?.constitution_version ?? detail?.constitution_version_id;
  const runId = detail?.run_id ?? detail?.run;
  return (
    <aside className="preview-drawer" aria-label="Milestone preview">
      <div className="preview-drawer-head">
        <button className="reader-popup-close" onClick={onClose} aria-label="Close preview">
          ✕
        </button>
        <span className="section-kicker" style={{ marginLeft: 4 }}>
          {laneLabel}
        </span>
        {milestone.artifact_id && (
          <Link
            to={`/artifact/${milestone.artifact_id}`}
            className="btn btn-ghost"
            style={{ marginLeft: 'auto', padding: '4px 10px', fontSize: 'var(--text-xs)', textDecoration: 'none' }}
          >
            Open artifact →
          </Link>
        )}
      </div>
      <div className="preview-drawer-body preview-drawer-dense">
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, lineHeight: 1.5, marginBottom: 6 }}>
          {milestone.title}
        </div>
        <div className="kv-grid" style={{ marginBottom: 10 }}>
          <span className="kv-key">Date</span>
          <span className="kv-val">{fmtDate(milestone.date)}</span>
          <span className="kv-key">Stage</span>
          <span className="kv-val">{laneLabel}</span>
          {milestone.status && (
            <>
              <span className="kv-key">Status</span>
              <span className="kv-val">{milestone.status}</span>
            </>
          )}
        </div>
        {milestone.summary && (
          <>
            <div className="section-label">Summary</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 10 }}>
              {milestone.summary}
            </div>
          </>
        )}
        {scores && (
          <div style={{ marginBottom: 10 }}>
            <div className="section-label">Gate Scores</div>
            {scores.map((s) => (
              <ScoreBar key={s.label} label={s.label} value={s.value} />
            ))}
          </div>
        )}
        {gridNumbers.length > 0 && (
          <>
            <div className="section-label">Key Numbers</div>
            <div className="preview-kn-grid" style={{ marginBottom: 10 }}>
              {gridNumbers.map((kn, i) => (
                <span key={`${kn.label}-${i}`} style={{ display: 'contents' }}>
                  <span className="preview-kn-label">{kn.label}</span>
                  <span className="preview-kn-value">{keyNumberText(kn)}</span>
                </span>
              ))}
            </div>
          </>
        )}
        <div className="inline-metadata">
          {constitution != null && <span>Constitution {String(constitution)}</span>}
          {runId != null && <span>Run {String(runId)}</span>}
          {constitution == null && runId == null && <span>Provenance retained on the artifact record</span>}
        </div>
      </div>
    </aside>
  );
}

function WorkflowMap({ lanes }: { lanes: CompanyLane[] }) {
  const [selected, setSelected] = useState<{ lane: string; index: number } | null>(null);
  const [showAll, setShowAll] = useState<Record<string, boolean>>({});
  const byKey = useMemo(() => new Map(lanes.map((l) => [l.lane, l.milestones])), [lanes]);

  const selectedLane = selected ? LANES.find((l) => l.key === selected.lane) : null;
  const selectedMilestone = selected ? (byKey.get(selected.lane) ?? [])[selected.index] : null;

  return (
    <div>
      {LANES.map(({ key, label }) => {
        const milestones = byKey.get(key) ?? [];
        const expanded = !!showAll[key];
        const visible = expanded ? milestones : milestones.slice(0, 3);
        return (
          <div className="lane-row" key={key}>
            <span className="lane-label">{label}</span>
            {milestones.length === 0 ? (
              <span className="lane-empty">Not reached</span>
            ) : (
              <div className="lane-cards">
                {visible.map((m, i) => (
                  <button
                    key={`${m.date}-${i}`}
                    className={`milestone-card${selected?.lane === key && selected.index === i ? ' selected' : ''}`}
                    onClick={() => setSelected({ lane: key, index: i })}
                  >
                    <div className="milestone-date">{fmtDate(m.date)}</div>
                    <div className="milestone-title">{m.title}</div>
                    {m.status && (
                      <div className="milestone-date" style={{ marginTop: 2 }}>
                        {m.status}
                      </div>
                    )}
                  </button>
                ))}
                {milestones.length > 3 && (
                  <button
                    className="btn btn-ghost"
                    style={{ fontSize: 'var(--text-xs)', padding: '4px 8px', alignSelf: 'center' }}
                    onClick={() => setShowAll((s) => ({ ...s, [key]: !expanded }))}
                  >
                    {expanded ? 'show fewer' : `show all (${milestones.length})`}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
      {selectedLane && selectedMilestone && (
        <MilestoneDrawer
          laneKey={selectedLane.key}
          laneLabel={selectedLane.label}
          milestone={selectedMilestone}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

/* ════════════════════════ Financials ════════════════════════ */

type StatementKey = 'income' | 'balance' | 'cashflow';

const SNAPSHOT_SLOTS: { key: string; label: string; fmt: (v: number | null | undefined) => string }[] = [
  { key: 'market_cap', label: 'Market Cap', fmt: fmtBigUsd },
  { key: 'pe', label: 'P/E', fmt: fmtMultiple },
  { key: 'revenue_growth', label: 'Rev Growth', fmt: (v) => pct(v) },
  { key: 'gross_margin', label: 'Gross Margin', fmt: (v) => pct(v) },
  { key: 'operating_margin', label: 'Op Margin', fmt: (v) => pct(v) },
  { key: 'fcf_yield', label: 'FCF Yield', fmt: (v) => pct(v) },
  { key: 'roic', label: 'ROIC', fmt: (v) => pct(v) },
  { key: 'debt_equity', label: 'Debt/Equity', fmt: fmtRatio },
];

function isFinancialPeriod(x: unknown): x is FinancialPeriod {
  return (
    !!x &&
    typeof x === 'object' &&
    typeof (x as FinancialPeriod).period_end === 'string' &&
    typeof (x as FinancialPeriod).metrics === 'object' &&
    (x as FinancialPeriod).metrics !== null
  );
}

// Point-in-time price/market metrics — never financial-statement lines
// (mirrors backend MARKET_METRICS; the API already strips these, this guards
// the regex fallback when an older server returns only generic periods).
const MARKET_RE = /momentum|volatility|avg_volume|avg_dollar_volume|below_52w|^price$|market_cap/;

function classify(metric: string): StatementKey {
  const m = metric.toLowerCase();
  if (/cash_flow|capex|capital_expenditure|fcf|free_cash|dividend|buyback|repurchase|depreciation|amortization|financing|investing|stock_comp/.test(m)) {
    return 'cashflow';
  }
  if (/asset|liabilit|equity|^cash|cash_and|debt|inventory|receivable|payable|book_value|working_capital|goodwill|shares_outstanding/.test(m)) {
    return 'balance';
  }
  return 'income';
}

function statementPeriods(
  block: CompanyFinancialsResponse['annual'] | CompanyFinancialsResponse['quarterly'] | undefined,
  stmt: StatementKey,
): FinancialPeriod[] {
  if (!block) return [];
  // Backend supplies catalog-classified, normalized income/balance/cashflow
  // sections (one column per fiscal period, market technicals excluded). Prefer
  // them; only fall back to regex classification for legacy generic payloads.
  const direct = block[stmt];
  if (Array.isArray(direct) && direct.length > 0) return direct.filter(isFinancialPeriod);
  const periods = (block.periods ?? []).filter(isFinancialPeriod);
  return periods.map((p) => ({
    period_end: p.period_end,
    metrics: Object.fromEntries(
      Object.entries(p.metrics).filter(
        ([k]) => !MARKET_RE.test(k.toLowerCase()) && classify(k) === stmt,
      ),
    ),
  }));
}

function basisLabel(b: SnapshotBasis | null | undefined): string {
  if (!b || !b.period_end) return '';
  const year = b.period_end.slice(0, 4);
  if (b.period_type === 'annual') return `FY${year}`;
  if (b.period_type === 'ttm') return `TTM ${b.period_end.slice(0, 7)}`;
  if (b.period_type === 'projection') return `proj ${b.period_end}`;
  return b.period_end.slice(0, 7); // quarterly → YYYY-MM
}

function sourceSummary(
  metric: string,
  data: CompanyFinancialsResponse | undefined,
): string {
  const source = data?.sources?.[metric];
  const basis = basisLabel(data?.snapshot_basis?.[metric]);
  if (!source) return basis ? `${basis} · source detail not retained` : 'Source detail not retained';
  const lineage = source.lineage && typeof source.lineage === 'object'
    ? (source.lineage as Record<string, unknown>)
    : {};
  const formula = typeof lineage.formula === 'string' ? lineage.formula : null;
  const fact = source.facts?.[0];
  const parts = [
    basis,
    source.is_calculated ? 'calculated' : 'reported',
    fact?.accession ? `accession ${fact.accession}` : null,
    fact?.concept ?? formula,
  ].filter(Boolean);
  return parts.join(' · ');
}

function DataIntegrityPanel({ data }: { data: CompanyFinancialsResponse | undefined }) {
  const q = data?.data_quality;
  const meta = data?.source_metadata;
  if (!q && !meta) return null;
  const missing = q?.missing_metrics ?? [];
  const stale = q?.stale_metrics ?? [];
  const unmapped = q?.mapping_gaps?.counts?.unmapped ?? 0;
  const rejected = q?.mapping_gaps?.counts?.rejected ?? 0;
  const suspicious = q?.suspicious_values ?? [];
  const issueCount = q?.issues?.length ?? 0;
  const qualityClass = meta?.quality_result === 'pass' ? 'health-chip intact' : 'health-chip watching';
  const qualityText = meta?.quality_result === 'pass' ? 'quality pass' : `${issueCount} quality signal${issueCount === 1 ? '' : 's'}`;
  const tagRows = q?.mapping_gaps?.tags ?? [];
  return (
    <div style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', padding: '10px 0', margin: '10px 0 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <span className="section-label" style={{ marginBottom: 0 }}>
          Data Integrity
        </span>
        <span className={qualityClass}>{qualityText}</span>
        {meta?.source_hash && <span className="inline-metadata">source {meta.source_hash}</span>}
      </div>
      <div className="kv-grid" style={{ maxWidth: 760, marginBottom: 8 }}>
        <span className="kv-key">Latest filing period</span>
        <span className="kv-val">{meta?.latest_filing_period ? fmtDate(meta.latest_filing_period) : '—'}</span>
        <span className="kv-key">Latest filing</span>
        <span className="kv-val">
          {[meta?.latest_filing_form, meta?.latest_filing_date ? fmtDate(meta.latest_filing_date) : null].filter(Boolean).join(' · ') || '—'}
        </span>
        <span className="kv-key">Latest price</span>
        <span className="kv-val">{meta?.latest_price_date ? fmtDate(meta.latest_price_date) : '—'}</span>
        <span className="kv-key">Catalog / mapping</span>
        <span className="kv-val">{[meta?.catalog_version, meta?.mapping_version].filter(Boolean).join(' / ') || '—'}</span>
      </div>
      <div className="inline-metadata" style={{ gap: 8, flexWrap: 'wrap' }}>
        {missing.length > 0 && <span>Missing: {missing.map(humanizeLabel).slice(0, 6).join(', ')}</span>}
        {stale.length > 0 && <span>Stale: {stale.map(humanizeLabel).slice(0, 6).join(', ')}</span>}
        {unmapped > 0 && <span>{unmapped} unmapped tag{unmapped === 1 ? '' : 's'}</span>}
        {rejected > 0 && <span>{rejected} rejected mapping{rejected === 1 ? '' : 's'}</span>}
        {suspicious.length > 0 && <span>{suspicious.length} suspicious value{suspicious.length === 1 ? '' : 's'}</span>}
        {(q?.price_stale) && <span>price stale</span>}
        {missing.length === 0 && stale.length === 0 && unmapped === 0 && suspicious.length === 0 && !q?.price_stale && (
          <span>Required metrics and price basis are current for this profile.</span>
        )}
      </div>
      {tagRows.length > 0 && (
        <div className="empty-note" style={{ padding: '6px 0 0', fontSize: 'var(--text-xs)' }}>
          Unmapped examples: {tagRows.slice(0, 3).map((t) => t.field_label || t.concept).join(' · ')}
        </div>
      )}
    </div>
  );
}

/* ── price chart (bulk price history, ADR-0059) ── */

const PRICE_RANGES: { key: PriceRange; label: string }[] = [
  { key: '1m', label: '1M' },
  { key: '6m', label: '6M' },
  { key: '1y', label: '1Y' },
  { key: '5y', label: '5Y' },
];

function priceTick(range: PriceRange, iso: string): string {
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return range === '1y' || range === '5y'
    ? d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function PriceTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload?: PricePoint }[];
}) {
  const point = active && payload && payload.length > 0 ? payload[0]?.payload : undefined;
  if (!point) return null;
  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '6px 10px',
        fontFamily: 'var(--font-data)',
        fontSize: 11,
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>{fmtDate(point.date)}</div>
      <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{fmtPrice(point.close)}</div>
    </div>
  );
}

const BENCHMARK_SYMBOL = '^GSPC';

/** Merge ticker + benchmark closes by date, both indexed to 100. */
function indexedOverlay(
  prices: PricePoint[],
  bench: PricePoint[],
): { date: string; stock: number; benchmark?: number }[] {
  if (!prices.length) return [];
  const base = prices[0].close;
  const benchByDate = new Map(bench.map((b) => [b.date, b.close]));
  const benchBase = bench.length ? bench[0].close : null;
  return prices.map((p) => {
    const b = benchByDate.get(p.date);
    return {
      date: p.date,
      stock: Math.round((p.close / base) * 10000) / 100,
      benchmark:
        b != null && benchBase
          ? Math.round((b / benchBase) * 10000) / 100
          : undefined,
    };
  });
}

function PriceChart({ ticker }: { ticker: string }) {
  const [range, setRange] = useState<PriceRange>('1y');
  const [touched, setTouched] = useState(false);
  const [overlay, setOverlay] = useState(false);
  const { data, isError } = useQuery({
    queryKey: ['company-prices', ticker, range],
    queryFn: () => getPrices(ticker, range),
    retry: 1,
  });
  const { data: benchData } = useQuery({
    queryKey: ['company-prices', BENCHMARK_SYMBOL, range],
    queryFn: () => getPrices(BENCHMARK_SYMBOL, range),
    enabled: overlay,
    retry: 1,
  });
  const prices = data?.prices ?? [];
  const bench = benchData?.prices ?? [];
  const overlayData = overlay ? indexedOverlay(prices, bench) : [];
  const hasVolume = prices.some((p) => (p.volume ?? 0) > 0);

  // No retained price history → render nothing while it's likely still syncing;
  // but if the backend says the ticker is genuinely dataless/delisted, show that
  // reason instead of a silent void.
  if (isError) return null;
  if (!touched && prices.length === 0 && !data?.empty_reason) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span className="section-label" style={{ marginBottom: 0 }}>
          Price
        </span>
        <div className="seg-control">
          {PRICE_RANGES.map(({ key, label }) => (
            <button
              key={key}
              className={`seg-option${range === key ? ' active' : ''}`}
              onClick={() => {
                setTouched(true);
                setRange(key);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className={`seg-option${overlay ? ' active' : ''}`}
          style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}
          onClick={() => setOverlay((v) => !v)}
          title="Overlay the S&P 500, both indexed to 100"
        >
          vs S&P 500
        </button>
        {overlay && bench.length === 0 && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
            benchmark series arrives with the daily sync
          </span>
        )}
      </div>
      {prices.length === 0 ? (
        <div className="empty-note">{data?.empty_reason || 'No price history retained for this range.'}</div>
      ) : overlay ? (
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={overlayData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              minTickGap={56}
              tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}
              tickFormatter={(v: string) => priceTick(range, v)}
            />
            <YAxis
              domain={['auto', 'auto']}
              width={52}
              orientation="right"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}
              tickFormatter={(v: number) => `${Math.round(v)}`}
            />
            <Tooltip
              cursor={{ stroke: 'var(--border-hover)', strokeWidth: 1 }}
              contentStyle={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-data)',
                fontSize: 11,
              }}
            />
            <Line
              type="monotone"
              dataKey="stock"
              name={ticker}
              stroke="var(--accent)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="benchmark"
              name="S&P 500"
              stroke="var(--text-muted)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={hasVolume ? 260 : 220}>
          <ComposedChart data={prices} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`price-fill-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.16} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              minTickGap={56}
              tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}
              tickFormatter={(v: string) => priceTick(range, v)}
            />
            <YAxis
              yAxisId="price"
              domain={['auto', 'auto']}
              width={52}
              orientation="right"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}
              tickFormatter={(v: number) => `$${v >= 100 ? Math.round(v) : v.toFixed(1)}`}
            />
            {hasVolume && (
              <YAxis yAxisId="volume" hide domain={[0, (max: number) => max * 4]} />
            )}
            <Tooltip
              content={<PriceTooltip />}
              cursor={{ stroke: 'var(--border-hover)', strokeWidth: 1 }}
            />
            {hasVolume && (
              <Bar
                yAxisId="volume"
                dataKey="volume"
                fill="var(--border-hover)"
                opacity={0.5}
                isAnimationActive={false}
              />
            )}
            <Area
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke="var(--accent)"
              strokeWidth={1.5}
              fill={`url(#price-fill-${ticker})`}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function FinancialsTab({ ticker }: { ticker: string }) {
  const [stmt, setStmt] = useState<StatementKey>('income');
  const [freq, setFreq] = useState<'annual' | 'quarterly'>('annual');
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['company-financials', ticker],
    queryFn: () => getCompanyFinancials(ticker),
  });

  if (isPending) return <div className="stage-empty">Loading financials…</div>;
  if (isError) return <div className="stage-empty">Financials unavailable: {(error as Error).message}</div>;

  const snapshot = data?.snapshot ?? {};
  const snapshotBasis = data?.snapshot_basis ?? {};
  const seenLabels = new Set<string>();
  const periods = statementPeriods(freq === 'annual' ? data?.annual : data?.quarterly, stmt)
    .slice()
    .sort((a, b) => (a.period_end < b.period_end ? 1 : -1)) // newest left
    // One column per fiscal period: drop any residual duplicate-label columns
    // (backend already normalizes; this guards legacy/regex-fallback payloads).
    .filter((p) => {
      const label = freq === 'annual' ? p.period_end.slice(0, 4) : p.period_end.slice(0, 7);
      if (seenLabels.has(label)) return false;
      seenLabels.add(label);
      return true;
    });

  const metricRows: string[] = [];
  for (const p of periods) {
    for (const k of Object.keys(p.metrics)) {
      if (!metricRows.includes(k)) metricRows.push(k);
    }
  }

  return (
    <div>
      <PriceChart ticker={ticker} />
      <div className="fin-strip">
        {SNAPSHOT_SLOTS.map((s) => {
          const display = s.fmt(snapshot[s.key]);
          const source = sourceSummary(s.key, data);
          return (
            <div
              className="kpi-mini askable"
              key={s.key}
              title={`Click to ask about this · ${source}`}
              onClick={(e) =>
                ask(e, {
                  title: `${ticker} · ${s.label} ${display}`,
                  questions: metricQuestions(ticker, s.label, display),
                })
              }
            >
              <div className="kpi-mini-label">{s.label}</div>
              <div className="kpi-mini-value">{display}</div>
              {basisLabel(snapshotBasis[s.key]) && (
                <div
                  style={{
                    fontSize: '10px', marginTop: 2,
                    color: snapshotBasis[s.key]?.stale ? 'var(--amber-ink, var(--negative))' : 'var(--text-muted)',
                  }}
                  title={source}
                >
                  {basisLabel(snapshotBasis[s.key])}{snapshotBasis[s.key]?.stale ? ' · stale' : ''}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', margin: '-4px 0 10px' }}>
        SEC companyfacts · each figure labeled with its reporting period · click any number to ask about it
      </div>
      <DataIntegrityPanel data={data} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <span className="section-label" style={{ marginBottom: 0 }}>
          Full Financials
        </span>
        <div className="seg-control">
          {(
            [
              ['income', 'Income'],
              ['balance', 'Balance'],
              ['cashflow', 'Cash Flow'],
            ] as [StatementKey, string][]
          ).map(([k, label]) => (
            <button key={k} className={`seg-option${stmt === k ? ' active' : ''}`} onClick={() => setStmt(k)}>
              {label}
            </button>
          ))}
        </div>
        <div className="seg-control">
          {(['annual', 'quarterly'] as const).map((f) => (
            <button key={f} className={`seg-option${freq === f ? ' active' : ''}`} onClick={() => setFreq(f)}>
              {f === 'annual' ? 'Annual' : 'Quarterly'}
            </button>
          ))}
        </div>
        {data?.as_of && <span className="inline-metadata">as of {fmtDate(data.as_of)}</span>}
      </div>

      {periods.length === 0 ? (
        <div className="stage-empty">
          {data?.coverage?.notes?.[0]
            ?? `No ${freq} ${stmt === 'cashflow' ? 'cash-flow' : stmt} data is retained for this company.`}
        </div>
      ) : (
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                {periods.map((p) => (
                  <th key={p.period_end} className="num">
                    {freq === 'annual' ? p.period_end.slice(0, 4) : p.period_end.slice(0, 7)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metricRows.map((metric) => (
                <tr key={metric}>
                  <td style={{ color: 'var(--text-secondary)' }}>{humanizeLabel(metric)}</td>
                  {periods.map((p) => {
                    const v = fmtMetric(metric, p.metrics[metric]);
                    const when = freq === 'annual' ? p.period_end.slice(0, 4) : p.period_end.slice(0, 7);
                    return (
                      <td
                        key={p.period_end}
                        className={`num${v === '—' ? '' : ' askable'}`}
                        title={v === '—' ? undefined : 'Click to ask about this'}
                        style={v === '—' ? undefined : { cursor: 'pointer' }}
                        onClick={v === '—' ? undefined : (e) =>
                          ask(e, {
                            title: `${ticker} · ${humanizeLabel(metric)} (${when}) ${v}`,
                            questions: [
                              `Why is ${ticker}'s ${humanizeLabel(metric).toLowerCase()} ${v} for ${when}?`,
                              `Show ${ticker}'s ${humanizeLabel(metric).toLowerCase()} history`,
                              `Compare ${ticker} with its peers on ${humanizeLabel(metric).toLowerCase()}`,
                            ],
                          })
                        }
                      >
                        {v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(data?.coverage?.notes?.length ?? 0) > 0 && periods.length > 0 && (
        <div className="empty-note" style={{ padding: '6px 0 0', fontSize: 'var(--text-xs)' }}>
          {data!.coverage!.notes.map((nt, i) => (
            <div key={i}>ⓘ {nt}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ════════════════════════ Thesis Health ════════════════════════ */

const COMPARATOR_SYMBOLS: Record<string, string> = {
  '>=': '≥',
  '<=': '≤',
  '>': '>',
  '<': '<',
  '==': '=',
  '=': '=',
  gte: '≥',
  lte: '≤',
  gt: '>',
  lt: '<',
  eq: '=',
};

const LOOKBACK_LABELS: Record<string, string> = {
  yoy: 'YoY',
  ttm: 'TTM',
  latest: 'latest',
  annual: 'annual',
  multi_period_avg: 'multi-period avg',
};

const HEALTH_GROUPS: { key: string; label: string; statuses: string[]; dot: string }[] = [
  { key: 'broken', label: 'Broken', statuses: ['broken'], dot: 'var(--negative)' },
  { key: 'watch', label: 'Watch', statuses: ['watch'], dot: 'var(--warning)' },
  { key: 'unknown', label: 'Unknown', statuses: ['unknown', 'data_gap'], dot: 'var(--text-muted)' },
  { key: 'intact', label: 'Intact', statuses: ['intact'], dot: 'var(--positive)' },
];

function summaryChipClass(label: string | null | undefined): string {
  if (label === 'Intact') return 'health-chip intact';
  if (label === 'Watching') return 'health-chip watching';
  if (label === 'Broken') return 'health-chip broken';
  return 'health-chip';
}

function conditionLine(item: ThesisWatchItem): string {
  const parts: string[] = [];
  if (item.metric) {
    const cmp = item.comparator ? (COMPARATOR_SYMBOLS[item.comparator] ?? item.comparator) : null;
    parts.push([item.metric, cmp, item.threshold != null ? String(item.threshold) : null].filter(Boolean).join(' '));
  }
  if (item.cadence) parts.push(item.cadence);
  if (item.lookback) parts.push(LOOKBACK_LABELS[item.lookback] ?? item.lookback);
  return parts.join(' · ');
}

function ThesisHealthTab({ ticker }: { ticker: string }) {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['thesis-health', ticker],
    queryFn: () => getThesisHealth(ticker),
  });

  if (isPending) return <div className="stage-empty">Loading thesis health…</div>;
  if (isError) return <div className="stage-empty">Thesis health unavailable: {(error as Error).message}</div>;
  const view: ThesisHealthResponse | undefined = data;
  if (!view) return null;

  if (!view.items || view.items.length === 0) {
    return (
      <div className="stage-empty">
        {view.empty_reason || 'No thesis-health plan yet — a completed investment memo creates one automatically.'}
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <span className={summaryChipClass(view.summary_label)}>{view.summary_label ?? 'Not Checked'}</span>
        {view.active_source && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            Tracking memo from{' '}
            <Link to={`/artifact/${view.active_source.memo_artifact_id}`} style={{ color: 'var(--accent)' }}>
              {fmtDate(view.active_source.memo_date)}
            </Link>
          </span>
        )}
      </div>

      {HEALTH_GROUPS.map((group) => {
        const items = view.items.filter((i) => group.statuses.includes(i.status));
        if (items.length === 0) return null;
        return (
          <div key={group.key} style={{ marginBottom: 16 }}>
            <div className="section-label">
              <span className="health-dot" style={{ background: group.dot }} />
              {group.label} ({items.length})
            </div>
            {items.map((item) => (
              <div className="watch-item" key={String(item.id)} title={item.why_matters ?? undefined}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{item.title}</span>
                  {item.item_type && <span className="badge badge-muted">{item.item_type.replace(/_/g, ' ')}</span>}
                  {item.data_gap && (
                    <span className="muted" style={{ fontSize: 'var(--text-xs)' }}>
                      data gap — metric not currently computable from retained facts
                    </span>
                  )}
                </div>
                <div
                  style={{
                    display: 'flex',
                    gap: 14,
                    flexWrap: 'wrap',
                    marginTop: 4,
                    fontFamily: 'var(--font-data)',
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {conditionLine(item) && <span>{conditionLine(item)}</span>}
                  <span>
                    current{' '}
                    <span style={{ color: 'var(--text-primary)' }}>
                      {item.current_value != null ? String(item.current_value) : '—'}
                    </span>
                  </span>
                  <span className="muted">checked {fmtDate(item.last_checked_at)}</span>
                </div>
              </div>
            ))}
          </div>
        );
      })}

      {view.history && view.history.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div className="section-label">Check History</div>
          <div className="card" style={{ padding: '8px 12px' }}>
            {view.history.map((h, i) => (
              <div className="alert-row" key={h.refresh_id ?? i} style={{ fontSize: 'var(--text-xs)' }}>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-secondary)', width: 110, flexShrink: 0 }}>
                  {fmtDate(h.ran_at)}
                </span>
                <span className="badge badge-muted">{h.metadata_only ? 'metadata-only' : 'recalculated'}</span>
                <span className="muted">{h.trigger || ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="inline-metadata">
        <span>Filings checked {fmtDate(view.filings_last_checked)}</span>
        <span>recalculated {fmtDate(view.recalculated_at)}</span>
        <span>checks run from the Dashboard — this view is the retained record</span>
      </div>
    </div>
  );
}

/* ════════════════════════ Ownership ════════════════════════ */

function txnSide(txn: string | null | undefined): 'buy' | 'sell' | null {
  const t = (txn ?? '').toLowerCase();
  if (t.includes('buy') || t.includes('purchase') || t.includes('acqui') || t === 'p' || t === 'a') {
    return 'buy';
  }
  if (t.includes('sell') || t.includes('sale') || t.includes('dispos') || t === 's' || t === 'd') {
    return 'sell';
  }
  return null;
}

function txnChipStyle(side: 'buy' | 'sell' | null): CSSProperties {
  return {
    display: 'inline-block',
    padding: '1px 8px',
    borderRadius: 'var(--radius-full)',
    fontFamily: 'var(--font-data)',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    color: side === 'buy' ? 'var(--positive)' : side === 'sell' ? 'var(--negative)' : 'var(--text-muted)',
    background:
      side === 'buy'
        ? 'rgba(52, 168, 83, 0.12)'
        : side === 'sell'
          ? 'rgba(234, 67, 53, 0.12)'
          : 'var(--bg-tertiary)',
  };
}

function OwnershipTab({ ticker }: { ticker: string }) {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['company-ownership', ticker],
    queryFn: () => getOwnership(ticker),
  });

  if (isPending) return <div className="stage-empty">Loading ownership…</div>;
  if (isError) return <div className="stage-empty">Ownership unavailable: {(error as Error).message}</div>;

  const insiders = (data?.insiders ?? [])
    .slice()
    .sort((a, b) => (a.as_of < b.as_of ? 1 : -1))
    .slice(0, 50); // newest first, retained record capped for the dossier view
  const holders = data?.largest_holders ?? [];

  if (insiders.length === 0 && holders.length === 0) {
    return (
      <div className="stage-empty">
        {data?.empty_reason ||
          'No ownership history retained yet — runs with the next data sync.'}
      </div>
    );
  }

  return (
    <div>
      {holders.length === 0 && insiders.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="section-label">Largest Holders — 5%+ Schedules (13D/G)</div>
          <div className="empty-note">
            {data?.holders_reason ||
              'No 5%+ beneficial-owner schedules (13D/G) retained for this ticker yet — '
              + 'these are filed only when a holder crosses 5%, and arrive as the filings index syncs.'}
          </div>
        </div>
      )}
      {holders.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="section-label">Largest Holders — 5%+ Schedules (13D/G)</div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Holder</th>
                  <th className="num">% of Class</th>
                  <th className="num">Shares</th>
                  <th>Schedule</th>
                  <th>As of</th>
                </tr>
              </thead>
              <tbody>
                {holders.map((h, i) => (
                  <tr key={`${h.owner_name}-${i}`}>
                    <td>{h.owner_name}</td>
                    <td className="num">{h.percent == null ? '—' : `${h.percent.toFixed(1)}%`}</td>
                    <td className="num">{h.shares == null ? '—' : h.shares.toLocaleString()}</td>
                    <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
                      {h.form || '—'}
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                      {fmtDate(h.as_of)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="section-label">Insider Transactions</div>
      {insiders.length === 0 && (
        <div className="stage-empty">No insider transactions retained yet — runs with the next data sync.</div>
      )}
      {insiders.length > 0 && (
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Insider</th>
              <th>Role</th>
              <th>Type</th>
              <th className="num">Shares</th>
              <th className="num">Value</th>
            </tr>
          </thead>
          <tbody>
            {insiders.map((t, i) => {
              const side = txnSide(t.txn_type);
              return (
                <tr key={`${t.as_of}-${t.owner_name ?? ''}-${i}`}>
                  <td
                    style={{
                      fontFamily: 'var(--font-data)',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {fmtDate(t.as_of)}
                  </td>
                  <td>{t.owner_name || '—'}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{t.owner_role || '—'}</td>
                  <td>
                    <span style={txnChipStyle(side)}>
                      {(t.txn_type || 'n/a').replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="num">{t.shares == null ? '—' : t.shares.toLocaleString()}</td>
                  <td className="num">{t.value == null ? '—' : fmtBigUsd(t.value)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      )}
      <div className="inline-metadata" style={{ marginTop: 10 }}>
        <span>read-only retained record — newest 50 transactions shown</span>
        <span>
          {data?.institutions_reason ||
            'institutional 13F holdings are not ingested — 13F INFO TABLE filings key '
            + 'positions by CUSIP and there is no local CUSIP→ticker map'}
        </span>
      </div>
    </div>
  );
}

/* ════════════════════════ identity strip + dossier ════════════════════════ */

function IdentityStrip({ identity }: { identity: CompanyIdentity }) {
  const verdict = identity.latest_verdict?.toLowerCase() ?? null;
  return (
    <div className="identity-strip">
      <span className="ticker" style={{ fontSize: 'var(--text-2xl)', fontWeight: 700 }}>
        {identity.ticker}
      </span>
      <div>
        <div style={{ fontSize: 'var(--text-base)', fontWeight: 600 }}>{identity.name || '—'}</div>
        <div className="ticker-meta-line">
          {[identity.sector, identity.industry].filter(Boolean).join(' · ') || '—'}
        </div>
      </div>
      <span className="num" style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginLeft: 'auto' }}>
        {fmtPrice(identity.price)}
      </span>
      {identity.latest_stage && <span className="badge badge-muted">{humanizeLabel(identity.latest_stage)}</span>}
      {identity.latest_verdict &&
        (verdict === 'pass' ? (
          <span className="verdict-pass">PASS</span>
        ) : verdict === 'fail' ? (
          <span className="verdict-fail">FAIL</span>
        ) : (
          <span className="badge badge-muted">{identity.latest_verdict.replace(/_/g, ' ')}</span>
        ))}
      {identity.owned && <span className="status-badge status-held">OWNED</span>}
    </div>
  );
}

export function CompanyDossier({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<
    'map' | 'financials' | 'health' | 'ownership' | 'events' | 'peers' | 'research'
  >('map');
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['company', ticker],
    queryFn: () => getCompany(ticker),
    retry: (failureCount, err) => !(err instanceof ApiError && err.status === 404) && failureCount < 2,
  });

  if (isPending) return <div className="stage-empty">Opening dossier for {ticker}…</div>;

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="stage-empty" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontFamily: 'var(--font-data)', color: 'var(--accent)', marginBottom: 6 }}>{ticker}</div>
          No retained history for {ticker}. Run research to create some.
        </div>
      );
    }
    return (
      <div className="stage-empty">
        Could not load {ticker}: {(error as Error).message}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <IdentityStrip identity={data.identity} />
      {data.identity.status === 'quarantined' && (
        <div className="empty-note" style={{ margin: '8px 0', fontSize: 'var(--text-xs)' }}>
          ⓘ {data.identity.status_reason
            ? `Not actively researched — ${data.identity.status_reason}.`
            : 'Not actively researched (delisted or dataless) — shown for reference only.'}{' '}
          It is excluded from screens, peer groups, and the Markets browser.
        </div>
      )}
      <div className="detail-tabs">
        {(
          [
            ['map', 'Workflow Map'],
            ['financials', 'Financials'],
            ['health', 'Thesis Health'],
            ['ownership', 'Ownership'],
            ['events', 'Events'],
            ['peers', 'Peers'],
            ['research', 'Research'],
          ] as const
        ).map(([k, label]) => (
          <button key={k} className={`detail-tab${tab === k ? ' active' : ''}`} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'map' && <WorkflowMap lanes={data.lanes} />}
      {tab === 'financials' && <FinancialsTab ticker={ticker} />}
      {tab === 'health' && <ThesisHealthTab ticker={ticker} />}
      {tab === 'ownership' && <OwnershipTab ticker={ticker} />}
      {tab === 'events' && <EventsTab ticker={ticker} />}
      {tab === 'peers' && <PeersTab ticker={ticker} />}
      {tab === 'research' && <ResearchTab ticker={ticker} />}
    </div>
  );
}

/* ════════════════════════ Events tab ════════════════════════ */

const EVENT_KIND_STYLE: Record<string, { label: string; color: string }> = {
  earnings: { label: 'Earnings', color: 'var(--accent)' },
  dividend: { label: 'Dividend', color: 'var(--info)' },
  split: { label: 'Split', color: 'var(--info)' },
  filing: { label: 'Filing', color: 'var(--text-secondary)' },
  insider_cluster: { label: 'Insiders', color: 'var(--warning)' },
};

function EventsTab({ ticker }: { ticker: string }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['company-events', ticker],
    queryFn: () => getCompanyEvents(ticker),
  });
  if (isPending) return <div className="stage-empty">Loading events…</div>;
  if (isError) return <div className="stage-empty">Events unavailable.</div>;
  const events = data?.events ?? [];
  if (events.length === 0) {
    return (
      <div className="stage-empty">
        {data?.empty_reason ||
          'No events retained yet — filing events arrive with daily syncs; earnings and '
          + 'dividend dates are pulled for held and watchlisted tickers.'}
      </div>
    );
  }
  return (
    <div>
      <div className="table-shell" style={{ marginBottom: 14 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 110 }}>Date</th>
              <th style={{ width: 100 }}>Type</th>
              <th>Event</th>
              <th style={{ width: 110 }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => {
              const k = EVENT_KIND_STYLE[e.kind] ?? { label: humanizeLabel(e.kind), color: 'var(--text-secondary)' };
              return (
                <tr key={i}>
                  <td style={{ fontFamily: 'var(--font-data)' }}>{fmtDate(e.date)}</td>
                  <td>
                    <span style={{ color: k.color, fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
                      {k.label}
                    </span>
                  </td>
                  <td>{e.label}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)' }}>
                    {e.source ?? '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <NewsSection ticker={ticker} />
    </div>
  );
}

function NewsSection({ ticker }: { ticker: string }) {
  const { data } = useQuery({
    queryKey: ['company-news', ticker],
    queryFn: () => getCompanyNews(ticker),
    retry: 1,
    staleTime: 10 * 60 * 1000,
  });
  if (!data) return null;
  return (
    <div className="card" style={{ padding: '12px 14px' }}>
      <div className="card-title">News</div>
      {data.items.length === 0 ? (
        <div className="empty-note">{data.note}</div>
      ) : (
        <>
          {data.items.map((n, i) => (
            <div key={i} style={{ padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
              <a href={n.url} target="_blank" rel="noreferrer"
                 style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', textDecoration: 'none' }}>
                {n.title}
              </a>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-data)' }}>
                {n.publisher ?? '—'}{n.published ? ` · ${fmtDate(n.published)}` : ''}
              </div>
            </div>
          ))}
          <div style={{ marginTop: 8, fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
            {data.note}
          </div>
        </>
      )}
    </div>
  );
}

/* ════════════════════════ Peers tab ════════════════════════ */

function PeersTab({ ticker }: { ticker: string }) {
  const navigate = useNavigate();
  const { data, isPending, isError } = useQuery({
    queryKey: ['company-peers', ticker],
    queryFn: () => getCompanyPeers(ticker),
  });
  const deepDive = useMutation({
    mutationFn: () =>
      startResearchRun({
        kind: 'peer_deep_dive',
        tickers: (data?.peers ?? []).slice(0, 4).map((p) => String(p.ticker)),
        label: `${ticker} vs peers`,
      }),
    onSuccess: (res) => navigate(`/artifact/${res.artifact_id}`),
  });
  if (isPending) return <div className="stage-empty">Loading peer group…</div>;
  if (isError) return <div className="stage-empty">Peer comparison unavailable.</div>;
  const peers = data?.peers ?? [];
  if (peers.length < 2) {
    return (
      <div className="stage-empty">
        No peer group yet — peers come from sector/industry identity data, which fills
        as the universe syncs.
      </div>
    );
  }
  const metrics = data?.metrics ?? [];
  // Coverage derived client-side from the present cells: a blank lattice should
  // read as "not retained for this group", not as "computed to nothing". (The
  // peers payload carries no backend coverage block — mirror the Company Page
  // financials honesty using the values already in hand.)
  const subject = peers.find((p) => p.is_subject);
  const subjectAllNull =
    !!subject && metrics.length > 0 && metrics.every((m) => subject[m] == null);
  const colCoverage: Record<string, number> = {};
  for (const m of metrics) colCoverage[m] = peers.filter((p) => p[m] != null).length;
  const sparseCols = metrics.filter((m) => colCoverage[m] === 0);
  const naMetrics = data?.na_metrics ?? [];  // genuinely inapplicable to this sector
  return (
    <div>
      {subjectAllNull && (
        <div className="empty-note" style={{ marginBottom: 10, fontSize: 'var(--text-xs)' }}>
          ⓘ No metrics retained for {ticker} yet — its row is blank because price/financial
          coverage hasn't synced for this name. Peers are shown for context.
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center' }}>
        <button className="btn" disabled={deepDive.isPending} onClick={() => deepDive.mutate()}>
          {deepDive.isPending ? 'Writing deep-dive…' : `Deep-dive ${ticker} vs peers`}
        </button>
        <span style={{ fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
          head-to-head research note · cited · saved as an artifact
        </span>
        {deepDive.isError && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--negative)' }}>
            {(deepDive.error as Error).message}
          </span>
        )}
      </div>
      <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Company</th>
            {metrics.map((m) => (
              <th key={m} style={{ textAlign: 'right' }}>
                {humanizeLabel(m)}
                {colCoverage[m] === 0 && (
                  <span
                    title="not retained for this peer group"
                    style={{ color: 'var(--text-muted)', fontWeight: 400 }}
                  > ·n/a</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {peers.map((p) => (
            <tr key={p.ticker} style={p.is_subject ? { background: 'var(--accent-subtle)' } : undefined}>
              <td style={{ fontFamily: 'var(--font-data)', fontWeight: p.is_subject ? 700 : 400 }}>
                {p.is_subject ? p.ticker : <Link to={`/company/${p.ticker}`}>{p.ticker}</Link>}
              </td>
              <td>{String(p.name ?? '')}</td>
              {metrics.map((m) => (
                <td key={m} style={{ textAlign: 'right', fontFamily: 'var(--font-data)' }}>
                  {fmtMetric(m, p[m] as number | null | undefined)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {sparseCols.length > 0 && (
        <div className="empty-note" style={{ padding: '6px 0 0', fontSize: 'var(--text-xs)' }}>
          ⓘ {sparseCols.map(humanizeLabel).join(', ')} not retained for this peer group —
          these may not apply to the sector or haven't synced.
        </div>
      )}
      {naMetrics.length > 0 && (
        <div className="empty-note" style={{ padding: '4px 0 0', fontSize: 'var(--text-xs)' }}>
          ⓘ {naMetrics.map(humanizeLabel).join(', ')} not applicable to this sector's filers —
          shown on roe / operating margin instead.
        </div>
      )}
    </div>
  );
}

/* ════════════════════════ Research tab (filing-text harness) ════════════════════════ */

function ResearchTab({ ticker }: { ticker: string }) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (kind: 'risk_diff' | 'mdna_note') => runCompanyResearch(ticker, kind),
    onSuccess: (res) => navigate(`/artifact/${res.artifact_id}`),
    onError: (err: Error) => setNotice(err.message),
  });
  return (
    <div>
      <div className="card" style={{ padding: '14px 16px', marginBottom: 12 }}>
        <div className="card-title">Filing-text research</div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 10 }}>
          Bounded runs over {ticker}'s SEC filings. Sections download on demand and are
          cached locally; every claim in the note cites its filing. The result is a
          versioned artifact in your library.
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn" disabled={run.isPending} onClick={() => run.mutate('risk_diff')}>
            Risk factors — what changed YoY
          </button>
          <button className="btn" disabled={run.isPending} onClick={() => run.mutate('mdna_note')}>
            MD&A summary (cited)
          </button>
          <a className="btn btn-ghost" href={exportUrls.financials(ticker)}>
            Financials CSV
          </a>
        </div>
        {run.isPending && (
          <div style={{ marginTop: 10, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Fetching filing sections and writing the note…
          </div>
        )}
        {notice && (
          <div className="banner banner-warning" style={{ marginTop: 10, fontSize: 'var(--text-xs)' }}>
            {notice}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const t = (ticker ?? '').toUpperCase();
  if (!t) return <div className="stage-empty">No ticker specified.</div>;
  return <CompanyDossier ticker={t} />;
}
