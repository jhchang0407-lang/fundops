/**
 * Workflow Artifact Reader (/artifact/:id) — shared shell + type-specific
 * body renderer over retained Structured Workflow Artifacts. Artifacts are
 * locked historical records: read-only by design, never "disabled".
 */
import { useEffect, useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { artifactExportUrl, getArtifact } from '../api/client';
import { askAt } from '../components/AskAnywhere';
import type {
  ArtifactKeyFigure,
  ArtifactResponse,
  ArtifactSectionTable,
  HurdleFinding,
  PassEvidence,
} from '../api/client';
import { ICScorecard } from '../components/workflow/ICScorecard';
import { ReturnProfilePanel } from '../components/workflow/ReturnProfile';
import { normalizeReturnComponents } from '../components/workflow/helpers';
import { fmtDate, fmtMetric, humanizeLabel } from '../utils/formatFinancials';

/* ── payload helpers ── */

type Payload = Record<string, unknown>;

const KERNEL_KEYS = new Set([
  'kind',
  'schema_version',
  'entity',
  'ticker',
  'generated_at',
  'constitution_version',
  'evidence_bundle_id',
  'validation',
  'citations',
  'sections',
  'fields',
]);

function pools(payload: Payload): Payload[] {
  const out: Payload[] = [payload];
  for (const sub of ['fields', 'body']) {
    const v = payload[sub];
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(v as Payload);
  }
  return out;
}

function pick(payload: Payload, ...keys: string[]): unknown {
  for (const pool of pools(payload)) {
    for (const k of keys) {
      const v = pool[k];
      if (v !== undefined && v !== null) return v;
    }
  }
  return undefined;
}

const pickStr = (p: Payload, ...keys: string[]): string | null => {
  const v = pick(p, ...keys);
  return typeof v === 'string' && v ? v : null;
};

const pickNum = (p: Payload, ...keys: string[]): number | null => {
  const v = pick(p, ...keys);
  return typeof v === 'number' && !Number.isNaN(v) ? v : null;
};

function isRecord(x: unknown): x is Payload {
  return !!x && typeof x === 'object' && !Array.isArray(x);
}

const recNum = (r: Payload | null, key: string): number | null => {
  const v = r?.[key];
  return typeof v === 'number' && !Number.isNaN(v) ? v : null;
};

const recStr = (r: Payload | null, key: string): string | null => {
  const v = r?.[key];
  return typeof v === 'string' && v ? v : null;
};

interface SectionBlock {
  title: string;
  content: string;
}

/** Sections may be `[{title, content}]`-ish arrays or `{title: content}` records. */
function sectionsOf(payload: Payload): SectionBlock[] {
  const raw = pick(payload, 'sections', 'scope_qa', 'scope_questions', 'scope');
  if (!raw) return [];
  const out: SectionBlock[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue;
      const o = item as Payload;
      const title =
        (typeof o.title === 'string' && o.title) ||
        (typeof o.heading === 'string' && o.heading) ||
        (typeof o.question === 'string' && o.question) ||
        (typeof o.name === 'string' && o.name) ||
        '';
      const content =
        (typeof o.content === 'string' && o.content) ||
        (typeof o.body === 'string' && o.body) ||
        (typeof o.answer === 'string' && o.answer) ||
        (typeof o.text === 'string' && o.text) ||
        '';
      if (title || content) out.push({ title: title || '—', content });
    }
  } else if (typeof raw === 'object') {
    for (const [k, v] of Object.entries(raw as Payload)) {
      if (typeof v === 'string') out.push({ title: humanizeLabel(k), content: v });
    }
  }
  return out;
}

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const KIND_LABELS: Record<string, string> = {
  investment_memo: 'Investment Memo',
  thesis: 'Completed Thesis',
  ic_verdict: 'IC Verdict',
  screener_snapshot: 'Screener Snapshot',
  thesis_health_check: 'Thesis Health Check',
  portfolio_review: 'Portfolio Review',
  learning_card: 'Learning Card',
};

/* ── markdown ── */

