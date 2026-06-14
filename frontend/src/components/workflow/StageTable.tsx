/**
 * Shared stage-selection UX (Screener / Thesis / IC Review).
 *
 * Pattern (docs/implementation-map.md §3): ranking is expressed by row order —
 * no rank/score columns. A SELECTED block (accent border) sits above a
 * REMAINING block; row-level +/− buttons move items between them once the
 * stage output exists for that row. Clicking a row expands an inline detail
 * panel; clicking the ticker navigates to /company/:ticker.
 * Operational failure is never styled as an investment judgment.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/* ── Ticker link (every ticker navigates to the Company Page) ── */
export function TickerLink({ ticker }: { ticker: string }) {
  return (
    <Link to={`/company/${ticker}`} className="ticker" onClick={(e) => e.stopPropagation()}>
      {ticker}
    </Link>
  );
}

/* ── Selected / remaining blocks ── */
export function StageBlock({
  variant,
  title,
  count,
  head,
  children,
  emptyText,
}: {
  variant: 'selected' | 'remaining';
  title: string;
  count: number;
  head: ReactNode;
  children: ReactNode;
  emptyText?: string;
}) {
  return (
    <section className={`stage-block${variant === 'selected' ? ' stage-block-selected' : ''}`}>
      <div className="stage-block-header">
        <span className="stage-block-title">{title}</span>
        <span className="stage-block-count">{count}</span>
      </div>
      {count === 0 ? (
        <div className="stage-empty">{emptyText ?? 'Nothing here yet.'}</div>
      ) : (
        <div className="table-shell">
          <table>
            <thead>{head}</thead>
            <tbody>{children}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ── Inline expanded detail row ── */
export function ExpandedRow({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="expanded-area" style={{ cursor: 'default' }}>
        {children}
      </td>
    </tr>
  );
}

/* ── Compact +/− move buttons ── */
export function MoveButton({
  kind,
  enabled,
  busy,
  onClick,
  label,
}: {
  kind: 'promote' | 'dismiss';
  enabled: boolean;
  busy?: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className="move-btn"
      title={label}
      aria-label={label}
      disabled={!enabled || !!busy}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {kind === 'promote' ? '+' : '−'}
    </button>
  );
}

/* ── Row state cue: progress pulse or quiet operational-failure tag ── */
export function StateCue({ state }: { state: string | null | undefined }) {
  if (!state || state === 'completed') return null;
  if (state === 'failed') {
    return (
      <span
        className="opfail-tag"
        title="Operational failure (retried ×3) — excluded from handoff. Not an investment judgment."
      >
        operational failure
      </span>
    );
  }
  return (
    <span className="pulse-text" style={{ fontSize: 'var(--text-xs)' }}>
      <span className="pulse-dot" />
      {state}…
    </span>
  );
}

/** Placeholder for a metric cell whose value is still being generated. */
export function PendingValue() {
  return <span className="pulse-text">—</span>;
}

/** In-flight banner for a stage while its run is executing. */
export function RunningBanner({ label }: { label: string }) {
  return (
    <div className="card" style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
      <span className="pulse-dot" />
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{label}</span>
    </div>
  );
}

/** Quiet operational-failure banner for a failed run. */
export function RunFailedBanner({ error }: { error?: string | null }) {
  return (
    <div className="banner banner-warning" style={{ marginBottom: 14 }}>
      <span className="opfail-tag" style={{ marginRight: 8 }}>
        operational failure
      </span>
      <span style={{ color: 'var(--text-secondary)' }}>
        {error || 'The last run hit an operational error. Re-run when ready — completed artifacts are retained.'}
      </span>
    </div>
  );
}
