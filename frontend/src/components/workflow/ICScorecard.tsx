/**
 * IC Detail Evidence Snapshot — shared by the IC Review expanded row and the
 * ic_verdict renderer in the Workflow Artifact Reader.
 *
 * Deterministic gate model (ADR-0012): hard hurdles first, then gate score =
 * blend of conviction / constitution fit / data quality vs cutoff (default 70).
 */
import type { HurdleFinding } from '../../api/client';

export function ScoreBar({ label, value }: { label: string; value: number | null | undefined }) {
  const v = value == null || Number.isNaN(value) ? null : Math.max(0, Math.min(100, value));
  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <span className="score-bar-track">
        <span className="score-bar-fill" style={{ width: `${v ?? 0}%`, display: 'block' }} />
      </span>
      <span className="score-bar-value">{v == null ? '—' : Math.round(v)}</span>
    </div>
  );
}

export function GateScoreLine({ score, cutoff }: { score: number | null | undefined; cutoff: number | null | undefined }) {
  const s = score == null || Number.isNaN(score) ? null : Math.max(0, Math.min(100, score));
  const c = cutoff == null || Number.isNaN(cutoff) ? null : Math.max(0, Math.min(100, cutoff));
  return (
    <div style={{ marginTop: 10 }}>
      <div className="score-bar-row" style={{ marginBottom: 2 }}>
        <span className="score-bar-label">Gate score</span>
        <span className="score-bar-track">
          <span
            className="score-bar-fill"
            style={{
              width: `${s ?? 0}%`,
              display: 'block',
              background: s != null && c != null ? (s >= c ? 'var(--positive)' : 'var(--negative)') : 'var(--accent)',
            }}
          />
          {c != null && <span className="score-bar-cutoff" style={{ left: `${c}%` }} title={`Pass cutoff ${c}`} />}
        </span>
        <span className="score-bar-value">{s == null ? '—' : Math.round(s)}</span>
      </div>
      <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', textAlign: 'right' }}>
        cutoff {c == null ? '—' : Math.round(c)}
      </div>
    </div>
  );
}

export function HurdleList({ hurdles }: { hurdles: HurdleFinding[] }) {
  if (hurdles.length === 0) {
    return <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>No hard hurdles configured for this review.</div>;
  }
  return (
    <div>
      {hurdles.map((h, i) => (
        <div className="hurdle-row" key={`${h.hurdle}-${i}`}>
          <span
            style={{
              fontFamily: 'var(--font-data)',
              color: h.met == null ? 'var(--text-muted)' : h.met ? 'var(--positive)' : 'var(--negative)',
              flexShrink: 0,
              width: 14,
              textAlign: 'center',
            }}
          >
            {h.met == null ? '·' : h.met ? '✓' : '✕'}
          </span>
          <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-primary)', flexShrink: 0 }}>{h.hurdle}</span>
          <span style={{ color: 'var(--text-secondary)' }}>{h.explanation || (h.met == null ? 'not evaluated' : h.met ? 'met' : 'missed')}</span>
        </div>
      ))}
    </div>
  );
}

export function ICScorecard({
  rationale,
  hurdles,
  conviction,
  constitutionFit,
  dataQuality,
  gateScore,
  cutoff,
}: {
  rationale?: string | null;
  hurdles?: HurdleFinding[] | null;
  conviction?: number | null;
  constitutionFit?: number | null;
  dataQuality?: number | null;
  gateScore?: number | null;
  cutoff?: number | null;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: 8 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="expanded-card">
          <div className="expanded-card-title">Verdict Rationale</div>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            {rationale || 'No rationale recorded.'}
          </div>
        </div>
        <div className="expanded-card">
          <div className="expanded-card-title">Hard Hurdles</div>
          <HurdleList hurdles={hurdles ?? []} />
        </div>
      </div>
      <div className="expanded-card">
        <div className="expanded-card-title">Gate Scoring</div>
        <ScoreBar label="Conviction" value={conviction} />
        <ScoreBar label="Constitution Fit" value={constitutionFit} />
        <ScoreBar label="Data Quality" value={dataQuality} />
        <GateScoreLine score={gateScore} cutoff={cutoff ?? 70} />
      </div>
    </div>
  );
}