function MarkdownBody({ md }: { md: string }) {
  const html = useMemo(() => {
    const raw = marked(md, { breaks: true, gfm: true }) as string;
    const withIds = raw.replace(/<h2([^>]*)>([\s\S]*?)<\/h2>/g, (_m, attrs: string, inner: string) => {
      const text = inner.replace(/<[^>]+>/g, '');
      return `<h2${attrs} id="md-${slugify(text)}">${inner}</h2>`;
    });
    return DOMPurify.sanitize(withIds);
  }, [md]);
  return <div className="reader-body reader-markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

/* ── kind-specific bodies ── */

function isSectionTable(x: unknown): x is ArtifactSectionTable {
  return (
    !!x &&
    typeof x === 'object' &&
    Array.isArray((x as ArtifactSectionTable).columns) &&
    Array.isArray((x as ArtifactSectionTable).rows)
  );
}

function isKeyFigure(x: unknown): x is ArtifactKeyFigure {
  return !!x && typeof x === 'object' && typeof (x as ArtifactKeyFigure).label === 'string';
}

function SectionTableBlock({ name, table }: { name: string; table: ArtifactSectionTable }) {
  return (
    <div style={{ marginBottom: 10 }}>
      {name && <div className="muted" style={{ fontSize: 'var(--text-xs)', marginBottom: 4 }}>{humanizeLabel(name)}</div>}
      <div className="table-shell">
        <table className="artifact-data-table">
          <thead>
            <tr>
              {table.columns.map((c, i) => (
                <th key={`${c}-${i}`} className={i > 0 ? 'num' : undefined}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} className={ci > 0 ? 'num' : undefined}>
                    {cell == null ? '—' : String(cell)}
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

interface RichMemoSection {
  title: string;
  paragraphs: string[];
  tables: { name: string; table: ArtifactSectionTable }[];
  keyFigures: ArtifactKeyFigure[];
}

/** Memo sections: arrays of `{title, content, tables?, key_figures?}` or a
 *  record of `{title, section_thesis, subsections, tables?, key_figures?}`. */
function memoSections(payload: Payload): RichMemoSection[] {
  const raw = pick(payload, 'sections');
  const out: RichMemoSection[] = [];
  const fromObj = (key: string, o: Payload) => {
    const title = recStr(o, 'title') ?? recStr(o, 'heading') ?? recStr(o, 'name') ?? humanizeLabel(key);
    const paragraphs: string[] = [];
    for (const k of ['content', 'body', 'text', 'section_thesis', 'answer']) {
      const v = o[k];
      if (typeof v === 'string' && v) paragraphs.push(v);
    }
    if (isRecord(o.subsections)) {
      for (const v of Object.values(o.subsections as Payload)) {
        if (typeof v === 'string' && v) paragraphs.push(v);
      }
    }
    const tables: { name: string; table: ArtifactSectionTable }[] = [];
    if (isRecord(o.tables)) {
      for (const [name, t] of Object.entries(o.tables as Payload)) {
        if (isSectionTable(t)) tables.push({ name, table: t });
      }
    }
    const keyFigures = Array.isArray(o.key_figures) ? o.key_figures.filter(isKeyFigure) : [];
    if (title || paragraphs.length || tables.length || keyFigures.length) {
      out.push({ title: title || '—', paragraphs, tables, keyFigures });
    }
  };
  if (Array.isArray(raw)) {
    raw.forEach((item, i) => {
      if (isRecord(item)) fromObj(`section_${i + 1}`, item);
    });
  } else if (isRecord(raw)) {
    for (const [k, v] of Object.entries(raw)) {
      if (isRecord(v)) fromObj(k, v);
      else if (typeof v === 'string') out.push({ title: humanizeLabel(k), paragraphs: [v], tables: [], keyFigures: [] });
    }
  }
  return out;
}

function MemoBody({ artifact }: { artifact: ArtifactResponse }) {
  const md = artifact.rendered_md;
  const headings = useMemo(
    () =>
      (md ?? '')
        .split('\n')
        .filter((l) => l.startsWith('## '))
        .map((l) => l.slice(3).trim()),
    [md],
  );

  // Prefer rendered_md when present; otherwise rebuild from structured sections
  // (paragraphs + key figures + tables).
  if (!md) {
    const sections = memoSections(artifact.payload);
    if (sections.length === 0) return <GenericBody artifact={artifact} />;
    return (
      <div>
        {sections.map((s) => (
          <div key={s.title} style={{ marginBottom: 16 }}>
            <div className="section-label">{s.title}</div>
            {s.paragraphs.map((para, i) => (
              <div className="reader-body" key={i} style={{ marginBottom: 8 }}>
                {para}
              </div>
            ))}
            {s.keyFigures.length > 0 && (
              <div className="kv-grid" style={{ margin: '6px 0 10px', maxWidth: 480 }}>
                {s.keyFigures.map((kf, i) => (
                  <span key={`${kf.label}-${i}`} style={{ display: 'contents' }}>
                    <span className="kv-key">{kf.label}</span>
                    <span className="kv-val">{kf.value == null ? '—' : String(kf.value)}</span>
                  </span>
                ))}
              </div>
            )}
            {s.tables.map((t) => (
              <SectionTableBlock key={t.name} name={t.name} table={t.table} />
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: headings.length > 1 ? '190px minmax(0, 1fr)' : 'minmax(0, 1fr)', gap: 18, alignItems: 'start' }}>
      {headings.length > 1 && (
        <nav style={{ position: 'sticky', top: 8 }}>
          <div className="section-label">Sections</div>
          {headings.map((h) => (
            <button
              key={h}
              className="suggest-item"
              style={{ display: 'block' }}
              onClick={() => document.getElementById(`md-${slugify(h)}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            >
              {h}
            </button>
          ))}
        </nav>
      )}
      <MarkdownBody md={md} />
    </div>
  );
}

/**
 * Markdown for a thesis opens with "# Thesis: TICKER" plus the same summary
 * sentence already shown in the Summary card — strip both before rendering
 * so nothing appears verbatim twice.
 */
function dedupeThesisMd(md: string, summary: string | null): string {
  const lines = md.split('\n');
  let i = 0;
  while (i < lines.length && lines[i].trim() === '') i++;
  if (i < lines.length && /^#\s/.test(lines[i])) i++;
  while (i < lines.length && lines[i].trim() === '') i++;
  if (summary) {
    // Drop the first paragraph when it repeats the summary verbatim.
    let j = i;
    while (j < lines.length && lines[j].trim() !== '') j++;
    const para = lines.slice(i, j).join(' ').trim();
    if (para === summary.trim()) i = j;
  }
  return lines.slice(i).join('\n').trim();
}

function ThesisBody({ artifact }: { artifact: ArtifactResponse }) {
  const p = artifact.payload;
  const body = isRecord(p.body) ? (p.body as Payload) : p;
  // Verified payload shape: body.price + body.return_potential.{expected_return_pct,
  // fair_value, valuation_method, components}.
  const rp = isRecord(body.return_potential) ? (body.return_potential as Payload) : null;
  const scopeRec = isRecord(body.scope) ? (body.scope as Payload) : null;
  const summary = pickStr(p, 'summary', 'thesis_summary');
  const scope = sectionsOf(p);
  const md = artifact.rendered_md ? dedupeThesisMd(artifact.rendered_md, summary) : null;
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)', gap: 12, marginBottom: 16 }}>
        <div>
          <div className="section-label">Summary</div>
          <div className="reader-body">{summary || 'No summary recorded.'}</div>
        </div>
        <ReturnProfilePanel
          price={pickNum(p, 'price', 'current_price')}
          fairValue={recNum(rp, 'fair_value') ?? pickNum(p, 'fair_value')}
          expectedReturnPct={
            recNum(rp, 'expected_return_pct') ?? pickNum(p, 'expected_return_pct', 'expected_return')
          }
          valuationMethod={recStr(rp, 'valuation_method') ?? pickStr(p, 'valuation_method')}
          components={normalizeReturnComponents(rp?.components ?? pick(p, 'return_components'))}
          coherenceWarning={pickStr(p, 'coherence_warning')}
          keyRisk={pickStr(p, 'key_risk') ?? recStr(scopeRec, 'key_risk')}
          capped={pick(p, 'capped') === true}
        />
      </div>
      {scope.length > 0 ? (
        <div>
          <div className="section-label">Research Scope</div>
          {scope.map((s) => (
            <div className="card" key={s.title} style={{ marginBottom: 8 }}>
              <div className="card-title">{s.title}</div>
              <div className="reader-body" style={{ fontSize: 'var(--text-sm)' }}>
                {s.content}
              </div>
            </div>
          ))}
        </div>
      ) : (
        md && <MarkdownBody md={md} />
      )}
    </div>
  );
}

function isHurdleFinding(x: unknown): x is HurdleFinding {
  return !!x && typeof x === 'object' && typeof (x as HurdleFinding).hurdle === 'string';
}

function ICBody({ artifact }: { artifact: ArtifactResponse }) {
  const p = artifact.payload;
  const verdict = pickStr(p, 'verdict');
  const hurdlesRaw = pick(p, 'hurdle_findings', 'hurdles');
  const hurdles = Array.isArray(hurdlesRaw) ? hurdlesRaw.filter(isHurdleFinding) : [];
  const isOverride = pick(p, 'is_override') === true;
  const prior = pickStr(p, 'prior_verdict');
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        {verdict === 'pass' ? <span className="verdict-pass">PASS</span> : verdict === 'fail' ? <span className="verdict-fail">FAIL</span> : <span className="verdict-pending">—</span>}
        {isOverride && <span className="tag-override">user override{prior ? ` · was ${prior.toUpperCase()}` : ''}</span>}
      </div>
      <ICScorecard
        rationale={pickStr(p, 'rationale')}
        hurdles={hurdles}
        conviction={pickNum(p, 'conviction')}
        constitutionFit={pickNum(p, 'constitution_fit', 'fit')}
        dataQuality={pickNum(p, 'data_quality')}
        gateScore={pickNum(p, 'gate_score')}
        cutoff={pickNum(p, 'cutoff', 'pass_cutoff')}
      />
    </div>
  );
}

function isPassEvidence(x: unknown): x is PassEvidence {
  return (
    !!x &&
    typeof x === 'object' &&
    (typeof (x as PassEvidence).criterion === 'string' ||
      typeof (x as PassEvidence).label === 'string')
  );
}

/** Prefer the humanized backend fields; fall back to the raw machine values. */
function evidenceCells(e: PassEvidence): { name: string; sub: string | null; threshold: string; observed: string } {
  const metric = typeof e.metric === 'string' ? e.metric : e.criterion ?? '';
  return {
    name: e.label || humanizeLabel((e.criterion ?? '').split('.').pop() ?? e.criterion ?? '—'),
    sub: e.rule ?? null,
    threshold: e.threshold_display ?? (e.threshold != null ? String(e.threshold) : '—'),
    observed:
      e.observed_display ??
      (typeof e.observed === 'number' ? fmtMetric(metric, e.observed) : e.observed != null ? String(e.observed) : '—'),
  };
}

interface RankingComponentRow {
  label: string;
  observed: string | null;
  percentile: number | null;
  weight: number | null;
  contribution: number | null;
}

/** `ranking_components` arrives as `[{criterion_id, metric, observed, percentile,
 *  weight, contribution, label?}]` (preferred) or a legacy `{metric: number}` record. */
function normalizeRankingComponents(raw: unknown): RankingComponentRow[] {
  if (Array.isArray(raw)) {
    const out: RankingComponentRow[] = [];
    for (const item of raw) {
      if (!isRecord(item)) continue;
      const metric = recStr(item, 'metric');
      const label =
        recStr(item, 'label') ??
        humanizeLabel(metric ?? (recStr(item, 'criterion_id') ?? '').split('.').pop() ?? 'component');
      const observedNum = recNum(item, 'observed');
      out.push({
        label,
        observed:
          recStr(item, 'observed_display') ??
          (observedNum != null ? fmtMetric(metric ?? label, observedNum) : null),
        percentile: recNum(item, 'percentile'),
        weight: recNum(item, 'weight') ?? recNum(item, 'normalized_weight'),
        contribution: recNum(item, 'contribution') ?? recNum(item, 'score'),
      });
    }
    return out;
  }
  if (isRecord(raw)) {
    return Object.entries(raw)
      .filter((e): e is [string, number] => typeof e[1] === 'number')
      .map(([k, v]) => ({
        label: humanizeLabel(k),
        observed: fmtMetric(k, v),
        percentile: null,
        weight: null,
        contribution: null,
      }));
  }
  return [];
}

function ScreenerBody({ artifact }: { artifact: ArtifactResponse }) {
  const p = artifact.payload;
  const rank = pickNum(p, 'rank');
  const evidenceRaw = pick(p, 'pass_evidence');
  const evidence = Array.isArray(evidenceRaw) ? evidenceRaw.filter(isPassEvidence) : [];
  const components = normalizeRankingComponents(pick(p, 'ranking_components'));
  const explanation = pickStr(p, 'ranking_explanation');
  return (
    <div>
      <div className="inline-metadata" style={{ marginBottom: 14 }}>
        <span>Rank {rank != null ? `#${rank}` : '—'} in this screener run</span>
        {pickNum(p, 'universe_size') != null && <span>universe {pickNum(p, 'universe_size')}</span>}
      </div>
      {explanation && (
        <div style={{ marginBottom: 16 }}>
          <div className="section-label">Ranking Explanation</div>
          <div className="reader-body">{explanation}</div>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)', gap: 12 }}>
        <div>
          <div className="section-label">Pass Evidence</div>
          {evidence.length === 0 ? (
            <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>No pass evidence recorded.</div>
          ) : (
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Criterion</th>
                    <th className="num">Threshold</th>
                    <th className="num">Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.map((e, i) => {
                    const c = evidenceCells(e);
                    return (
                      <tr key={`${e.criterion ?? c.name}-${i}`}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{c.name}</div>
                          {c.sub && (
                            <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>{c.sub}</div>
                          )}
                        </td>
                        <td className="num">{c.threshold}</td>
                        <td className="num">{c.observed}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div>
          <div className="section-label">Ranking Components</div>
          {components.length === 0 ? (
            <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>No component breakdown recorded.</div>
          ) : (
            <div>
              {components.map((c, i) => (
                <div className="component-row" key={`${c.label}-${i}`}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>{c.label}</div>
                    <div className="component-row-meta">
                      {[
                        c.observed != null ? `observed ${c.observed}` : null,
                        c.percentile != null ? `${Math.round(c.percentile)}th pct` : null,
                        c.weight != null ? `weight ${Math.round(c.weight * 100)}%` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </div>
                  </div>
                  {c.contribution != null && (
                    <span className="component-row-score">{c.contribution.toFixed(2)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function GenericBody({ artifact }: { artifact: ArtifactResponse }) {
  const p = artifact.payload;
  const sections = sectionsOf(p);
  const kv: [string, unknown][] = [];
  for (const pool of pools(p)) {
    for (const [k, v] of Object.entries(pool)) {
      if (pool === p && KERNEL_KEYS.has(k)) continue;
      if (v == null || typeof v === 'object') continue;
      if (!kv.some(([key]) => key === k)) kv.push([k, v]);
    }
  }
  return (
    <div>
      {kv.length > 0 && (
        <div className="kv-grid" style={{ marginBottom: 16, maxWidth: 560 }}>
          {kv.map(([k, v]) => (
            <span key={k} style={{ display: 'contents' }}>
              <span className="kv-key">{humanizeLabel(k)}</span>
              <span className="kv-val">{typeof v === 'number' ? fmtMetric(k, v) : String(v)}</span>
            </span>
          ))}
        </div>
      )}
      {sections.map((s) => (
        <div key={s.title} style={{ marginBottom: 14 }}>
          <div className="section-label">{s.title}</div>
          <div className="reader-body">{s.content}</div>
        </div>
      ))}
      {artifact.rendered_md && <MarkdownBody md={artifact.rendered_md} />}
      {kv.length === 0 && sections.length === 0 && !artifact.rendered_md && (
        <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>This artifact has no renderable body.</div>
      )}
    </div>
  );
}

/* ── shell ── */

export default function ArtifactReader() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data, isPending, isError, error } = useQuery({
    queryKey: ['artifact', id],
    queryFn: () => getArtifact(id!),
    enabled: !!id,
  });

  // Select-to-ask: highlight any passage in the document and the popover
  // offers questions about it. The quote rides with the question, and the
  // companion's artifact context lets the analyst open this document.
  useEffect(() => {
    const onMouseUp = () => {
      // Defer past the click that follows mouseup, which closes the popover.
      setTimeout(() => {
        const sel = window.getSelection();
        const text = sel?.toString().replace(/\s+/g, ' ').trim() ?? '';
        if (!sel || sel.isCollapsed || text.length < 12) return;
        const node = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement;
        if (!node?.closest('.reader-body, .artifact-locked')) return;
        const rect = sel.getRangeAt(0).getBoundingClientRect();
        const quote = text.length > 420 ? `${text.slice(0, 420)}…` : text;
        askAt(Math.min(rect.left + rect.width / 2, window.innerWidth - 320), rect.bottom, {
          title: `Selected: “${quote.slice(0, 60)}${quote.length > 60 ? '…' : ''}”`,
          quote,
          questions: [
            'Explain this passage in plain terms',
            'What evidence supports this claim?',
            'What are the counter-arguments or risks here?',
          ],
        });
      }, 30);
    };
    document.addEventListener('mouseup', onMouseUp);
    return () => document.removeEventListener('mouseup', onMouseUp);
  }, [id]);

  if (!id) return <div className="stage-empty">No artifact specified.</div>;
  if (isPending) return <div className="stage-empty">Opening artifact…</div>;
  if (isError) return <div className="stage-empty">Could not open artifact: {(error as Error).message}</div>;
  if (!data) return null;

  const kindLabel = KIND_LABELS[data.kind] ?? humanizeLabel(data.kind);
  const constitution = data.constitution_version_id ?? (pickStr(data.payload, 'constitution_version') || null);

  const goBack = () => {
    if (window.history.length > 1) navigate(-1);
    else if (data.ticker) navigate(`/company/${data.ticker}`);
    else navigate('/dashboard');
  };

  const body =
    data.kind === 'investment_memo' ? (
      <MemoBody artifact={data} />
    ) : data.kind === 'thesis' ? (
      <ThesisBody artifact={data} />
    ) : data.kind === 'ic_verdict' ? (
      <ICBody artifact={data} />
    ) : data.kind === 'screener_snapshot' ? (
      <ScreenerBody artifact={data} />
    ) : (
      <GenericBody artifact={data} />
    );

  return (
    <div>
      <div className="page-header" style={{ alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={goBack}>
            ← Back
          </button>
          {data.ticker && (
            <Link to={`/company/${data.ticker}`} className="ticker" style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>
              {data.ticker}
            </Link>
          )}
          <span className="badge badge-muted">{kindLabel}</span>
          <span className="inline-metadata">
            <span>generated {fmtDate(data.created_at)}</span>
            {constitution && <span>constitution {constitution}</span>}
            {data.schema_version != null && <span>schema v{data.schema_version}</span>}
          </span>
        </div>
        <a className="btn" href={artifactExportUrl(data.id)} download>
          Export ⬇
        </a>
      </div>

      <div className="artifact-locked" style={{ padding: '14px 18px' }}>
        <div className="artifact-locked-caption" style={{ marginBottom: 12 }}>
          Generated {fmtDate(data.created_at)} · read-only · retained workflow record ·
          select any passage to ask about it
        </div>
        {body}
        <div className="inline-metadata" style={{ marginTop: 18, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
          <span>Run {data.run_id ?? '—'}</span>
          <span>Evidence bundle {data.evidence_bundle_id ?? '—'}</span>
          <span>Constitution {constitution ?? '—'}</span>
        </div>
      </div>
    </div>
  );
}
