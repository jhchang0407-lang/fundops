/**
 * Return Profile panel — shared by the Thesis stage expanded detail and the
 * thesis renderer in the Workflow Artifact Reader.
 */
import { fmtPct, fmtPrice } from '../../utils/formatFinancials';
import type { ReturnComponentEntry } from './helpers';

const BAR_COLORS = ['var(--info)', 'var(--positive)', 'var(--accent)', 'var(--text-muted)', 'var(--warning)'];

export function ReturnComponentBar({ components }: { components: ReturnComponentEntry[] }) {
  const total = components.reduce((s, c) => s + Math.abs(c.value), 0);
  if (components.length === 0 || total === 0) return null;
  return (
    <div>
      <div className="return-bar" style={{ marginBottom: 6 }}>
        {components.map((c, i) => (
          <div
            key={c.label}
            style={{ width: `${(Math.abs(c.value) / total) * 100}%`, background: BAR_COLORS[i % BAR_COLORS.length] }}
            title={`${c.label} ${fmtPct(c.value)}`}
          />
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px', fontSize: 10, fontFamily: 'var(--font-data)', color: 'var(--text-muted)' }}>
        {components.map((c, i) => (
          <span key={c.label}>
            <span className="return-legend-dot" style={{ background: BAR_COLORS[i % BAR_COLORS.length] }} />
            {c.label} {fmtPct(c.value)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ReturnProfilePanel({
  price,
  fairValue,
  expectedReturnPct,
  valuationMethod,
  components,
  coherenceWarning,
  keyRisk,
  capped,
}: {
  price?: number | null;
  fairValue?: number | null;
  expectedReturnPct?: number | null;
  valuationMethod?: string | null;
  components: ReturnComponentEntry[];
  coherenceWarning?: string | null;
  keyRisk?: string | null;
  capped?: boolean;
}) {
  const er = expectedReturnPct;
  return (
    <div className="expanded-card">
      <div className="expanded-card-title">
        Return Profile
        {capped && (
          <span className="tag-amber" style={{ marginLeft: 8 }} title="Return profile capped by selection ranking — weak or unsupported return evidence.">
            weak return profile
          </span>
        )}
      </div>
      <div className="kv-grid" style={{ marginBottom: 10 }}>
        <span className="kv-key">Price</span>
        <span className="kv-val">{fmtPrice(price)}</span>
        <span className="kv-key">Fair value</span>
        <span className="kv-val">{fmtPrice(fairValue)}</span>
        <span className="kv-key">Expected return</span>
        <span className="kv-val" style={{ color: er == null ? undefined : er >= 0 ? 'var(--positive)' : 'var(--negative)', fontWeight: 600 }}>
          {fmtPct(er)}
        </span>
        <span className="kv-key">Valuation method</span>
        <span className="kv-val">{valuationMethod || '—'}</span>
      </div>
      <ReturnComponentBar components={components} />
      {coherenceWarning && (
        <div style={{ marginTop: 10, fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>
          <span className="tag-amber" style={{ marginRight: 6 }}>coherence</span>
          {coherenceWarning}
        </div>
      )}
      {keyRisk && (
        <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', marginRight: 6 }}>
            Key risk
          </span>
          {keyRisk}
        </div>
      )}
    </div>
  );
}
